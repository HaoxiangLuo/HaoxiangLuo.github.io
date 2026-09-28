#!/usr/bin/env python3
"""Archive the newest articles from the site's journal shortlist.

The journal list lives in `_data/academic_frontiers_sources.yml` and is checked
by hand against JCR data once a year. This script never searches by keyword or
subject: it asks OpenAlex only for works whose primary location carries one of
the whitelisted ISSN-L values.

Only metadata is stored — title, authors, journal, date, DOI and a short
abstract excerpt. No publisher page is scraped, no PDF is downloaded and no
full text is kept. When OpenAlex misbehaves or returns nothing, the existing
archive is left exactly as it is.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "_data" / "academic_frontiers_sources.yml"
OUTPUT = ROOT / "_data" / "academic_frontiers.json"

ENDPOINT = "https://api.openalex.org/works"
USER_AGENT = "HaoxiangLuo.github.io academic-frontiers collector/1.0"

WINDOW_DAYS = 30          # only articles published in the last 30 days
MAX_PER_JOURNAL = 3
MAX_ITEMS = 24
MAX_DAYS = 180            # how much history the archive keeps
ABSTRACT_LIMIT = 450
MAX_AUTHORS = 6
MAX_ISSN_PER_QUERY = 5    # OpenAlex accepts 50 OR values; stay well below it
MAX_ATTEMPTS = 4
REQUEST_TIMEOUT = 30
BACKOFF_BASE = 2.0
TIMEZONE = ZoneInfo("Asia/Shanghai")


def today() -> str:
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")


def stamp() -> str:
    return datetime.now(TIMEZONE).isoformat(timespec="seconds")


def parse_sources(path: Path) -> list[dict]:
    """Read the short list without adding a YAML dependency.

    The file is a flat sequence of `- key: value` mappings written by hand, so
    a small reader is enough and keeps the script on the standard library.
    """
    entries: list[dict] = []
    current: dict | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("- "):
            current = {}
            entries.append(current)
            line = line[2:].strip()
            if not line:
                continue
        if current is None or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip('"').strip("'")
        if value.startswith("[") and value.endswith("]"):
            current[key.strip()] = [part.strip().strip('"').strip("'") for part in value[1:-1].split(",") if part.strip()]
        else:
            current[key.strip()] = value
    return entries


def active_sources(entries: list[dict]) -> list[dict]:
    selected: list[dict] = []
    for entry in entries:
        if str(entry.get("active", "false")).strip().lower() != "true":
            continue
        issn = str(entry.get("issn_l", "")).strip()
        if not issn:
            continue
        focus = entry.get("focus")
        selected.append(
            {
                "name": str(entry.get("name", "")).strip(),
                "issn_l": issn,
                "focus": [str(part) for part in focus] if isinstance(focus, list) else [],
                "tier": str(entry.get("tier", "")).strip(),
            }
        )
    return selected


def request_json(url: str) -> dict:
    """GET with exponential backoff for 429 and 5xx responses."""
    delay = BACKOFF_BASE
    last_error = "unknown error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code not in (429, 500, 502, 503, 504):
                raise
        except Exception as exc:  # noqa: BLE001 - report and retry
            last_error = str(exc)
        if attempt < MAX_ATTEMPTS:
            print(f"warning: OpenAlex request failed ({last_error}); retrying in {delay:.0f}s", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"OpenAlex unavailable after {MAX_ATTEMPTS} attempts: {last_error}")


def build_url(issns: list[str], since: str) -> str:
    filters = [
        f"primary_location.source.issn:{'|'.join(issns)}",
        "type:article",
        "has_abstract:true",
        "is_retracted:false",
        f"from_publication_date:{since}",
    ]
    query = urllib.parse.urlencode(
        {
            "filter": ",".join(filters),
            "sort": "publication_date:desc",
            "per-page": 100,
        }
    )
    return f"{ENDPOINT}?{query}"


def fetch_works(issns: list[str], since: str) -> list[dict]:
    """Query OpenAlex in small OR batches so no single filter explodes."""
    works: list[dict] = []
    seen_ids: set[str] = set()
    for start in range(0, len(issns), MAX_ISSN_PER_QUERY):
        batch = issns[start : start + MAX_ISSN_PER_QUERY]
        payload = request_json(build_url(batch, since))
        for work in payload.get("results", []):
            identifier = str(work.get("id") or "")
            if identifier and identifier in seen_ids:
                continue
            seen_ids.add(identifier)
            works.append(work)
    return works


def abstract_text(inverted: object) -> str:
    """Rebuild the abstract from OpenAlex's inverted index."""
    if not isinstance(inverted, dict) or not inverted:
        return ""
    slots: dict[int, str] = {}
    for word, positions in inverted.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            slots[int(position)] = str(word)
    return " ".join(slots[index] for index in sorted(slots))


def excerpt(text: str, limit: int = ABSTRACT_LIMIT) -> str:
    """Trim to `limit` characters on a whole-word boundary."""
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= limit:
        return clean
    cut = clean[: limit - 1]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:.") + "…"


def normalise_doi(value: str) -> str:
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", (value or "").strip())


def to_item(work: dict, sources_by_issn: dict[str, dict]) -> dict | None:
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    issn = str(source.get("issn_l") or "").strip()
    if issn and issn not in sources_by_issn:
        return None
    meta = sources_by_issn.get(issn, {})

    doi = normalise_doi(str(work.get("doi") or ""))
    openalex_id = str(work.get("id") or "").strip()
    identifier = f"doi:{doi}" if doi else (f"openalex:{openalex_id}" if openalex_id else "")
    if not identifier:
        return None

    authors: list[str] = []
    for authorship in work.get("authorships", []) or []:
        author = (authorship or {}).get("author") or {}
        name = str(author.get("display_name") or "").strip()
        if name and name not in authors:
            authors.append(name)
        if len(authors) == MAX_AUTHORS:
            break

    landing = str(location.get("landing_page_url") or "").strip()
    abstract = abstract_text(work.get("abstract_inverted_index"))

    return {
        "id": identifier,
        "title": str(work.get("title") or work.get("display_name") or "").strip(),
        "abstract_excerpt": excerpt(abstract) if abstract else None,
        "journal": str(source.get("display_name") or meta.get("name") or "").strip(),
        "issn_l": issn,
        "published_at": str(work.get("publication_date") or "").strip(),
        "authors": authors,
        "doi_url": f"https://doi.org/{doi}" if doi else "",
        "landing_page_url": landing or (f"https://doi.org/{doi}" if doi else ""),
        "source_tier": meta.get("tier", ""),
        "focus": meta.get("focus", []),
    }


def select_items(works: list[dict], sources: list[dict]) -> list[dict]:
    """Keep the newest articles: at most three per journal, 24 in total."""
    sources_by_issn = {entry["issn_l"]: entry for entry in sources}
    items: list[dict] = []
    for work in works:
        item = to_item(work, sources_by_issn)
        if item and item["published_at"] and item["title"]:
            items.append(item)

    items.sort(key=lambda item: item["published_at"], reverse=True)

    per_journal: dict[str, int] = {}
    selected: list[dict] = []
    for item in items:
        key = item["issn_l"] or item["journal"]
        if per_journal.get(key, 0) >= MAX_PER_JOURNAL:
            continue
        per_journal[key] = per_journal.get(key, 0) + 1
        selected.append(item)
        if len(selected) == MAX_ITEMS:
            break
    return selected


def merge_archive(existing: dict, items: list[dict], cutoff: str) -> list[dict]:
    """Merge by stable id and drop anything older than the retention window."""
    by_id: dict[str, dict] = {}
    for item in existing.get("items", []) or []:
        if isinstance(item, dict) and item.get("id"):
            by_id[str(item["id"])] = item
    for item in items:
        by_id[item["id"]] = item
    kept = [item for item in by_id.values() if str(item.get("published_at") or "") >= cutoff]
    kept.sort(key=lambda item: (str(item.get("published_at") or ""), str(item.get("journal") or "")), reverse=True)
    return kept


def load_archive() -> dict:
    if not OUTPUT.exists():
        return {"updated_at": None, "items": []}
    try:
        raw = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - never overwrite a damaged archive
        print(f"error: cannot read {OUTPUT.name}: {exc}", file=sys.stderr)
        return {"updated_at": None, "items": []}
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        return {"updated_at": None, "items": []}
    return raw


def write_archive(items: list[dict]) -> None:
    archive = {"updated_at": stamp(), "items": items}
    OUTPUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=SOURCES, help="override the journal shortlist (for tests)")
    parser.add_argument("--dry-run", action="store_true", help="collect and report without writing the archive")
    args = parser.parse_args()

    if not args.sources.exists():
        print(f"error: journal shortlist is missing: {args.sources}", file=sys.stderr)
        return 1

    sources = active_sources(parse_sources(args.sources))
    existing = load_archive()

    if not sources:
        # A broad OpenAlex search would be the wrong answer here: without a
        # whitelist there is nothing to filter on, so keep the archive intact.
        print("error: no active journals in the shortlist; not contacting OpenAlex", file=sys.stderr)
        if not existing["items"]:
            if args.dry_run:
                print("dry run: would write an empty archive")
            else:
                write_archive([])
                print(f"wrote empty archive to {OUTPUT.name}")
        return 0

    since = (datetime.now(TIMEZONE) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    issns = [entry["issn_l"] for entry in sources]

    try:
        works = fetch_works(issns, since)
    except Exception as exc:  # noqa: BLE001 - keep the archive on failure
        print(f"error: OpenAlex collection failed: {exc}", file=sys.stderr)
        print(f"error: keeping the existing archive ({len(existing['items'])} items)", file=sys.stderr)
        return 0

    items = select_items(works, sources)
    if not items:
        print(f"no new articles since {since}; keeping the existing archive ({len(existing['items'])} items)")
        return 0

    cutoff = (datetime.now(TIMEZONE) - timedelta(days=MAX_DAYS)).strftime("%Y-%m-%d")
    merged = merge_archive(existing, items, cutoff)

    if args.dry_run:
        print(f"dry run: {len(items)} new articles, archive would hold {len(merged)} items")
        for item in merged[:5]:
            print(f"  {item['published_at']}  {item['journal']}  {item['title'][:60]}")
        return 0

    write_archive(merged)
    print(f"saved {len(items)} new articles; archive now holds {len(merged)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

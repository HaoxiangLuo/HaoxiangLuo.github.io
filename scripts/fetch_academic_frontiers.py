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

The long-term archive is authoritative: each run files the articles it found
into `assets/data/archive/academic-frontiers/YYYY.jsonl` and only then lets
`scripts/archive_data.py` regenerate the short `_data/academic_frontiers.json`
index (the last 180 days) that Jekyll builds from.

A Chinese title (`title_zh`) and Chinese abstract (`abstract_excerpt_zh`) are
written beside the English wording, never over it: the translation makes the
page readable, the original keeps the paper findable. Translation is best
effort and budgeted per run — a field that cannot be filled stays empty and the
next run tries again.
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
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import archive_data
import model_client

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "_data" / "academic_frontiers_sources.yml"

ENDPOINT = "https://api.openalex.org/works"
USER_AGENT = "HaoxiangLuo.github.io academic-frontiers collector/1.0"

WINDOW_DAYS = 30          # only articles published in the last 30 days
MAX_PER_JOURNAL = 3
MAX_ITEMS = 24
# How much history the JSON archive keeps is decided by `archive_data`; this
# collector only ever hands records over to it.
ABSTRACT_LIMIT = 450
MAX_AUTHORS = 6
MAX_ISSN_PER_QUERY = 5    # OpenAlex accepts 50 OR values; stay well below it
MAX_ATTEMPTS = 4
REQUEST_TIMEOUT = 30
BACKOFF_BASE = 2.0
TIMEZONE = ZoneInfo("Asia/Shanghai")

# Translations are stored next to the original wording, never instead of it:
# a Chinese title is there to make the page readable, the English one to keep
# the article findable.
TRANSLATE_TIMEOUT = 25
MAX_TRANSLATE_CHARS = 700
MAX_CHUNK_CHARS = 180       # one request per sentence group, not per abstract
DEFAULT_TRANSLATIONS = 40
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
TITLE_PROMPT = (
    "Translate this paper title into Simplified Chinese. Keep every proper noun, "
    "journal concept and method name recognisable, and do not add punctuation of "
    "your own. Reply with the translation only."
)
ABSTRACT_PROMPT = (
    "Translate this academic abstract excerpt into Simplified Chinese. Keep the "
    "technical terms accurate and the tone academic. Reply with the translation only."
)


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


class ArticleTranslator:
    """Write the Chinese fields beside the original wording.

    A configured provider is used when there is one; otherwise the
    unauthenticated endpoint the other collectors already fall back on takes
    over, so the Chinese page is not left empty just because nobody set a key
    up. Either way the English title stays on the record: a translated title is
    for reading, the original one is for finding the paper again.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.public_calls = 0
        self.pending = 0
        self.public_unavailable = False

    def chinese(self, text: str, prompt: str) -> str:
        text = (text or "").strip()
        if not text or len(text) > MAX_TRANSLATE_CHARS:
            return ""
        pieces = split_sentences(text)
        if len(pieces) == 1:
            return self._request(pieces[0], prompt)
        # Long text is sent sentence group by sentence group: the unauthenticated
        # endpoint answers a short request completely, but echoes whole English
        # sentences back when the request is long.
        values = [self._request(piece, prompt, require_cjk=False) for piece in pieces]
        if not all(values):
            return ""
        joined = self._tidy(" ".join(values))
        # The same echo can still happen per group: a translation that contains
        # its own source sentence is worse than no translation at all, so the
        # field stays pending and the next run tries again.
        if echoes_source(text, joined):
            return ""
        return joined

    def _request(self, text: str, prompt: str, require_cjk: bool = True) -> str:
        if model_client.configured():
            try:
                self.calls += 1
                value = self._tidy(
                    model_client.chat(
                        [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": text},
                        ],
                        timeout=TRANSLATE_TIMEOUT,
                    ),
                    require_cjk,
                )
                if value:
                    return value
            except Exception as exc:  # noqa: BLE001 - provider failures of any kind
                print(f"warning: translation failed: {exc}", file=sys.stderr)
        if self.public_unavailable:
            return ""
        try:
            self.public_calls += 1
            value = self._tidy(model_client.public_translate(text, "zh"), require_cjk)
        except Exception as exc:  # noqa: BLE001 - network failures of any kind
            print(f"warning: public translation failed: {exc}", file=sys.stderr)
            self.public_unavailable = True
            return ""
        time.sleep(0.15)
        return value

    @staticmethod
    def _tidy(value: str, require_cjk: bool = True) -> str:
        text = re.sub(r"\s+", " ", value or "").strip()
        # A reply without one Chinese character is not a translation.
        if not text or len(text) > MAX_TRANSLATE_CHARS * 3:
            return ""
        if require_cjk and not CJK_RE.search(text):
            return ""
        return text


def echoes_source(source: str, translation: str) -> bool:
    """True when a "translation" still carries whole sentences of the source.

    The unauthenticated endpoint occasionally answers a long request with some
    sentences left in English. Such a value is not published: it is dropped so
    the next run translates it properly.
    """
    source = re.sub(r"\s+", " ", source or "").strip()
    translation = re.sub(r"\s+", " ", translation or "").strip()
    if len(source) < 40 or not translation:
        return False
    return any(
        len(piece) >= 40 and piece in translation for piece in split_sentences(source)
    )


def split_sentences(text: str) -> list[str]:
    """Group the text into requests of roughly `MAX_CHUNK_CHARS`, on boundaries."""
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    chunks: list[str] = []
    current = ""
    for part in re.split(r"(?<=[.!?;])\s+", text):
        part = part.strip()
        if not part:
            continue
        if current and len(current) + 1 + len(part) > MAX_CHUNK_CHARS:
            chunks.append(current)
            current = part
        else:
            current = f"{current} {part}".strip()
    if current:
        chunks.append(current)
    # One sentence longer than the limit: send it whole rather than cut it.
    return chunks or [text]


def translate_articles(
    records: list[dict], budget: int
) -> tuple[dict, ArticleTranslator, list[str]]:
    """Fill `title_zh` and `abstract_excerpt_zh` where they are still missing.

    The list is expected to be newest first, so a fresh article is translated
    before the backlog; whatever the budget leaves out stays pending and the
    next run picks it up. The ids of the records that changed are returned so
    the caller can write those and nothing else.
    """
    translator = ArticleTranslator()
    filled = {"titles": 0, "abstracts": 0, "dropped": 0}
    changed: list[str] = []
    for record in records:
        touched = False
        # A stored translation that kept whole English sentences is not one:
        # drop it so this run translates it again.
        if record.get("abstract_excerpt_zh") and echoes_source(
            str(record.get("abstract_excerpt") or ""), str(record["abstract_excerpt_zh"])
        ):
            record.pop("abstract_excerpt_zh")
            filled["dropped"] += 1
            touched = True
        if budget > 0 and not record.get("title_zh") and record.get("title"):
            value = translator.chinese(str(record["title"]), TITLE_PROMPT)
            if value:
                record["title_zh"] = value
                filled["titles"] += 1
                budget -= 1
                touched = True
        if budget > 0 and not record.get("abstract_excerpt_zh") and record.get("abstract_excerpt"):
            value = translator.chinese(str(record["abstract_excerpt"]), ABSTRACT_PROMPT)
            if value:
                record["abstract_excerpt_zh"] = value
                filled["abstracts"] += 1
                budget -= 1
                touched = True
        if touched and record.get("id"):
            changed.append(str(record["id"]))
        if budget <= 0:
            break
    translator.pending = sum(
        1
        for record in records
        if not record.get("title_zh") or not record.get("abstract_excerpt_zh")
    )
    return filled, translator, changed


def public_note(translator: ArticleTranslator) -> str:
    """Report how many fields came from the unauthenticated endpoint."""
    if not translator.public_calls:
        return ""
    return f" ({translator.public_calls} via the public endpoint)"


def translation_line(filled: dict, translator: ArticleTranslator) -> str:
    line = (
        f"translations: {filled['titles']} titles, {filled['abstracts']} abstracts filled; "
        f"{translator.pending} field(s) pending retry"
    )
    if filled.get("dropped"):
        line += f"; {filled['dropped']} echoed translation(s) dropped"
    return line + public_note(translator)


def newest_first(records: list[dict]) -> list[dict]:
    return sorted(records, key=lambda record: str(record.get("published_at") or ""), reverse=True)


def merge_history(history: list[dict], fresh: list[dict]) -> tuple[list[dict], set[str]]:
    """Overlay this run's finds on the archive and return the newest-first list.

    A stored article keeps its Chinese fields when it is collected again: the
    translation is only ever missing, never stale. The second return value is
    the set of ids this run brought in, which have to be written even when
    nothing was translated for them.
    """
    merged: dict[str, dict] = {}
    for index, record in enumerate(history):
        merged[str(record.get("id") or f"history-{index}")] = dict(record)
    fresh_ids: set[str] = set()
    for index, record in enumerate(fresh):
        key = str(record.get("id") or f"fresh-{index}")
        fresh_ids.add(key)
        stored = merged.get(key)
        if stored:
            # Fresh metadata wins, stored translations survive.
            carried = {name: value for name, value in stored.items() if name.endswith("_zh")}
            merged[key] = {**record, **carried}
        else:
            merged[key] = dict(record)
    return newest_first(list(merged.values())), fresh_ids


def backfill_history(existing: list[dict], budget: int, dry_run: bool) -> int:
    """Translate what the archive is still missing, newest article first."""
    filled, translator, changed = translate_articles(newest_first(existing), budget)
    print(translation_line(filled, translator))
    if dry_run:
        print("dry run: archive not written")
        return 0
    if not changed:
        print("nothing left to translate; archive left unchanged")
        return 0
    updated = [record for record in existing if str(record.get("id")) in set(changed)]
    stats = archive_data.upsert(ROOT, "academic_frontiers", updated)
    print(f"saved {len(updated)} translated article(s); {stats.as_line()}")
    return 0


def load_archive() -> list[dict]:
    """Every article the long-term archive already holds."""
    records, invalid = archive_data.read_archive(ROOT, "academic_frontiers")
    if invalid:
        print(f"warning: skipped {invalid} unreadable archive line(s)", file=sys.stderr)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=SOURCES, help="override the journal shortlist (for tests)")
    parser.add_argument("--dry-run", action="store_true", help="collect and report without writing the archive")
    parser.add_argument(
        "--translate-only",
        action="store_true",
        help="fill in the missing Chinese fields of stored articles without collecting anything",
    )
    parser.add_argument(
        "--max-translations",
        type=int,
        default=DEFAULT_TRANSLATIONS,
        help=f"how many text fields one run may translate (default {DEFAULT_TRANSLATIONS})",
    )
    args = parser.parse_args()

    if not args.dry_run and not model_client.configured():
        print(
            "note: no translation provider configured (set TRANSLATE_BASE_URL and "
            "TRANSLATE_API_KEY); fields are filled through the public endpoint",
            file=sys.stderr,
        )

    if not args.sources.exists():
        print(f"error: journal shortlist is missing: {args.sources}", file=sys.stderr)
        return 1

    sources = active_sources(parse_sources(args.sources))
    existing = load_archive()

    if args.translate_only:
        return backfill_history(existing, args.max_translations, args.dry_run)

    if not sources:
        # A broad OpenAlex search would be the wrong answer here: without a
        # whitelist there is nothing to filter on, so keep the archive intact.
        print("error: no active journals in the shortlist; not contacting OpenAlex", file=sys.stderr)
        if not existing:
            if args.dry_run:
                print("dry run: would write an empty archive")
            else:
                stats = archive_data.upsert(ROOT, "academic_frontiers", [])
                print(f"wrote an empty archive; {stats.as_line()}")
        return 0

    since = (datetime.now(TIMEZONE) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    issns = [entry["issn_l"] for entry in sources]

    try:
        works = fetch_works(issns, since)
    except Exception as exc:  # noqa: BLE001 - keep the archive on failure
        print(f"error: OpenAlex collection failed: {exc}", file=sys.stderr)
        print(f"error: keeping the existing archive ({len(existing)} items)", file=sys.stderr)
        return 0

    items = select_items(works, sources)
    if not items:
        print(f"no new articles since {since}; keeping the existing archive ({len(existing)} items)")
        # Nothing new to file, but the backlog can still be translated.
        return backfill_history(existing, args.max_translations, args.dry_run)

    records = [record for record in (archive_data.normalize("academic_frontiers", item) for item in items) if record]

    if args.dry_run:
        print(f"dry run: {len(records)} collected articles; archive holds {len(existing)} items")
        for record in records[:5]:
            print(f"  {record['published_at']}  {record['journal']}  {record['title'][:60]}")
        return 0

    # Newest first: this run's finds are translated before the backlog, and an
    # article whose translation failed last time is retried on a later run.
    merged, fresh_ids = merge_history(existing, records)
    filled, translator, changed = translate_articles(merged, args.max_translations)
    print(translation_line(filled, translator))
    write_ids = fresh_ids | set(changed)
    to_write = [record for record in merged if str(record.get("id")) in write_ids]

    # Archive first: the recent index is only ever generated from it.
    stats = archive_data.upsert(ROOT, "academic_frontiers", to_write)
    print(f"saved {len(records)} collected articles; {stats.as_line()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

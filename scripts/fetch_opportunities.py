#!/usr/bin/env python3
"""Collect internship and academic-mobility opportunities for the "Opportunities" page.

Two sections are maintained in `_data/opportunities.json`:

* `internships` — internships at the United Nations and well-known global
  companies, read from their official job feeds (Taleo RSS, Greenhouse board
  APIs, Amazon's public search endpoint).
* `academia` — PhD exchange, visiting-scholar and joint-training
  announcements from journalism/communication departments at QS top-50
  universities, extracted from official department pages.

Only items that have never been collected before are appended under today's
date. When nothing new is found the archive file is left untouched, so the
daily workflow can skip the commit entirely.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # Fallback for hosts without the IANA tz database.
    TZ = timezone(timedelta(hours=8))

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "_data" / "opportunities.json"
MAX_DAYS = 180
MAX_NEW_PER_SOURCE = 8
MAX_NEW_PER_DAY = 20
REQUEST_TIMEOUT = 25
USER_AGENT = "HaoxiangLuo.github.io opportunities collector/1.0"

# --- Translation -----------------------------------------------------------
# Same approach as scripts/fetch_daily_news.py (GitHub Models, OpenAI-compatible
# endpoint, GITHUB_TOKEN from the workflow) but packaged for the Opportunities
# record shape: two plain-text fields per item instead of a single headline.
# There is deliberately no unauthenticated public translate endpoint as a
# silent fallback: when GitHub Models is unreachable the field simply stays
# pending and the next scheduled run fills it in.
TRANSLATE_TIMEOUT = 20
MODELS_ENDPOINT = "https://models.github.ai/inference/chat/completions"
MODELS_MODEL = "openai/gpt-4o-mini"
MAX_TRANSLATIONS_PER_RUN = 40  # text fields per run, history first
MAX_SOURCE_CHARS = 240  # refuse to send anything longer to the model
MAX_TRANSLATION_CHARS = 240  # refuse a reply that rambles or explains
TRANSLATE_ATTEMPTS = 2  # bounded retries for one field
CJK_RE = re.compile(r"[\u3400-\u9fff]")
# URLs, HTML and workflow variables never reach the model.
UNSAFE_TEXT_RE = re.compile(r"https?://|<[a-z!/]|[{][{]", re.I)

# Internship sources: official job feeds of the UN and leading global companies.
# `group` splits the archive into the UN and company sub-sections.
INTERN_SOURCES = [
    {"name": "UNICEF", "name_zh": "联合国儿童基金会", "kind": "taleo_rss", "value": "https://jobs.unicef.org/cw/en/rss", "group": "un"},
    {"name": "UN Women", "name_zh": "联合国妇女署", "kind": "taleo_rss", "value": "https://careers.unwomen.org/cw/en/rss", "group": "un"},
    {"name": "Amazon", "name_zh": "亚马逊", "kind": "amazon_json", "value": "https://www.amazon.jobs/en/search.json?result_limit=30&base_query=intern", "group": "company"},
    {"name": "Airbnb", "name_zh": "爱彼迎", "kind": "greenhouse", "value": "airbnb", "group": "company"},
    {"name": "Stripe", "name_zh": "Stripe", "kind": "greenhouse", "value": "stripe", "group": "company"},
    {"name": "Anthropic", "name_zh": "Anthropic", "kind": "greenhouse", "value": "anthropic", "group": "company"},
    {"name": "Cloudflare", "name_zh": "Cloudflare", "kind": "greenhouse", "value": "cloudflare", "group": "company"},
]

# Academic sources: official pages of journalism/communication departments at
# QS top-50 universities where exchange, visiting and joint programmes appear.
ACADEMIA_SOURCES = [
    {"name": "Reuters Institute, University of Oxford", "name_zh": "牛津大学路透新闻研究院", "url": "https://reutersinstitute.politics.ox.ac.uk/fellowships"},
    {"name": "POLIS, University of Cambridge", "name_zh": "剑桥大学政治与国际研究系", "url": "https://www.polis.cam.ac.uk/news"},
    {"name": "Shorenstein Center, Harvard University", "name_zh": "哈佛大学肖伦斯坦中心", "url": "https://shorensteincenter.org/fellowships/"},
    {"name": "NYU, Arthur L. Carter Journalism Institute", "name_zh": "纽约大学新闻学院", "url": "https://journalism.nyu.edu/news/"},
    {"name": "Stanford University, Department of Communication", "name_zh": "斯坦福大学传播系", "url": "https://comm.stanford.edu/"},
    {"name": "USC Annenberg School for Communication and Journalism", "name_zh": "南加州大学安纳伯格传播学院", "url": "https://annenberg.usc.edu/news"},
    {"name": "HKU, Journalism and Media Studies Centre", "name_zh": "香港大学新闻及传媒研究中心", "url": "https://jmsc.hku.hk/news/"},
    {"name": "UW-Madison, Department of Communication Arts", "name_zh": "威斯康星大学麦迪逊分校传播艺术系", "url": "https://commarts.wisc.edu/news/"},
    {"name": "NTU, Wee Kim Wee School of Communication and Information", "name_zh": "南洋理工大学黄金辉传播与信息学院", "url": "https://www.wkwsci.ntu.edu.sg/News-and-Events/"},
]

# \b prevents "International" / "Internal" from matching.
INTERN_RE = re.compile(r"\bintern(ship)?s?\b", re.I)
# Exchange, visiting, joint-training and fellowship vocabulary for academia.
ACADEMIA_RE = re.compile(
    r"visiting|exchange|joint|dual|double[- ]degree|fellowship|studentship"
    r"|research stay|secondment|mobility|联合培养|访学|交换",
    re.I,
)
ANCHOR_RE = re.compile(r'<a\s[^>]*href="([^"\s>]+)"[^>]*>(.*?)</a>', re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return re.sub(r"\s+", " ", value).strip()


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return response.read()


def normalise_url(url: str, base: str | None = None) -> str:
    url = urljoin(base, url.strip()) if base else url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return url


def item_key(item: dict) -> str:
    url = re.sub(r"[#?].*$", "", item["url"].rstrip("/").lower())
    title = re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", item["title"].lower())
    return url or title


SYSTEM_PROMPTS = {
    "zh": (
        "You translate English job titles, academic programme titles and short "
        "location or supplementary lines taken from official internship and "
        "academic-mobility announcements into concise Simplified Chinese. Keep "
        "organisations, universities, companies, programme abbreviations, job "
        "levels, numbers, deadlines and place names exactly as they are. Do not "
        "add any information that the source does not contain. Reply with the "
        "translation only: no quotes, no pinyin, no explanation."
    ),
    "en": (
        "You translate Chinese job titles, academic programme titles and short "
        "location or supplementary lines into concise English. Keep "
        "organisations, universities, companies, programme abbreviations, job "
        "levels, numbers, deadlines and place names exactly as they are. Do not "
        "add any information that the source does not contain. Reply with the "
        "translation only."
    ),
}


def tidy_translation(value: str, target: str) -> str:
    """Normalise a model reply, or return "" when it is not usable.

    Empty, over-long, URL-bearing and wrong-script replies are rejected so the
    field is left for the next run instead of being filled with noise.
    """
    text = clean_text(value)
    text = text.strip().strip('"').strip("“”‘’").strip()
    text = re.sub(
        r"^(翻译|译文|简体中文|英译|Chinese translation|Chinese|English|Translation)\s*[:：]\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) > MAX_TRANSLATION_CHARS:
        return ""
    if UNSAFE_TEXT_RE.search(text):
        return ""
    has_cjk = bool(CJK_RE.search(text))
    if target == "zh" and not has_cjk:
        return ""
    if target == "en" and has_cjk:
        return ""
    return text


def _snippet(raw: bytes | str, limit: int = 200) -> str:
    """A short printable excerpt of an unexpected reply, for the warning line."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    text = text.replace("\n", " ").replace("\r", " ").strip()
    return repr(text[:limit])


class Translator:
    """A tiny field-level translator with a per-run cache.

    Only plain text is sent. Identical text is translated once per run, so a
    repeated job title across sources costs one request.
    """

    def __init__(self, token: str = "") -> None:
        self.token = token
        self.cache: dict[tuple[str, str], str] = {}
        self.calls = 0
        self.pending = 0
        # Set once the endpoint has refused us twice in a row: the rest of the
        # run then stays offline instead of spending a request per field.
        self.unavailable = ""
        self._diagnosed = False

    @staticmethod
    def translatable(text: str) -> bool:
        if not text or len(text) > MAX_SOURCE_CHARS:
            return False
        return not UNSAFE_TEXT_RE.search(text)

    def translate(self, text: str, target: str) -> str:
        """Return the translation of `text`, or "" to leave the field pending."""
        key = (target, text)
        if key in self.cache:
            return self.cache[key]
        value = ""
        if self.token and self.translatable(text) and not self.unavailable:
            failures = 0
            for _ in range(TRANSLATE_ATTEMPTS):
                try:
                    self.calls += 1
                    value = tidy_translation(self._request(text, target), target)
                    time.sleep(0.15)
                except Exception as exc:
                    print(f"warning: translation failed: {exc}", file=sys.stderr)
                    self._diagnose()
                    failures += 1
                    value = ""
                if value:
                    break
            if not value and failures:
                self.unavailable = "endpoint refused the request; skipping the rest of this run"
        if not value:
            self.pending += 1
        self.cache[key] = value
        return value

    def _request(self, text: str, target: str) -> str:
        payload = json.dumps(
            {
                "model": MODELS_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPTS[target]},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.2,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            MODELS_ENDPOINT,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TRANSLATE_TIMEOUT) as response:
                status = getattr(response, "status", None)
                raw = response.read()
        except urllib.error.HTTPError as exc:
            # The body of an error reply is the only place that says why the
            # token or the endpoint was refused, so it goes into the warning.
            raise RuntimeError(
                f"models endpoint returned HTTP {exc.code} ({exc.reason}): "
                f"{_snippet(exc.read())}"
            ) from exc
        try:
            body = json.loads(raw.decode("utf-8", "replace"))
        except ValueError as exc:
            raise RuntimeError(
                f"models endpoint replied HTTP {status} with a non-JSON body: {_snippet(raw)}"
            ) from exc
        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"models endpoint replied without a choice: {_snippet(raw)}") from exc


    def _diagnose(self) -> None:
        """Print, once per run, why the endpoint may be unreachable.

        A plain "OK" body means something between us and GitHub Models answers
        instead of the inference API, so the run records the host resolution
        and the proxy environment next to the failure.
        """
        if self._diagnosed:
            return
        self._diagnosed = True
        try:
            address = socket.gethostbyname("models.github.ai")
        except Exception as exc:  # noqa: BLE001
            address = f"dns failed: {exc}"
        proxies = {
            name: os.environ[name]
            for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")
            if os.environ.get(name)
        }
        print(
            f"warning: models probe models.github.ai -> {address}; proxy env {proxies or 'none'}",
            file=sys.stderr,
        )
        request = urllib.request.Request(
            "https://models.github.ai/catalog/models",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TRANSLATE_TIMEOUT) as response:
                print(
                    f"warning: models catalog probe HTTP {response.status}: "
                    f"{_snippet(response.read(), 120)}",
                    file=sys.stderr,
                )
        except urllib.error.HTTPError as exc:
            print(
                f"warning: models catalog probe HTTP {exc.code}: {_snippet(exc.read(), 120)}",
                file=sys.stderr,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"warning: models catalog probe failed: {exc}", file=sys.stderr)


def build_translator() -> Translator:
    """Build the translator from the token GitHub Actions provides."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_MODELS_TOKEN") or ""
    if not token:
        print(
            "note: no GITHUB_TOKEN in the environment; translations stay pending for the next run",
            file=sys.stderr,
        )
    return Translator(token)


# (source field, Chinese target, English target): `title_en` / `detail_en` are
# reserved for Chinese-language sources that may be collected later.
TRANSLATION_FIELDS = (
    ("title", "title_zh", "title_en"),
    ("detail", "detail_zh", "detail_en"),
)


def pending_field(item: dict, source_key: str, zh_key: str, en_key: str):
    """Describe the field that still needs a translation, or None."""
    text = str(item.get(source_key) or "").strip()
    if not text:
        return None
    if CJK_RE.search(text):  # a Chinese source: the English page needs it
        return None if item.get(en_key) else (text, en_key, "en")
    return None if item.get(zh_key) else (text, zh_key, "zh")


def backfill_translations(sections: dict, translator: Translator, budget: int = MAX_TRANSLATIONS_PER_RUN) -> dict:
    """Fill missing translations, newest day first, within `budget` fields.

    Existing translations are never overwritten, and one failed field never
    touches the record it belongs to: the item keeps its publisher wording and
    the Chinese page falls back to it.
    """
    filled = {"titles": 0, "details": 0}
    for name in ("internships", "academia"):
        for day in sections.get(name) or []:
            for item in day.get("items", []):
                for source_key, zh_key, en_key in TRANSLATION_FIELDS:
                    if filled["titles"] + filled["details"] >= budget:
                        return filled
                    job = pending_field(item, source_key, zh_key, en_key)
                    if job is None:
                        continue
                    text, target_key, target = job
                    translated = translator.translate(text, target)
                    if not translated:
                        continue
                    item[target_key] = translated
                    filled["titles" if source_key == "title" else "details"] += 1
    return filled


# Long-term archive hook: `opportunities` is not one of the three datasets in
# scripts/archive_data.py yet (those are daily_news, academic_frontiers and
# site_updates), so `_data/opportunities.json` is still the only storage and
# this file is written directly. When Opportunities joins the three-layer
# archive, replace write_archive() below with
# `archive_data.upsert(ROOT, "opportunities", records)` exactly as
# scripts/fetch_daily_news.py does: the translations then live in the JSONL
# partitions and are re-projected into the recent index, and nothing in the
# record shape has to change.
def write_archive(archive: dict) -> None:
    """Replace the archive atomically: write a temp file, parse it, then swap."""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(archive, ensure_ascii=False, indent=2) + "\n"
    temporary = OUTPUT.with_name(OUTPUT.name + ".tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        json.loads(temporary.read_text(encoding="utf-8"))
        os.replace(temporary, OUTPUT)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def collect_taleo_rss(source: dict) -> list[dict]:
    root = ET.fromstring(fetch(source["value"]))
    results = []
    for entry in root.findall(".//item"):
        title = clean_text(entry.findtext("title", ""))
        link = normalise_url(clean_text(entry.findtext("link", "")))
        if title and link and INTERN_RE.search(title):
            results.append({"title": title, "url": link})
            if len(results) >= MAX_NEW_PER_SOURCE:
                break
    return results


def collect_greenhouse(source: dict) -> list[dict]:
    payload = json.loads(fetch(f"https://boards-api.greenhouse.io/v1/boards/{source['value']}/jobs"))
    results = []
    for job in payload.get("jobs", []):
        title = clean_text(job.get("title", ""))
        link = normalise_url(job.get("absolute_url", ""))
        location = clean_text((job.get("location") or {}).get("name", ""))
        if title and link and INTERN_RE.search(title):
            entry = {"title": title, "url": link}
            if location and location.lower() not in title.lower():
                entry["detail"] = location
            results.append(entry)
            if len(results) >= MAX_NEW_PER_SOURCE:
                break
    return results


def collect_amazon(source: dict) -> list[dict]:
    payload = json.loads(fetch(source["value"]))
    results = []
    for job in payload.get("jobs", []):
        title = clean_text(job.get("title", ""))
        link = normalise_url("https://www.amazon.jobs" + (job.get("job_path") or ""))
        location = clean_text(job.get("normalized_location") or job.get("company_name") or "")
        if title and link and INTERN_RE.search(title):
            entry = {"title": title, "url": link}
            if location and location.lower() not in title.lower():
                entry["detail"] = location
            results.append(entry)
            if len(results) >= MAX_NEW_PER_SOURCE:
                break
    return results


def collect_academia(source: dict) -> list[dict]:
    page = fetch(source["url"]).decode("utf-8", "ignore")
    results = []
    seen_titles: set[str] = set()
    for match in ANCHOR_RE.finditer(page):
        href = match.group(1)
        text = clean_text(TAG_RE.sub(" ", match.group(2)))
        if not (12 <= len(text) <= 160) or not ACADEMIA_RE.search(text):
            continue
        link = normalise_url(href, source["url"])
        if not link:
            continue
        key = re.sub(r"[^a-z0-9]+", "", text.lower())
        if key in seen_titles:
            continue
        seen_titles.add(key)
        results.append({"title": text, "url": link})
        if len(results) >= MAX_NEW_PER_SOURCE:
            break
    return results


COLLECTORS = {
    "taleo_rss": collect_taleo_rss,
    "greenhouse": collect_greenhouse,
    "amazon_json": collect_amazon,
}


def gather(section_sources: list[dict], collector) -> list[dict]:
    """Fetch every source and interleave their candidate items."""
    groups: list[list[dict]] = []
    for source in section_sources:
        try:
            candidates = collector(source)
            for candidate in candidates:
                candidate["source"] = source["name"]
                candidate["source_zh"] = source["name_zh"]
                candidate["group"] = source.get("group", "company")
            groups.append(candidates)
        except Exception as exc:
            print(f"warning: {source['name']}: {exc}", file=sys.stderr)
    merged: list[dict] = []
    for index in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if index < len(group) and len(merged) < MAX_NEW_PER_DAY:
                merged.append(group[index])
    return merged


def archive_keys(days: list[dict]) -> set[str]:
    keys = set()
    for day in days:
        for item in day.get("items", []):
            keys.add(item_key(item))
    return keys


def normalise_days(days: list[dict]) -> list[dict]:
    """Repair an archive in place: one entry per date, no repeated items.

    The archive is the only storage this page has, so it is normalised before
    anything is added rather than trusted: two runs that land on the same date
    (a retry after a push race, say) would otherwise leave two entries for one
    day, and repeated items would survive inside a single day.
    """
    merged: dict[str, dict] = {}
    order: list[str] = []
    for day in days or []:
        date = day.get("date")
        if not date:
            continue
        bucket = merged.setdefault(date, {"date": date, "items": []})
        if date not in order:
            order.append(date)
        seen = {item_key(item) for item in bucket["items"]}
        for item in day.get("items", []):
            key = item_key(item)
            if key in seen:
                continue
            seen.add(key)
            bucket["items"].append(item)
    normalised = [merged[date] for date in order]
    normalised.sort(key=lambda day: day["date"], reverse=True)
    return normalised


def append_new(days: list[dict], candidates: list[dict], today: str) -> int:
    known = archive_keys(days)
    fresh: list[dict] = []
    for candidate in candidates:
        if item_key(candidate) in known:
            continue
        known.add(item_key(candidate))
        fresh.append(candidate)
    if not fresh:
        return 0
    for day in days:
        if day.get("date") == today:
            existing = archive_keys([day])
            fresh_today = [item for item in fresh if item_key(item) not in existing]
            day["items"].extend(fresh_today)
            return len(fresh_today)
    days.insert(0, {"date": today, "items": fresh})
    days.sort(key=lambda day: day.get("date", ""), reverse=True)
    del days[MAX_DAYS:]
    return len(fresh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Collect and report without writing the archive.")
    parser.add_argument(
        "--translate-only",
        action="store_true",
        help="Fill in missing translations of stored items without collecting anything.",
    )
    parser.add_argument(
        "--max-translations",
        type=int,
        default=MAX_TRANSLATIONS_PER_RUN,
        help=f"How many text fields one run may translate (default {MAX_TRANSLATIONS_PER_RUN}).",
    )
    args = parser.parse_args(argv)

    raw = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    sections = {
        "internships": raw.get("internships") if isinstance(raw.get("internships"), list) else [],
        "academia": raw.get("academia") if isinstance(raw.get("academia"), list) else [],
    }
    normalised = {name: normalise_days(days) for name, days in sections.items()}
    # A copy, not the same list: append_new edits in place, so the "did
    # normalising repair anything" comparison needs the pre-normalised state.
    before = {name: copy.deepcopy(value) for name, value in normalised.items()}
    sections.update(normalised)

    translator = build_translator()

    def fill(budget: int) -> dict:
        """Translate within a budget; a failure here must never lose an item."""
        try:
            return backfill_translations(sections, translator, budget)
        except Exception as exc:
            print(f"warning: translation backfill aborted: {exc}", file=sys.stderr)
            return {"titles": 0, "details": 0}

    # History first: an older item whose translation failed last time gets
    # another chance before today's new items are translated.
    history = fill(args.max_translations)

    if args.translate_only:
        print(
            f"translations: {history['titles']} titles, {history['details']} details filled; "
            f"{translator.pending} field(s) pending retry"
        )
        if args.dry_run:
            print("dry run: archive not written")
            return 0
        if not (history["titles"] or history["details"]):
            print("nothing left to translate; archive left unchanged")
            return 0
        write_archive(
            {
                "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
                "internships": sections["internships"][:MAX_DAYS],
                "academia": sections["academia"][:MAX_DAYS],
            }
        )
        print(f"saved {history['titles']} titles and {history['details']} details without collecting")
        return 0

    today = datetime.now(TZ).strftime("%Y-%m-%d")

    intern_candidates = gather(INTERN_SOURCES, lambda s: COLLECTORS[s["kind"]](s))
    academia_candidates = gather(ACADEMIA_SOURCES, collect_academia)

    added_intern = append_new(sections["internships"], intern_candidates, today)
    added_academia = append_new(sections["academia"], academia_candidates, today)

    print(f"candidates: {len(intern_candidates)} internships, {len(academia_candidates)} academia")
    print(f"new items: internships={added_intern}, academia={added_academia}")

    # Whatever is left of the budget goes to the items just collected.
    remaining = max(args.max_translations - history["titles"] - history["details"], 0)
    fresh = fill(remaining) if remaining else {"titles": 0, "details": 0}
    titles = history["titles"] + fresh["titles"]
    details = history["details"] + fresh["details"]
    print(
        f"translations: {titles} titles, {details} details filled; "
        f"{translator.pending} field(s) pending retry"
    )

    if args.dry_run:
        stored_intern = sum(len(day["items"]) for day in sections["internships"])
        stored_academia = sum(len(day["items"]) for day in sections["academia"])
        print(
            f"dry run: archive not written "
            f"(would hold {len(sections['internships'])} internship days / {stored_intern} items, "
            f"{len(sections['academia'])} academia days / {stored_academia} items)"
        )
        return 0

    # Nothing new is the normal case: the archive already holds these items and
    # stays exactly as it was. It is only rewritten when the day added
    # something, when normalising repaired a duplicate date or item, or when a
    # translation was filled in.
    repaired = any(before[name] != sections[name] for name in before)
    if added_intern == 0 and added_academia == 0 and not repaired and not (fresh["titles"] or fresh["details"]):
        print("nothing new to record; archive left unchanged")
        return 0

    archive = {
        "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "internships": sections["internships"][:MAX_DAYS],
        "academia": sections["academia"][:MAX_DAYS],
    }
    write_archive(archive)
    stored_intern = sum(len(day["items"]) for day in archive["internships"])
    stored_academia = sum(len(day["items"]) for day in archive["academia"])
    print(f"saved {added_intern} internships and {added_academia} academia items for {today}")
    print(
        f"archive now holds {len(archive['internships'])} internship days / {stored_intern} items, "
        f"{len(archive['academia'])} academia days / {stored_academia} items"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Collect a compact, date-keyed world-news index from public RSS feeds.

Every headline is stored twice: `title` keeps the publisher's original wording
and `title_zh` holds a Simplified Chinese rendering so the two language
versions of the site can show the same story in their own language.

The long-term archive is authoritative: each run files the day it collected into
`assets/data/archive/daily-news/YYYY-MM.jsonl` and only then lets
`scripts/archive_data.py` regenerate the short `_data/daily_news.json` index
that Jekyll builds from. Nothing is trimmed out of history here.
"""

from __future__ import annotations

import html
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

import archive_data
import model_client

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
    ("UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
)
MAX_PER_DAY = 9

TRANSLATE_TIMEOUT = 20
GTX_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
MAX_TRANSLATIONS_PER_RUN = 60
CJK_RE = re.compile(r"[\u3400-\u9fff]")


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return re.sub(r"\s+", " ", value).strip()


def read_feed(source: str, url: str) -> list[dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "HaoxiangLuo.github.io daily-news collector/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read())

    results: list[dict[str, str]] = []
    for item in root.findall(".//item")[:8]:
        title = clean_text(item.findtext("title", ""))
        link = clean_text(item.findtext("link", ""))
        if title and urlparse(link).scheme in {"http", "https"}:
            results.append({"title": title, "source": source, "url": link})
    return results


def interleave(groups: list[list[dict[str, str]]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for index in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if index >= len(group):
                continue
            item = group[index]
            key = re.sub(r"[^a-z0-9]+", "", item["title"].lower())
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
            if len(merged) == MAX_PER_DAY:
                return merged
    return merged


def tidy_translation(value: str) -> str:
    """Normalise a raw model/engine reply into a single clean headline."""
    text = clean_text(value)
    text = text.strip().strip('"').strip("“”").strip()
    text = re.sub(r"^(翻译|译文|Chinese|简体中文)\s*[:：]\s*", "", text)
    if not text or not CJK_RE.search(text):
        return ""
    if len(text) > 220:
        return ""
    return text


def translate_via_models(text: str, token: str) -> str:
    return model_client.chat(
        [
            {
                "role": "system",
                "content": (
                    "You translate English news headlines into concise Simplified "
                    "Chinese as used in mainland China. Keep proper nouns, place "
                    "names and numbers accurate. Reply with the translation only: "
                    "no quotes, no pinyin, no explanation."
                ),
            },
            {"role": "user", "content": text},
        ],
        timeout=TRANSLATE_TIMEOUT,
    )


def translate_via_gtx(text: str) -> str:
    query = urllib.parse.urlencode(
        {"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text}
    )
    request = urllib.request.Request(
        f"{GTX_ENDPOINT}?{query}",
        headers={"User-Agent": "HaoxiangLuo.github.io daily-news translator/1.0"},
    )
    with urllib.request.urlopen(request, timeout=TRANSLATE_TIMEOUT) as response:
        body = json.loads(response.read().decode("utf-8"))
    segments = body[0] if body else []
    return "".join(segment[0] for segment in segments if segment and segment[0])


def build_translator():
    """Return a callable that maps an English headline to Chinese (or "")."""
    token = model_client.api_key()
    # The original provider (GitHub Models) was retired on 2026-07-30, so a bare
    # GITHUB_TOKEN is not a provider any more; without one the unauthenticated
    # endpoint below stays the only source, exactly as before.
    enabled = model_client.configured()

    def translate(text: str) -> str:
        if token and enabled:
            try:
                result = tidy_translation(translate_via_models(text, token))
                if result:
                    return result
            except Exception as exc:
                print(f"warning: github models translation failed: {exc}", file=sys.stderr)
        try:
            return tidy_translation(translate_via_gtx(text))
        except Exception as exc:
            print(f"warning: translate endpoint failed: {exc}", file=sys.stderr)
        return ""

    return translate


def backfill_translations(days: list[dict], translate) -> int:
    """Fill in `title_zh` for every archived headline that still lacks one."""
    cache: dict[str, str] = {}
    filled = 0
    for day in days:
        for item in day.get("items", []):
            title = item.get("title")
            if not title or item.get("title_zh"):
                continue
            if filled >= MAX_TRANSLATIONS_PER_RUN:
                return filled
            if title in cache:
                chinese = cache[title]
            else:
                chinese = translate(title)
                cache[title] = chinese
                time.sleep(0.15)
            if chinese:
                item["title_zh"] = chinese
                filled += 1
    return filled


def archived_days() -> list[dict]:
    """Every day the long-term archive holds, newest first."""
    records, invalid = archive_data.read_archive(ROOT, "daily_news")
    if invalid:
        print(f"warning: skipped {invalid} unreadable archive line(s)", file=sys.stderr)
    return sorted(records, key=lambda record: record.get("date", ""), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--translate-only",
        action="store_true",
        help="Skip feed collection and only fill in missing Chinese titles.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="collect and report without writing the archive or the index",
    )
    args = parser.parse_args()

    days = archived_days()

    if args.translate_only:
        filled = backfill_translations(days, build_translator())
        if args.dry_run:
            print(f"dry run: {filled} headlines would be translated")
            return 0
        stats = archive_data.upsert(ROOT, "daily_news", days)
        print(f"translated {filled} headlines; {stats.as_line()}")
        return 0

    groups: list[list[dict[str, str]]] = []
    for source, url in SOURCES:
        try:
            groups.append(read_feed(source, url))
        except Exception as exc:  # Keep the digest available if one publisher is down.
            print(f"warning: {source}: {exc}", file=sys.stderr)

    items = interleave(groups)
    if not items:
        print("error: no news items were collected", file=sys.stderr)
        return 1

    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    record = archive_data.normalize_daily_news({"date": today, "items": items})

    if args.dry_run:
        print(f"dry run: {len(items)} headlines for {today}; archive holds {len(days)} days")
        return 0

    # Archive first: the recent index is only ever generated from it.
    stats = archive_data.upsert(ROOT, "daily_news", [record])

    translated = archived_days()
    filled = backfill_translations(translated, build_translator())
    if filled:
        # Translations are part of the record, so they go straight back in.
        stats = archive_data.upsert(ROOT, "daily_news", translated)
    print(f"saved {len(items)} headlines for {today}; translated {filled} headlines; {stats.as_line()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

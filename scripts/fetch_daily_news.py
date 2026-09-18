#!/usr/bin/env python3
"""Collect a compact, date-keyed world-news index from public RSS feeds.

Every headline is stored twice: `title` keeps the publisher's original wording
and `title_zh` holds a Simplified Chinese rendering so the two language
versions of the site can show the same story in their own language.
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


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "_data" / "daily_news.json"
SOURCES = (
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("NPR World", "https://feeds.npr.org/1004/rss.xml"),
    ("UN News", "https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
)
MAX_PER_DAY = 9
MAX_DAYS = 90

TRANSLATE_TIMEOUT = 20
GTX_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
MODELS_ENDPOINT = "https://models.github.ai/inference/chat/completions"
MODELS_MODEL = "openai/gpt-4o-mini"
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
    payload = json.dumps(
        {
            "model": MODELS_MODEL,
            "messages": [
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
            "temperature": 0.2,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        MODELS_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=TRANSLATE_TIMEOUT) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


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
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_MODELS_TOKEN")

    def translate(text: str) -> str:
        if token:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--migrate-only", action="store_true")
    parser.add_argument("--migrate-from", type=Path)
    parser.add_argument(
        "--translate-only",
        action="store_true",
        help="Skip feed collection and only fill in missing Chinese titles.",
    )
    args = parser.parse_args()

    source_file = args.migrate_from or OUTPUT
    raw_archive = json.loads(source_file.read_text(encoding="utf-8")) if source_file.exists() else {}
    if isinstance(raw_archive, dict) and isinstance(raw_archive.get("days"), list):
        days = raw_archive["days"]
    elif isinstance(raw_archive, dict):
        # Migrate the original date-keyed object without losing its history.
        days = [
            {"date": date, "items": entries}
            for date, entries in raw_archive.items()
            if isinstance(entries, list)
        ]
    else:
        days = []

    if args.migrate_only:
        archive = {
            "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
            "days": sorted(days, key=lambda day: day.get("date", ""), reverse=True)[:MAX_DAYS],
        }
        OUTPUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"migrated {len(archive['days'])} archived days")
        return 0

    if args.translate_only:
        filled = backfill_translations(days, build_translator())
        archive = {
            "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
            "days": days,
        }
        OUTPUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"translated {filled} headlines")
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
    days = [day for day in days if day.get("date") != today]
    days.append({"date": today, "items": items})
    days = sorted(days, key=lambda day: day.get("date", ""), reverse=True)[:MAX_DAYS]

    filled = backfill_translations(days, build_translator())

    archive = {
        "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "days": days,
    }
    OUTPUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved {len(items)} headlines for {today}; translated {filled} headlines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Collect a compact, date-keyed world-news index from public RSS feeds."""

from __future__ import annotations

import html
import argparse
import json
import re
import sys
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--migrate-only", action="store_true")
    args = parser.parse_args()

    raw_archive = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
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
    archive = {
        "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "days": days,
    }
    OUTPUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved {len(items)} headlines for {today}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

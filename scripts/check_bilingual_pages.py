#!/usr/bin/env python3
"""Check reciprocal language routes for every public bilingual page."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAIRS = (
    ("_pages/about.md", "_pages/about-zh.md", "/", "/zh/"),
    ("_pages/publications.html", "_pages/publications-zh.html", "/publications/", "/zh/publications/"),
    ("_pages/year-archive.html", "_pages/study-notes-zh.html", "/study-notes/", "/zh/study-notes/"),
    ("_pages/site-log.html", "_pages/site-log-zh.html", "/site-log/", "/zh/site-log/"),
    ("_pages/daily-news.html", "_pages/daily-news-zh.html", "/daily-news/", "/zh/daily-news/"),
)


def front_matter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing front matter")
    block = text.split("---", 2)[1]
    values: dict[str, str] = {}
    for line in block.splitlines():
        match = re.match(r"^([a-z_]+):\s*[\"']?([^\"']*)[\"']?\s*$", line)
        if match:
            values[match.group(1)] = match.group(2).strip()
    return values


def main() -> int:
    errors: list[str] = []
    for en_name, zh_name, en_url, zh_url in PAIRS:
        en_path, zh_path = ROOT / en_name, ROOT / zh_name
        en, zh = front_matter(en_path), front_matter(zh_path)
        checks = (
            (en.get("lang") == "en", f"{en_name}: lang must be en"),
            (zh.get("lang") == "zh", f"{zh_name}: lang must be zh"),
            (en.get("permalink") == en_url, f"{en_name}: expected permalink {en_url}"),
            (zh.get("permalink") == zh_url, f"{zh_name}: expected permalink {zh_url}"),
            (en.get("translation_url") == zh_url, f"{en_name}: translation must point to {zh_url}"),
            (zh.get("translation_url") == en_url, f"{zh_name}: translation must point to {en_url}"),
        )
        errors.extend(message for passed, message in checks if not passed)

    masthead = (ROOT / "_includes/masthead.html").read_text(encoding="utf-8")
    if "page.translation_url" not in masthead:
        errors.append("masthead: language control does not use page.translation_url")

    if errors:
        print("Bilingual route check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Bilingual route check passed for {len(PAIRS)} page pairs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

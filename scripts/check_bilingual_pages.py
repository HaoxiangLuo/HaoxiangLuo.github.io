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
    ("_pages/opportunities.html", "_pages/opportunities-zh.html", "/opportunities/", "/zh/opportunities/"),
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


def navigation_sections() -> dict[str, list[tuple[str, str]]]:
    """Parse _data/navigation.yml into {section: [(title, url), ...]}."""
    sections: dict[str, list[tuple[str, str]]] = {}
    current: str | None = None
    title = ""
    for line in (ROOT / "_data/navigation.yml").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith((" ", "\t")) and stripped.endswith(":"):
            current = stripped[:-1]
            sections[current] = []
            continue
        if current is None:
            continue
        if stripped.startswith("- title:"):
            title = stripped.split(":", 1)[1].strip().strip('"').strip("'")
        elif stripped.startswith("url:"):
            url = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            sections[current].append((title, url))
    return sections


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

    # The two navigation lists must stay parallel, otherwise a menu entry
    # silently disappears on one side of the site.
    sections = navigation_sections()
    main, main_zh = sections.get("main", []), sections.get("main_zh", [])
    if len(main) != len(main_zh):
        errors.append(
            f"_data/navigation.yml: main has {len(main)} entries but main_zh has {len(main_zh)}"
        )
    for (en_title, en_url), (zh_title, zh_url) in zip(main, main_zh):
        if en_url.rsplit("/", 2)[-2] != zh_url.rsplit("/", 2)[-2]:
            errors.append(
                f"_data/navigation.yml: '{en_title}' ({en_url}) and '{zh_title}' ({zh_url}) do not match"
            )

    masthead = (ROOT / "_includes/masthead.html").read_text(encoding="utf-8")
    if "page.translation_url" not in masthead:
        errors.append("masthead: language control does not use page.translation_url")

    if errors:
        print("Bilingual route check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Bilingual route check passed for {len(PAIRS)} page pairs and {len(main)} navigation entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

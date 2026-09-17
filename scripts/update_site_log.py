#!/usr/bin/env python3
"""Save concise, durable site-update records from Git commits."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "_data" / "site_updates.json"
MAX_ENTRIES = 100


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def changed_files(sha: str) -> list[str]:
    output = git("diff-tree", "--no-commit-id", "--name-only", "-r", "-m", sha)
    return sorted(set(filter(None, output.splitlines())))


def labels(files: list[str]) -> tuple[list[str], list[str]]:
    zh: list[str] = []
    en: list[str] = []

    def add(zh_label: str, en_label: str) -> None:
        if zh_label not in zh:
            zh.append(zh_label)
            en.append(en_label)

    for path in files:
        if path.startswith("_pages/about"):
            add("首页", "Home")
        elif "publications" in path:
            add("论文发表", "Publications")
        elif "study-notes" in path:
            add("学习札记", "Study Notes")
        elif "site-log" in path or "site_log" in path:
            add("网站日志", "Site Log")
        elif "daily-news" in path or "daily_news" in path:
            add("每日新闻", "Daily News")
        elif path.startswith("_data/navigation") or "masthead" in path:
            add("导航", "navigation")
        elif path.startswith(("_sass/", "assets/css/")):
            add("界面样式", "interface styling")
        elif path.startswith(("_includes/", "_layouts/")):
            add("页面结构", "page structure")
        elif path.startswith("assets/js/"):
            add("页面交互", "interactions")

    if not zh:
        add("网站内容", "site content")
    return zh[:4], en[:4]


def details(files: list[str]) -> tuple[str, str]:
    """Describe changed areas in language suited to the public log."""
    descriptions = (
        (lambda path: path.startswith("_pages/about"), "调整首页介绍、研究兴趣或全球要闻卡片。", "Refined the home introduction, research interests, or global-news card."),
        (lambda path: "publications" in path, "调整论文发表页面的内容或筛选浏览方式。", "Refined publication content or its browsing controls."),
        (lambda path: "study-notes" in path, "调整学习札记的内容或展开交互。", "Refined study-note content or its expandable interaction."),
        (lambda path: "site-log" in path or "site_log" in path, "调整网站日志的归档内容、呈现方式或自动记录。", "Refined the site-log archive, presentation, or automatic record."),
        (lambda path: "daily-news" in path or "daily_news" in path, "调整每日新闻的归档内容、呈现方式或自动更新。", "Refined the daily-news archive, presentation, or automatic update."),
        (lambda path: path.startswith(("_sass/", "assets/css/")), "优化页面的排版、间距与响应式视觉效果。", "Improved typography, spacing, and responsive visual presentation."),
        (lambda path: path.startswith("assets/js/"), "优化页面筛选或其他交互体验。", "Improved page filtering or other interactions."),
        (lambda path: path.startswith(("_includes/", "_layouts/")), "调整页面组件与内容结构。", "Adjusted page components and content structure."),
    )
    zh, en = [], []
    for matches, zh_text, en_text in descriptions:
        if any(matches(path) for path in files) and zh_text not in zh:
            zh.append(zh_text)
            en.append(en_text)
    if not zh:
        return "更新网站内容与信息呈现。", "Updated website content and information presentation."
    return "".join(zh), " ".join(en)


def make_entry(sha: str) -> dict[str, object] | None:
    message = git("show", "-s", "--format=%s", sha)
    if message.startswith(("Update daily news ", "Record site update ", "Merge branch ")):
        return None

    files = changed_files(sha)
    zh, en = labels(files)
    details_zh, details_en = details(files)
    raw_date = git("show", "-s", "--format=%cI", sha)
    date = datetime.fromisoformat(raw_date).astimezone(ZoneInfo("Asia/Shanghai"))
    short_sha = git("rev-parse", "--short=7", sha)
    return {
        "date": date.strftime("%Y-%m-%d"),
        "title_zh": "更新：" + "、".join(zh),
        "title_en": "Updated " + ", ".join(en),
        "message": message,
        "purpose_zh": "持续改进网站内容、信息组织与使用体验。",
        "purpose_en": message,
        "details_zh": details_zh,
        "details_en": details_en,
        "sha": short_sha,
        "url": f"https://github.com/HaoxiangLuo/HaoxiangLuo.github.io/commit/{sha}",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", default="HEAD")
    parser.add_argument("--backfill", type=int, default=0)
    args = parser.parse_args()

    current = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else []
    if not isinstance(current, list):
        current = []

    shas = [args.sha]
    if args.backfill:
        shas = git("rev-list", f"--max-count={args.backfill}", args.sha).splitlines()

    by_sha = {
        entry.get("sha"): entry
        for entry in current
        if isinstance(entry, dict)
        and not str(entry.get("message", "")).startswith(("Update daily news ", "Record site update ", "Merge branch "))
    }
    for sha in reversed(shas):
        entry = make_entry(sha)
        if entry:
            by_sha[entry["sha"]] = entry

    entries = sorted(by_sha.values(), key=lambda entry: (entry["date"], entry["sha"]), reverse=True)
    OUTPUT.write_text(json.dumps(entries[:MAX_ENTRIES], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved {min(len(entries), MAX_ENTRIES)} site updates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

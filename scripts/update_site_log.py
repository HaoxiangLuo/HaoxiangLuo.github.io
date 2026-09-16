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


def make_entry(sha: str) -> dict[str, object] | None:
    message = git("show", "-s", "--format=%s", sha)
    if message.startswith(("Update daily news ", "Record site update ", "Merge branch ")):
        return None

    files = changed_files(sha)
    zh, en = labels(files)
    raw_date = git("show", "-s", "--format=%cI", sha)
    date = datetime.fromisoformat(raw_date).astimezone(ZoneInfo("Asia/Shanghai"))
    short_sha = git("rev-parse", "--short=7", sha)
    return {
        "date": date.strftime("%Y-%m-%d"),
        "title_zh": "更新：" + "、".join(zh),
        "title_en": "Updated " + ", ".join(en),
        "message": message,
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

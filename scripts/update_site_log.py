#!/usr/bin/env python3
"""Save concise, durable site-update records from Git commits."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # Fallback for hosts without the IANA tz database.
    TZ = timezone(timedelta(hours=8))

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "_data" / "site_updates.json"
MAX_ENTRIES = 100
MODELS_ENDPOINT = "https://models.github.ai/inference/chat/completions"
MODELS_MODEL = "openai/gpt-4o-mini"


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
        elif "opportunities" in path:
            add("资讯", "Opportunities")
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
        (lambda path: "opportunities" in path, "调整资讯页面的收录内容、板块结构或自动采集。", "Refined the opportunities archive, sections, or automatic collection."),
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


def story(files: list[str], zh_labels: list[str], en_labels: list[str]) -> tuple[str, str]:
    """Write one brief, public-facing sentence about the change."""
    scope_zh = "、".join(zh_labels)
    scope_en = ", ".join(en_labels)
    if any("daily-news" in path or "daily_news" in path for path in files):
        return (
            f"为了更方便地了解世界动态，我调整了{scope_zh}，让信息更新与归档更可靠。",
            f"To make world events easier to follow, I refined {scope_en} so updates and archives remain reliable.",
        )
    if any(path.startswith(("_sass/", "assets/css/")) or "masthead" in path for path in files):
        return (
            f"页面还可以更清楚、更顺手。这次重新整理了{scope_zh}的视觉与交互。",
            f"The site could feel clearer and easier to use, so I refined the visual design and interaction of {scope_en}.",
        )
    return (
        f"为了让内容更完整、查找更轻松，这次更新了{scope_zh}。",
        f"To make the content more complete and easier to find, I updated {scope_en}.",
    )


def describe_via_models(subject: str, files: list[str], stat: str, token: str) -> dict[str, str]:
    """Ask GitHub Models for one specific, brief sentence about the change."""
    file_list = "\n".join(files[:20])
    stat_text = "\n".join(stat.splitlines()[:14])
    payload = json.dumps(
        {
            "model": MODELS_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You write public changelog entries for Haoxiang Luo's bilingual academic "
                        "website. Given a commit subject, changed files and a diff stat, reply with "
                        'a JSON object with keys "story_zh", "story_en", "details_zh", "details_en". '
                        "story_zh: one Simplified Chinese sentence, at most 45 characters, in the "
                        "pattern 增加了X，用于X or 对X进行了X改动，使X更X. story_en: the matching English "
                        "sentence, at most 24 words. details_zh/details_en: one or two short clauses "
                        "naming the concrete areas changed. Describe only what the commit clearly "
                        "does. No markdown, no quotes, no commit jargon, keep it brief."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Subject: {subject}\n\nFiles:\n{file_list}\n\nDiff stat:\n{stat_text}",
                },
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
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
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = json.loads(body["choices"][0]["message"]["content"])
    return {
        key: str(content.get(key, "")).strip().strip('"').strip()
        for key in ("story_zh", "story_en", "details_zh", "details_en")
    }


def make_entry(sha: str) -> dict[str, object] | None:
    message = git("show", "-s", "--format=%s", sha)
    if message.startswith(("Update daily news ", "Record site update ", "Merge branch ")):
        return None

    files = changed_files(sha)
    zh, en = labels(files)
    story_zh, story_en = story(files, zh, en)
    details_zh, details_en = details(files)
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        try:
            stat = git("diff-tree", "--no-commit-id", "--stat", "-m", sha)
            described = describe_via_models(message, files, stat, token)
            story_zh = described["story_zh"] or story_zh
            story_en = described["story_en"] or story_en
            details_zh = described["details_zh"] or details_zh
            details_en = described["details_en"] or details_en
        except Exception as exc:
            print(f"warning: model description failed for {sha[:7]}: {exc}", file=sys.stderr)
    raw_date = git("show", "-s", "--format=%cI", sha)
    date = datetime.fromisoformat(raw_date).astimezone(TZ)
    short_sha = git("rev-parse", "--short=7", sha)
    return {
        "date": date.strftime("%Y-%m-%d"),
        "title_zh": "调整了" + "、".join(zh),
        "title_en": "Refined " + ", ".join(en),
        "message": message,
        "story_zh": story_zh,
        "story_en": story_en,
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
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Regenerate the entry for --sha (or the backfilled range) even if it already exists.",
    )
    args = parser.parse_args()

    current = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else []
    if not isinstance(current, list):
        current = []

    shas = [args.sha]
    if args.backfill:
        shas = git("rev-list", f"--max-count={args.backfill}", args.sha).splitlines()

    if args.refresh:
        refresh_keys = {git("rev-parse", "--short=7", sha) for sha in shas}
        current = [entry for entry in current if entry.get("sha") not in refresh_keys]

    by_sha = {
        entry.get("sha"): entry
        for entry in current
        if isinstance(entry, dict)
        and not str(entry.get("message", "")).startswith(("Update daily news ", "Record site update ", "Merge branch "))
    }
    for sha in reversed(shas):
        entry = make_entry(sha)
        if entry and entry["sha"] not in by_sha:
            by_sha[entry["sha"]] = entry

    entries = sorted(by_sha.values(), key=lambda entry: (entry["date"], entry["sha"]), reverse=True)
    OUTPUT.write_text(json.dumps(entries[:MAX_ENTRIES], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved {min(len(entries), MAX_ENTRIES)} site updates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

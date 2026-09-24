#!/usr/bin/env python3
"""Save concise, specific site-update records from Git commits.

Every entry is written for a reader of the site, not for a developer: it names
the concrete thing that changed and what that change is for. One sentence, in
one of two shapes:

    增加了X，该功能用于X        (something was added; say what it does)
    对X进行了X改动，使X变得X     (something was changed; say what it improves)

Vague wording ("优化了体验", "让页面更清楚") is rejected: it describes nothing
and reads the same for every commit. When the model call fails or returns
something unusable, the fallback below names the touched areas instead of
falling back to a generic sentence.
"""

from __future__ import annotations

import argparse
import json
import os
import re
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

# Wording that describes nothing. If a generated sentence contains one of these
# it is discarded and the area-based fallback is used instead.
BANNED_PHRASES = (
    "更清楚、更顺手",
    "持续改进",
    "进一步完善",
    "不断优化",
    "提升用户体验",
    "优化体验",
    "界面更友好",
    "更加完善",
    "让网站更好",
)

SYSTEM_PROMPT = """You write public changelog entries for Haoxiang Luo's bilingual academic website.

Reply with a JSON object with exactly these keys: story_zh, story_en, title_zh, title_en, details_zh, details_en.

Rules for story_zh — ONE Simplified Chinese sentence, 20 to 45 characters, following one of these two shapes word for word:
  增加了X，该功能用于X
  对X进行了X改动，使X变得X
X must be a concrete part of this site: a page, a section, a control, a script or a data file. Never a vague noun such as 体验、效果、内容、质量.
Name what the change does for a visitor, for example 使导航栏各间距相等、使每日抓取的内容按日收起、使论文可按年份筛选.

Rules for story_en — the same content in English, ONE sentence, at most 22 words, in one of these shapes:
  Added X, which does Y.
  Changed X so that Y.

Rules for title_zh — 6 to 16 characters naming the concrete thing that changed, no full stop, e.g. 导航栏间距与切换器、每日新闻归档、资讯页按日折叠.
Rules for title_en — at most 6 words, same content.
Rules for details_zh / details_en — one or two short clauses naming the concrete areas or files touched.

Never use these phrases: 更清楚、更顺手、持续改进、进一步完善、优化体验、界面更友好、更加完善.
Never mention commit hashes, branch names, markdown or quotes.
Describe only what the commit clearly does. If the diff is ambiguous, name the areas or files touched rather than guessing at a purpose."""

FEWSHOT_USER = """Subject: Add Opportunities page with daily internship and academia collectors

Files:
_pages/opportunities.html
_data/opportunities.json

Diff stat:
 _pages/opportunities.html | 84 ++++++++++
 _data/opportunities.json | 26 +++"""

FEWSHOT_ASSISTANT = json.dumps(
    {
        "story_zh": "增加了资讯页面，该功能用于按日收录联合国与企业实习、以及海外高校交流项目。",
        "story_en": "Added an Opportunities page, which archives UN and company internships plus university exchange programmes by day.",
        "title_zh": "资讯页面与每日采集",
        "title_en": "Opportunities page and daily collection",
        "details_zh": "新增中英双语资讯页与导航入口，实习板块区分联合国与企业两类来源。",
        "details_en": "Added the bilingual Opportunities page and its navigation entry, splitting UN and company internship sources.",
    },
    ensure_ascii=False,
)


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
        elif "opportunities" in path or "opps" in path:
            add("资讯", "Opportunities")
        elif "archive-date-filter" in path:
            add("归档筛选", "archive date filter")
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
        (lambda path: path.startswith(("_sass/", "assets/css/")), "调整样式表中的排版、间距与响应式规则。", "Adjusted typography, spacing and responsive rules in the stylesheet."),
        (lambda path: path.startswith("assets/js/"), "调整页面的筛选、展开或其他交互脚本。", "Adjusted the page's filtering, expand/collapse or other interaction scripts."),
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


def fallback_story(files: list[str], zh_labels: list[str], en_labels: list[str]) -> tuple[str, str]:
    """A sentence that still names the concrete area when the model is unavailable.

    The model is not reliable from the workflow, so this path is taken often;
    it must read like a real entry rather than a placeholder. It names the
    touched area and what that area does, never a general improvement.
    """
    scope_zh = "、".join(zh_labels)
    scope_en = ", ".join(en_labels)

    # A commit touching only scripts and templates is an interaction change,
    # even when those files belong to a section: repairing the expand button is
    # not the same as changing what that section collects.
    if files and all(path.startswith(("assets/js/", "_includes/", "_layouts/")) for path in files):
        return (
            f"对{scope_zh}的脚本与交互逻辑进行了改动，使页面上的展开、筛选等操作能够稳定完成。",
            f"Changed the script and interaction logic of {scope_en} so expanding and filtering the page works reliably.",
        )

    def whole_topic(predicate) -> bool:
        """True when every changed file belongs to that one topic.

        A commit spanning several areas must not be described as if all of
        them did the same thing, so the specific sentences are reserved for
        commits whose files all point at one topic.
        """
        return bool(files) and all(predicate(path) for path in files)

    if whole_topic(lambda path: "daily-news" in path or "daily_news" in path):
        return (
            f"对{scope_zh}的采集与归档脚本进行了改动，使每日内容按日留存、重复条目不再重复入库。",
            f"Changed the collection and archiving script behind {scope_en} so daily items are kept by date and duplicates are stored once.",
        )
    if whole_topic(lambda path: "opportunities" in path or "opps" in path):
        return (
            f"对{scope_zh}的收录与归档方式进行了改动，使每天抓取的内容按日留存、历史日期默认收起。",
            f"Changed how {scope_en} is collected and archived so each day's items are kept by date and earlier days stay folded.",
        )
    if whole_topic(lambda path: path.startswith(("_sass/", "assets/css/")) or "masthead" in path):
        return (
            f"对{scope_zh}的排版、间距与响应式规则进行了改动，使其在窄屏与宽屏下的排布更整齐。",
            f"Changed the typography, spacing and responsive rules of {scope_en} so the layout is tidier on both narrow and wide screens.",
        )
    if any(path.startswith("_data/") for path in files):
        return (
            f"更新了{scope_zh}的归档数据，使页面读到的记录与最新一次改动保持一致。",
            f"Updated the archived data behind {scope_en} so the page shows the records from the latest change.",
        )
    if any(path.startswith(("assets/js/", "_includes/", "_layouts/")) for path in files):
        return (
            f"对{scope_zh}的脚本与交互逻辑进行了改动，使页面上的展开、筛选等操作能够稳定完成。",
            f"Changed the script and interaction logic of {scope_en} so expanding and filtering the page works reliably.",
        )
    if any(path.startswith(("_sass/", "assets/css/")) or "masthead" in path for path in files):
        return (
            f"对{scope_zh}的排版、间距与响应式规则进行了改动，使其在窄屏与宽屏下的排布更整齐。",
            f"Changed the typography, spacing and responsive rules of {scope_en} so the layout is tidier on both narrow and wide screens.",
        )
    return (
        f"对{scope_zh}的内容与呈现方式进行了改动，使相关信息更完整、更容易查到。",
        f"Changed the content and presentation of {scope_en} so the information is more complete and easier to find.",
    )


def acceptable(text: str, max_len: int) -> bool:
    """Reject empty, padded or substance-free sentences."""
    value = (text or "").strip()
    if not value or len(value) > max_len:
        return False
    return not any(phrase in value for phrase in BANNED_PHRASES)


def describe_via_models(subject: str, body: str, files: list[str], stat: str, diff: str, token: str, compact: bool = False) -> dict[str, str] | None:
    """Ask GitHub Models for one specific, brief sentence about the change.

    `compact` drops the few-shot example and the diff excerpt: a retry with a
    smaller payload gets through in cases where the full one does not.
    """
    if compact:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Subject: {subject}\n\nFiles:\n" + "\n".join(files[:12])},
        ]
        payload = json.dumps(
            {"model": MODELS_MODEL, "messages": messages, "temperature": 0.2, "response_format": {"type": "json_object"}}
        ).encode("utf-8")
        request = urllib.request.Request(
            MODELS_ENDPOINT,
            data=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body_json = json.loads(response.read().decode("utf-8"))
        content = json.loads(body_json["choices"][0]["message"]["content"])
        keys = ("story_zh", "story_en", "title_zh", "title_en", "details_zh", "details_en")
        return {key: re.sub(r"\s+", " ", str(content.get(key, "")).strip().strip('"').strip()) for key in keys}

    user_parts = [f"Subject: {subject}"]
    if body:
        user_parts.append(f"\nCommit message body:\n{body[:800]}")
    user_parts.append("\nFiles:\n" + "\n".join(files[:20]))
    if stat:
        user_parts.append("\nDiff stat:\n" + "\n".join(stat.splitlines()[:14]))
    if diff:
        user_parts.append("\nDiff excerpt:\n" + diff[:3000])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": FEWSHOT_USER},
        {"role": "assistant", "content": FEWSHOT_ASSISTANT},
        {"role": "user", "content": "\n".join(user_parts)},
    ]
    payload = json.dumps(
        {
            "model": MODELS_MODEL,
            "messages": messages,
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
        body_json = json.loads(response.read().decode("utf-8"))
    content = json.loads(body_json["choices"][0]["message"]["content"])
    keys = ("story_zh", "story_en", "title_zh", "title_en", "details_zh", "details_en")
    return {
        key: re.sub(r"\s+", " ", str(content.get(key, "")).strip().strip('"').strip())
        for key in keys
    }


def make_entry(sha: str) -> dict[str, object] | None:
    message = git("show", "-s", "--format=%s", sha)
    if message.startswith(("Update daily news ", "Record site update ", "Merge branch ")):
        return None

    files = changed_files(sha)
    zh, en = labels(files)
    story_zh, story_en = fallback_story(files, zh, en)
    details_zh, details_en = details(files)
    title_zh = "调整了" + "、".join(zh)
    title_en = "Refined " + ", ".join(en)

    body = git("show", "-s", "--format=%b", sha)
    stat = git("diff-tree", "--no-commit-id", "--stat", "-m", sha)
    try:
        diff = git("show", "--format=", "-U1", "--no-color", sha)
        diff = "\n".join(line for line in diff.splitlines() if not line.startswith("index "))
    except Exception:
        diff = ""

    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        for attempt, compact in ((1, False), (2, True)):
            try:
                described = describe_via_models(message, body, files, stat, diff, token, compact=compact)
                problems = [
                    label
                    for label, value, limit in (
                        ("story_zh", described.get("story_zh", ""), 60),
                        ("story_en", described.get("story_en", ""), 160),
                    )
                    if not acceptable(value, limit)
                ]
                if problems:
                    print(f"warning: model answer rejected for {sha[:7]}: {', '.join(problems)} unusable", file=sys.stderr)
                    continue
                story_zh = described["story_zh"]
                story_en = described["story_en"]
                if described.get("details_zh"):
                    details_zh = described["details_zh"]
                if described.get("details_en"):
                    details_en = described["details_en"]
                if described.get("title_zh") and acceptable(described["title_zh"], 24):
                    title_zh = described["title_zh"]
                if described.get("title_en") and acceptable(described["title_en"], 48):
                    title_en = described["title_en"]
                break
            except Exception as exc:
                print(f"warning: model description failed for {sha[:7]} (attempt {attempt}): {exc}", file=sys.stderr)

    raw_date = git("show", "-s", "--format=%cI", sha)
    date = datetime.fromisoformat(raw_date).astimezone(TZ)
    short_sha = git("rev-parse", "--short=7", sha)
    return {
        "date": date.strftime("%Y-%m-%d"),
        "title_zh": title_zh,
        "title_en": title_en,
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
    parser.add_argument("--dry-run", action="store_true", help="Build the entries and print them without writing the archive.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Regenerate the entry for --sha (or the backfilled range) even if it already exists.",
    )
    parser.add_argument(
        "--only-shas",
        default="",
        help="Comma-separated short SHAs to regenerate; other existing entries are kept as they are.",
    )
    args = parser.parse_args()

    current = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else []
    if not isinstance(current, list):
        current = []

    shas = [args.sha]
    if args.backfill:
        shas = git("rev-list", f"--max-count={args.backfill}", args.sha).splitlines()

    if args.only_shas:
        wanted = {value.strip() for value in args.only_shas.split(",") if value.strip()}
        shas = [
            sha
            for sha in git("rev-list", "--max-count=400", args.sha).splitlines()
            if git("rev-parse", "--short=7", sha) in wanted
        ]
        args.refresh = True

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
    if args.dry_run:
        for sha in shas:
            entry = by_sha.get(git("rev-parse", "--short=7", sha))
            if not entry:
                continue
            print(f"--- {entry['sha']} {entry['date']}")
            print(f"    subject : {entry['message']}")
            print(f"    title_zh: {entry['title_zh']}")
            print(f"    story_zh: {entry['story_zh']}")
            print(f"    title_en: {entry['title_en']}")
            print(f"    story_en: {entry['story_en']}")
        print(f"dry run: {len(entries)} entries would be saved")
        return 0

    OUTPUT.write_text(json.dumps(entries[:MAX_ENTRIES], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved {min(len(entries), MAX_ENTRIES)} site updates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

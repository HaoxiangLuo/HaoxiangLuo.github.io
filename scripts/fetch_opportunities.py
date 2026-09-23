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
import html
import json
import re
import sys
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Collect and report without writing the archive.")
    args = parser.parse_args()

    raw = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    sections = {
        "internships": raw.get("internships") if isinstance(raw.get("internships"), list) else [],
        "academia": raw.get("academia") if isinstance(raw.get("academia"), list) else [],
    }

    today = datetime.now(TZ).strftime("%Y-%m-%d")

    intern_candidates = gather(INTERN_SOURCES, lambda s: COLLECTORS[s["kind"]](s))
    academia_candidates = gather(ACADEMIA_SOURCES, collect_academia)

    added_intern = append_new(sections["internships"], intern_candidates, today)
    added_academia = append_new(sections["academia"], academia_candidates, today)

    print(f"candidates: {len(intern_candidates)} internships, {len(academia_candidates)} academia")
    print(f"new items: internships={added_intern}, academia={added_academia}")

    if args.dry_run:
        print("dry run: archive not written")
        return 0

    if added_intern == 0 and added_academia == 0:
        print("nothing new to record; archive left unchanged")
        return 0

    archive = {
        "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "internships": sections["internships"][:MAX_DAYS],
        "academia": sections["academia"][:MAX_DAYS],
    }
    OUTPUT.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"saved {added_intern} internships and {added_academia} academia items for {today}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

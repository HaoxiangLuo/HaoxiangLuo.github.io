#!/usr/bin/env python3
"""Collect internship and academic-mobility opportunities for the "Opportunities" page.

Two sections are maintained in `_data/opportunities.json`:

* `internships` — United Nations system openings collected by
  scripts/un_sources.py across twenty organisations, then judged by
  scripts/opps_match.py (direction, function, topics, eligibility, mode and
  organisation, out of 100). Anything scoring below 60 is never stored, so the
  page stays a shortlist rather than a mirror of every vacancy; plus a handful
  of global-company internship boards.
* `academia` — PhD exchange, visiting-scholar and joint-training
  announcements from journalism/communication departments at QS top-50
  universities, extracted from official department pages.

Only items that have never been collected before are appended under today's
date. When nothing new is found the archive file is left untouched, so the
daily workflow can skip the commit entirely.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import os
import re
import socket
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import model_client  # noqa: E402  (sibling module: scripts/model_client.py)
import opps_match  # noqa: E402  (sibling module: scripts/opps_match.py)
import un_sources  # noqa: E402  (sibling module: scripts/un_sources.py)

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
MAX_UN_PER_DAY = 60  # scored UN openings kept in one day
# One organisation must not fill the page: UNESCO alone can publish fourteen
# internships at once, and fourteen near-identical cards answer none of the
# three questions the page exists for. Six keeps a daily run readable while a
# smaller organisation still gets its one relevant post through.
MAX_UN_PER_ORG = 6
REQUEST_TIMEOUT = 25
USER_AGENT = "HaoxiangLuo.github.io opportunities collector/1.0"

# --- Translation -----------------------------------------------------------
# Packaged for the Opportunities record shape: two plain-text fields per item
# instead of a single headline. The model call itself is shared with the other
# generators through scripts/model_client.py, which reads the endpoint, key and
# model from the environment (GitHub Models, the original provider, was retired
# on 2026-07-30). There is deliberately no unauthenticated public translate
# endpoint as a silent fallback: when no provider is configured or the request
# fails, the field simply stays pending and the next scheduled run fills it in.
TRANSLATE_TIMEOUT = 20
MAX_TRANSLATIONS_PER_RUN = 40  # text fields per run, history first
MAX_SOURCE_CHARS = 240  # refuse to send anything longer to the model
MAX_TRANSLATION_CHARS = 240  # refuse a reply that rambles or explains
TRANSLATE_ATTEMPTS = 2  # bounded retries for one field
CJK_RE = re.compile(r"[\u3400-\u9fff]")
# URLs, HTML and workflow variables never reach the model.
UNSAFE_TEXT_RE = re.compile(r"https?://|<[a-z!/]|[{][{]", re.I)

# The United Nations section is collected by scripts/un_sources.py and judged by
# scripts/opps_match.py; see those two modules for the organisation list and the
# scoring rules. What is left here are the company boards, which stay on the old
# title-matching path because they publish internships and nothing else.
COMPANY_SOURCES = [
    {"name": "Amazon", "name_zh": "亚马逊", "kind": "amazon_json", "value": "https://www.amazon.jobs/en/search.json?result_limit=30&base_query=intern", "group": "company"},
    {"name": "Airbnb", "name_zh": "爱彼迎", "kind": "greenhouse", "value": "airbnb", "group": "company"},
    {"name": "Stripe", "name_zh": "Stripe", "kind": "greenhouse", "value": "stripe", "group": "company"},
    {"name": "Anthropic", "name_zh": "Anthropic", "kind": "greenhouse", "value": "anthropic", "group": "company"},
    {"name": "Cloudflare", "name_zh": "Cloudflare", "kind": "greenhouse", "value": "cloudflare", "group": "company"},
]

# A consultancy is not an internship and is kept out of the internship list; the
# exception the profile asks for is a consultancy that says in writing that it
# takes doctoral, postgraduate or early-career researchers. Those are stored
# anyway, tagged "extended", so they can be shown apart rather than mixed in.
UN_INTERNSHIP_TYPES = {"internship", "traineeship", "fellowship", "young_professional"}
EARLY_CAREER_RE = re.compile(
    r"\b(?:phd|doctoral|doctorate|postgraduate|graduate student|early[- ]career"
    r"|recent graduate|master'?s (?:degree|student)|master'?s level)\b",
    re.I,
)
# An opening missing from its organisation's listing for this many days has been
# taken down. Long enough that one broken career site cannot close anything.
UNSEEN_DAYS = 21
# "Closing soon" is seven days; three days or fewer is urgent enough to say so.
URGENT_DAYS = 3

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
    """The identity an archived item is deduplicated by.

    A UN opening carries its organisation and job id, which is authoritative:
    the same post seen on two platforms still has one id. Everything else falls
    back to the URL and then to a normalised title.
    """
    if item.get("org") and item.get("job_id"):
        return f"{item['org']}:{item['job_id']}"
    url = re.sub(r"[#?].*$", "", (item.get("url") or "").rstrip("/").lower())
    if url:
        return url
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", (item.get("title") or "").lower())


SYSTEM_PROMPTS = {
    "zh": (
        "You translate English job titles, academic programme titles and short "
        "location or supplementary lines taken from official internship and "
        "academic-mobility announcements into concise Simplified Chinese. Keep "
        "organisations, universities, companies, programme abbreviations, job "
        "levels, numbers, deadlines and place names exactly as they are. Do not "
        "add any information that the source does not contain. Reply with the "
        "translation only: no quotes, no pinyin, no explanation."
    ),
    "en": (
        "You translate Chinese job titles, academic programme titles and short "
        "location or supplementary lines into concise English. Keep "
        "organisations, universities, companies, programme abbreviations, job "
        "levels, numbers, deadlines and place names exactly as they are. Do not "
        "add any information that the source does not contain. Reply with the "
        "translation only."
    ),
}


def tidy_translation(value: str, target: str) -> str:
    """Normalise a model reply, or return "" when it is not usable.

    Empty, over-long, URL-bearing and wrong-script replies are rejected so the
    field is left for the next run instead of being filled with noise.
    """
    text = clean_text(value)
    text = text.strip().strip('"').strip("“”‘’").strip()
    text = re.sub(
        r"^(翻译|译文|简体中文|英译|Chinese translation|Chinese|English|Translation)\s*[:：]\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) > MAX_TRANSLATION_CHARS:
        return ""
    if UNSAFE_TEXT_RE.search(text):
        return ""
    has_cjk = bool(CJK_RE.search(text))
    if target == "zh" and not has_cjk:
        return ""
    if target == "en" and has_cjk:
        return ""
    return text


class Translator:
    """A tiny field-level translator with a per-run cache.

    Only plain text is sent. Identical text is translated once per run, so a
    repeated job title across sources costs one request.
    """

    def __init__(self, token: str = "") -> None:
        self.token = token
        self.cache: dict[tuple[str, str], str] = {}
        self.calls = 0
        self.public_calls = 0
        self.pending = 0
        # Set once the endpoint has refused us twice in a row: the rest of the
        # run then stays offline instead of spending a request per field.
        self.unavailable = ""
        self.public_unavailable = False
        self._diagnosed = False

    @staticmethod
    def translatable(text: str) -> bool:
        if not text or len(text) > MAX_SOURCE_CHARS:
            return False
        return not UNSAFE_TEXT_RE.search(text)

    def translate(self, text: str, target: str) -> str:
        """Return the translation of `text`, or "" to leave the field pending."""
        key = (target, text)
        if key in self.cache:
            return self.cache[key]
        value = ""
        if self.token and self.translatable(text) and not self.unavailable:
            failures = 0
            for _ in range(TRANSLATE_ATTEMPTS):
                try:
                    self.calls += 1
                    value = tidy_translation(self._request(text, target), target)
                    time.sleep(0.15)
                except Exception as exc:
                    print(f"warning: translation failed: {exc}", file=sys.stderr)
                    self._diagnose()
                    failures += 1
                    value = ""
                if value:
                    break
            if not value and failures:
                self.unavailable = "endpoint refused the request; skipping the rest of this run"
        if not value and self.translatable(text) and not self.public_unavailable:
            value = self._public(text, target)
        if not value:
            self.pending += 1
        self.cache[key] = value
        return value

    def _public(self, text: str, target: str) -> str:
        """Google's unauthenticated endpoint: no key, but no guarantees.

        Reached when no provider is configured or the provider refused, so the
        Chinese page is not left empty just because nobody set a key up. One
        failure is enough to stop trying: an endpoint that has started refusing
        will refuse every remaining field in the run too.
        """
        try:
            self.public_calls += 1
            value = tidy_translation(model_client.public_translate(text, target), target)
        except Exception as exc:  # noqa: BLE001 - network failures of any kind
            print(f"warning: public translation failed: {exc}", file=sys.stderr)
            self.public_unavailable = True
            return ""
        time.sleep(0.15)
        return value

    def _request(self, text: str, target: str) -> str:
        return model_client.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPTS[target]},
                {"role": "user", "content": text},
            ],
            timeout=TRANSLATE_TIMEOUT,
        )


    def _diagnose(self) -> None:
        """Print, once per run, the host and proxy context of a failed call.

        A plain "OK" body means something answers in place of the inference
        API, so the run records how the endpoint resolved next to the failure.
        """
        if self._diagnosed:
            return
        self._diagnosed = True
        host = urlparse(model_client.endpoint()).hostname or "?"
        try:
            address = socket.gethostbyname(host)
        except Exception as exc:  # noqa: BLE001
            address = f"dns failed: {exc}"
        proxies = {
            name: os.environ[name]
            for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")
            if os.environ.get(name)
        }
        print(
            f"warning: translation host {host} -> {address}; proxy env {proxies or 'none'}",
            file=sys.stderr,
        )


def build_translator() -> Translator:
    """Build the translator from the provider the workflow configured.

    Without a configured provider the translator stays offline, so the run
    leaves every field pending instead of spending a request per field.
    """
    if not model_client.configured():
        print(
            "note: no translation provider configured (set TRANSLATE_BASE_URL and "
            "TRANSLATE_API_KEY); fields are filled through the public endpoint",
            file=sys.stderr,
        )
        return Translator("")
    return Translator(model_client.api_key())


def public_note(translator: Translator) -> str:
    """Report how many fields came from the unauthenticated endpoint."""
    if not translator.public_calls:
        return ""
    return f" ({translator.public_calls} via the public endpoint)"


# (source field, Chinese target, English target): `title_en` / `detail_en` are
# reserved for Chinese-language sources that may be collected later.
TRANSLATION_FIELDS = (
    ("title", "title_zh", "title_en"),
    ("detail", "detail_zh", "detail_en"),
)


def pending_field(item: dict, source_key: str, zh_key: str, en_key: str):
    """Describe the field that still needs a translation, or None."""
    text = str(item.get(source_key) or "").strip()
    if not text:
        return None
    if CJK_RE.search(text):  # a Chinese source: the English page needs it
        return None if item.get(en_key) else (text, en_key, "en")
    return None if item.get(zh_key) else (text, zh_key, "zh")


def backfill_translations(sections: dict, translator: Translator, budget: int = MAX_TRANSLATIONS_PER_RUN) -> dict:
    """Fill missing translations, newest day first, within `budget` fields.

    Existing translations are never overwritten, and one failed field never
    touches the record it belongs to: the item keeps its publisher wording and
    the Chinese page falls back to it.
    """
    filled = {"titles": 0, "details": 0}
    for name in ("internships", "academia"):
        for day in sections.get(name) or []:
            for item in day.get("items", []):
                for source_key, zh_key, en_key in TRANSLATION_FIELDS:
                    if filled["titles"] + filled["details"] >= budget:
                        return filled
                    job = pending_field(item, source_key, zh_key, en_key)
                    if job is None:
                        continue
                    text, target_key, target = job
                    translated = translator.translate(text, target)
                    if not translated:
                        continue
                    item[target_key] = translated
                    filled["titles" if source_key == "title" else "details"] += 1
    return filled


# Long-term archive hook: `opportunities` is not one of the three datasets in
# scripts/archive_data.py yet (those are daily_news, academic_frontiers and
# site_updates), so `_data/opportunities.json` is still the only storage and
# this file is written directly. When Opportunities joins the three-layer
# archive, replace write_archive() below with
# `archive_data.upsert(ROOT, "opportunities", records)` exactly as
# scripts/fetch_daily_news.py does: the translations then live in the JSONL
# partitions and are re-projected into the recent index, and nothing in the
# record shape has to change.
def write_archive(archive: dict) -> None:
    """Replace the archive atomically: write a temp file, parse it, then swap."""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(archive, ensure_ascii=False, indent=2) + "\n"
    temporary = OUTPUT.with_name(OUTPUT.name + ".tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        json.loads(temporary.read_text(encoding="utf-8"))
        os.replace(temporary, OUTPUT)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


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


# --- United Nations pipeline -----------------------------------------------
def un_summary(record: dict, result: dict, deadline: str) -> tuple[str, str]:
    """One summary line per language, built from the fields already extracted.

    Both lines are generated, not translated: the archive has to read correctly
    in Chinese on a day when no translation provider answers, and every word in
    them comes from data the collector actually found.
    """
    place_zh = opps_match.location_zh(result["city"], result["country"])
    en = [record["org_name"], record["location"] or "Location not stated"]
    zh = [record["org_zh"], place_zh or record["location"] or "地点未说明"]
    if result["mode"] != "unknown":
        en.append(result["mode"].capitalize())
        zh.append(opps_match.MODE_ZH.get(result["mode"], ""))
    if deadline:
        en.append(f"Apply by {deadline}")
        zh.append(f"截止 {deadline}")
    else:
        en.append("Deadline not stated")
        zh.append("截止日期未说明")
    if result["duration"]:
        en.append(result["duration"])
        zh.append(result["duration"].replace("months", "个月").replace("month", "个月")
                  .replace("weeks", "周").replace("week", "周")
                  .replace("years", "年").replace("year", "年"))
    en.append(opps_match.STIPEND_EN.get(result["stipend"], "Stipend not stated"))
    zh.append(opps_match.STIPEND_ZH.get(result["stipend"], "津贴未说明"))
    return " · ".join(part for part in en if part), " · ".join(part for part in zh if part)


def build_un_item(record: dict, result: dict, today: date) -> dict:
    """Turn one scored opening into the record the page renders."""
    deadline = record["deadline"] or result["deadline"]
    remaining = opps_match.days_left(deadline, today)
    status = opps_match.status_of(deadline, today)
    detail, detail_zh = un_summary(record, result, deadline)
    extended = result["type"] == "consultancy"
    return {
        "title": record["title"],
        "url": record["url"],
        "detail": detail,
        "detail_zh": detail_zh,
        "source": record["org_name"],
        "source_zh": record["org_zh"],
        "org": record["org"],
        "group": "un",
        "job_id": record["job_id"],
        "type": result["type"],
        "type_label": opps_match.TYPE_LABELS.get(result["type"], "Opening"),
        "type_zh": opps_match.TYPE_ZH.get(result["type"], "其他"),
        "areas": result["areas"],
        "areas_zh": opps_match.areas_zh(result["areas"]),
        "location": record["location"],
        "city": result["city"],
        "country": result["country"],
        "region": result["region"],
        "mode": result["mode"],
        "mode_zh": opps_match.MODE_ZH.get(result["mode"], "未说明"),
        "department": record["department"],
        "eligibility": result["eligibility"],
        "eligibility_zh": "、".join(
            opps_match.ELIGIBILITY_ZH.get(key, key) for key in result["eligibility"]
        ),
        "phd_ok": result["phd_ok"],
        "duration": result["duration"],
        "stipend": result["stipend"],
        "stipend_zh": opps_match.STIPEND_ZH.get(result["stipend"], "津贴未说明"),
        "stipend_amount": result["stipend_amount"],
        "language": result["language"],
        "posted": record["posted"],
        "deadline": deadline,
        "days_left": remaining,
        # Booleans the page filters on. Liquid cannot compare a date to today,
        # so "closing soon" and the score bands are decided here instead.
        "open": status != "closed",
        "closing": remaining is not None and 0 <= remaining <= 7,
        "urgent": remaining is not None and 0 <= remaining <= URGENT_DAYS and status != "closed",
        "score90": result["score"] >= 90,
        "score80": result["score"] >= 80,
        "score70": result["score"] >= 70,
        "status": status,
        "status_zh": opps_match.STATUS_ZH.get(status, "未说明"),
        # What the page sorts "newly published" by: the organisation's own
        # posting date when it prints one, otherwise the day we first saw it.
        "sort_date": record["posted"] or today.isoformat(),
        "found": today.isoformat(),
        "score": result["score"],
        "tier": result["tier"],
        "tier_zh": result["tier_zh"],
        "tier_en": opps_match.tier_en(result["score"]),
        "reasons": result["reasons"],
        "reasons_zh": result["reasons_zh"],
        "extended": extended,
        "excluded": result["excluded"],
    }


def collect_un_candidates(today: date) -> tuple[list[dict], set[str]]:
    """Fetch, judge, deduplicate and rank the UN openings.

    The order is the order the page promises: match first, then how soon it
    closes, then how recently it appeared. A closing deadline is the tie-break
    that makes "worth applying to" and "about to close" the same list.

    The second return value is every opening the run saw, filtered or not. The
    archive is checked against it each day: an opening that stops appearing has
    been taken down, and only the run that saw the listing can know that.
    """
    records = un_sources.collect_all()
    kept: dict[str, dict] = {}
    seen: set[str] = set()
    for record in records:
        identity, fallback = opps_match.dedupe_key(
            record["org"], record["job_id"], record["url"], record["title"]
        )
        if identity:
            seen.add(identity)
        result = opps_match.score_opening(
            title=record["title"],
            description=record["description"],
            org_code=record["org"],
            org_priority=record["priority"],
            department=record["department"],
            location=record["location"],
            today=today,
        )
        if result["excluded"] or result["score"] < opps_match.MIN_SCORE:
            continue  # finance, HR, engineering and anything else off-profile
        if result["type"] in UN_INTERNSHIP_TYPES:
            pass
        elif result["type"] == "consultancy" and EARLY_CAREER_RE.search(
            f"{record['title']} {record['description']}"
        ):
            pass  # a consultancy that explicitly takes doctoral researchers
        else:
            continue
        item = build_un_item(record, result, today)
        key = identity or fallback
        # Same opening seen twice: keep the better described copy, and never
        # let an aggregator's link replace the organisation's own.
        previous = kept.get(key)
        if previous is None or item["score"] > previous["score"] or (
            item["score"] == previous["score"] and len(item["detail"]) > len(previous["detail"])
        ):
            kept[key] = item
    ranked = sorted(
        kept.values(),
        key=lambda item: (
            -item["score"],
            item["deadline"] or "9999-12-31",
            -(int(item["posted"].replace("-", "") or 0) if item["posted"] else 0),
        ),
    )
    per_org: dict[str, int] = {}
    limited = []
    for item in ranked:
        already = per_org.get(item["org"], 0)
        if already >= MAX_UN_PER_ORG:
            continue
        per_org[item["org"]] = already + 1
        limited.append(item)
    return limited[:MAX_UN_PER_DAY], seen


def refresh_un_items(sections: dict, seen: set[str], today: date) -> int:
    """Re-derive everything about a stored opening that depends on today.

    A stored record keeps the day it was collected; its deadline moves. Run
    daily, this is what turns an open post into a closed one, and what notices
    a post that has been taken down: an opening missing from the listing for
    UNSEEN_DAYS runs has gone, however far away its deadline was.
    """
    changed = 0
    for day in sections.get("internships") or []:
        for item in day.get("items", []):
            if item.get("group") != "un":
                continue
            identity = f"{item.get('org', '')}:{item.get('job_id', '')}"
            if identity in seen and item.get("last_seen") != today.isoformat():
                item["last_seen"] = today.isoformat()
                changed += 1
            deadline = item.get("deadline") or ""
            remaining = opps_match.days_left(deadline, today)
            status = opps_match.status_of(deadline, today)
            last_seen = item.get("last_seen") or ""
            if last_seen and opps_match.days_left(last_seen, today) is not None:
                if opps_match.days_left(last_seen, today) <= -UNSEEN_DAYS:
                    status = "closed"  # gone from the listing, not just past its date
            for field, value in (
                ("status", status),
                ("status_zh", opps_match.STATUS_ZH.get(status, "未说明")),
                ("days_left", remaining),
                ("open", status != "closed"),
                ("closing", remaining is not None and 0 <= remaining <= 7),
                ("urgent", remaining is not None and 0 <= remaining <= URGENT_DAYS and status != "closed"),
            ):
                if item.get(field) != value:
                    item[field] = value
                    changed += 1
    return changed


COLLECTORS = {
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


def normalise_days(days: list[dict]) -> list[dict]:
    """Repair an archive in place: one entry per date, no repeated items.

    The archive is the only storage this page has, so it is normalised before
    anything is added rather than trusted: two runs that land on the same date
    (a retry after a push race, say) would otherwise leave two entries for one
    day, and repeated items would survive inside a single day.
    """
    merged: dict[str, dict] = {}
    order: list[str] = []
    for day in days or []:
        date = day.get("date")
        if not date:
            continue
        bucket = merged.setdefault(date, {"date": date, "items": []})
        if date not in order:
            order.append(date)
        seen = {item_key(item) for item in bucket["items"]}
        for item in day.get("items", []):
            key = item_key(item)
            if key in seen:
                continue
            seen.add(key)
            bucket["items"].append(item)
    normalised = [merged[date] for date in order]
    normalised.sort(key=lambda day: day["date"], reverse=True)
    return normalised


def migrate_un_items(sections: dict) -> int:
    """Give UN items collected before scoring existed the fields the page filters on.

    The page sorts and filters on `score`, `status` and `open`, and Liquid
    cannot compare a missing value safely, so the archive is given explicit
    values instead of nils. An item saved before scoring existed is judged on
    what was stored — its title, which is the one field every source
    provides — so it takes its real place in the ranking instead of showing
    a bare zero.
    """
    registry = {source["name"].lower(): source for source in un_sources.SOURCES}
    changed = 0
    for day in sections.get("internships") or []:
        for item in day.get("items", []):
            if item.get("group") != "un":
                continue
            if "status" not in item:
                item["status"] = "open"
                changed += 1
            if "open" not in item:
                item["open"] = item["status"] != "closed"
                changed += 1
            if not isinstance(item.get("score"), int):
                source = registry.get((item.get("source") or "").lower(), {})
                judged = opps_match.score_opening(
                    title=item.get("title", ""),
                    org_code=source.get("code", ""),
                    org_priority=source.get("priority", 2),
                    location=item.get("location", ""),
                )
                item["score"] = judged["score"]
                item["tier"] = judged["tier"]
                item["tier_zh"] = judged["tier_zh"]
                item["reasons"] = judged["reasons"]
                item["reasons_zh"] = judged["reasons_zh"]
                changed += 1
    return changed


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Collect and report without writing the archive.")
    parser.add_argument(
        "--translate-only",
        action="store_true",
        help="Fill in missing translations of stored items without collecting anything.",
    )
    parser.add_argument(
        "--max-translations",
        type=int,
        default=MAX_TRANSLATIONS_PER_RUN,
        help=f"How many text fields one run may translate (default {MAX_TRANSLATIONS_PER_RUN}).",
    )
    args = parser.parse_args(argv)

    raw = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    sections = {
        "internships": raw.get("internships") if isinstance(raw.get("internships"), list) else [],
        "academia": raw.get("academia") if isinstance(raw.get("academia"), list) else [],
    }
    normalised = {name: normalise_days(days) for name, days in sections.items()}
    # A copy, not the same list: append_new edits in place, so the "did
    # normalising repair anything" comparison needs the pre-normalised state.
    before = {name: copy.deepcopy(value) for name, value in normalised.items()}
    sections.update(normalised)
    migrated = migrate_un_items(sections)

    translator = build_translator()

    def fill(budget: int) -> dict:
        """Translate within a budget; a failure here must never lose an item."""
        try:
            return backfill_translations(sections, translator, budget)
        except Exception as exc:
            print(f"warning: translation backfill aborted: {exc}", file=sys.stderr)
            return {"titles": 0, "details": 0}

    # History first: an older item whose translation failed last time gets
    # another chance before today's new items are translated.
    history = fill(args.max_translations)

    if args.translate_only:
        print(
            f"translations: {history['titles']} titles, {history['details']} details filled; "
            f"{translator.pending} field(s) pending retry{public_note(translator)}"
        )
        if args.dry_run:
            print("dry run: archive not written")
            return 0
        if not (history["titles"] or history["details"]):
            print("nothing left to translate; archive left unchanged")
            return 0
        write_archive(
            {
                "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
                "internships": sections["internships"][:MAX_DAYS],
                "academia": sections["academia"][:MAX_DAYS],
            }
        )
        print(f"saved {history['titles']} titles and {history['details']} details without collecting")
        return 0

    today = datetime.now(TZ).strftime("%Y-%m-%d")

    un_candidates, seen = collect_un_candidates(datetime.now(TZ).date())
    company_candidates = gather(COMPANY_SOURCES, lambda s: COLLECTORS[s["kind"]](s))
    intern_candidates = un_candidates + company_candidates
    academia_candidates = gather(ACADEMIA_SOURCES, collect_academia)
    # Before anything new is added: yesterday's openings are a day older, and a
    # deadline that has passed must not still read "open".
    refreshed = refresh_un_items(sections, seen, datetime.now(TZ).date())

    added_intern = append_new(sections["internships"], intern_candidates, today)
    added_academia = append_new(sections["academia"], academia_candidates, today)

    print(f"candidates: {len(intern_candidates)} internships, {len(academia_candidates)} academia")
    print(f"new items: internships={added_intern}, academia={added_academia}")
    print(f"status refreshed on {refreshed} stored field(s)")

    # Whatever is left of the budget goes to the items just collected.
    remaining = max(args.max_translations - history["titles"] - history["details"], 0)
    fresh = fill(remaining) if remaining else {"titles": 0, "details": 0}
    titles = history["titles"] + fresh["titles"]
    details = history["details"] + fresh["details"]
    print(
        f"translations: {titles} titles, {details} details filled; "
        f"{translator.pending} field(s) pending retry{public_note(translator)}"
    )

    if args.dry_run:
        stored_intern = sum(len(day["items"]) for day in sections["internships"])
        stored_academia = sum(len(day["items"]) for day in sections["academia"])
        print(
            f"dry run: archive not written "
            f"(would hold {len(sections['internships'])} internship days / {stored_intern} items, "
            f"{len(sections['academia'])} academia days / {stored_academia} items)"
        )
        return 0

    # Nothing new is the normal case: the archive already holds these items and
    # stays exactly as it was. It is only rewritten when the day added
    # something, when normalising repaired a duplicate date or item, or when a
    # translation was filled in.
    repaired = any(before[name] != sections[name] for name in before) or migrated or refreshed
    if added_intern == 0 and added_academia == 0 and not repaired and not (fresh["titles"] or fresh["details"]):
        print("nothing new to record; archive left unchanged")
        return 0

    archive = {
        "updated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "internships": sections["internships"][:MAX_DAYS],
        "academia": sections["academia"][:MAX_DAYS],
    }
    write_archive(archive)
    stored_intern = sum(len(day["items"]) for day in archive["internships"])
    stored_academia = sum(len(day["items"]) for day in archive["academia"])
    print(f"saved {added_intern} internships and {added_academia} academia items for {today}")
    print(
        f"archive now holds {len(archive['internships'])} internship days / {stored_intern} items, "
        f"{len(archive['academia'])} academia days / {stored_academia} items"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

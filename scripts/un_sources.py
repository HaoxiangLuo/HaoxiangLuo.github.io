#!/usr/bin/env python3
"""Fetch internship openings from United Nations system career sites.

Every organisation here publishes its vacancies differently, so this module is
a registry of sources plus one small collector per publishing platform:

    un_careers          careers.un.org JSON API (returns the full text)
    workday             Workday CXS JSON (UNHCR, WFP)
    oracle_cx           Oracle Recruiting Cloud REST (UNFPA, IOM)
    undp_html           UNDP's own vacancy table (title, level, deadline, station)
    unwomen_html        UN Women's own vacancy table (title, type, city, deadline)
    taleo               Taleo REST search (WHO, FAO)
    rss                 category feeds that carry the full text (ITU, ILO, UNOPS,
                        UNESCO, UNICEF)
    successfactors_html SuccessFactors career sites rendered as HTML (UNIDO)
    smartrecruiters     SmartRecruiters public API (OECD)

Three rules govern everything here:

1. **Official first.** Only organisation-run career sites and the ATS they
   host on their own domain are listed; no aggregator is a source.
2. **The official link survives.** Whatever a record gains in analysis, `url`
   always points back at the publisher's own job page.
3. **A source that fails loses only itself.** Collectors raise, the caller
   catches, and the rest of the run continues — one broken career site must
   never empty a day's collection.

Nothing here decides whether an opening is interesting; that is
scripts/opps_match.py. This module only produces text and links.
"""

from __future__ import annotations

import gzip
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import opps_match  # noqa: E402  (sibling module: scripts/opps_match.py)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30
RETRIES = 3
MAX_DETAIL_PER_SOURCE = 8
MAX_DETAIL_TOTAL = 60
MAX_TEXT_CHARS = 12000  # enough for the rules, small enough to stay quick

# --- Source registry -------------------------------------------------------
# `priority` follows the site owner's own ordering of organisations; `code`
# doubles as the dedupe namespace and the page's filter value.
SOURCES: list[dict] = [
    # --- first priority -------------------------------------------------
    {"code": "un", "name": "UN Secretariat", "name_zh": "联合国秘书处", "kind": "un_careers", "priority": 1},
    {"code": "unesco", "name": "UNESCO", "name_zh": "联合国教科文组织", "kind": "rss",
     "value": "https://careers.unesco.org/services/rss/job/?locale=en_GB&keywords=(internship)", "priority": 1},
    {"code": "unicef", "name": "UNICEF", "name_zh": "联合国儿童基金会", "kind": "rss",
     "value": "https://jobs.unicef.org/cw/en/rss", "priority": 1},
    {"code": "undp", "name": "UNDP", "name_zh": "联合国开发计划署", "kind": "undp_html",
     "value": "https://jobs.undp.org/cj_view_jobs.cfm", "priority": 1},
    {"code": "unwomen", "name": "UN Women", "name_zh": "联合国妇女署", "kind": "unwomen_html",
     "value": "https://www.unwomen.org/en/jobs/undp?items_per_page=50", "priority": 1},
    {"code": "unhcr", "name": "UNHCR", "name_zh": "联合国难民署", "kind": "workday",
     "host": "unhcr.wd3.myworkdayjobs.com", "tenant": "unhcr", "site": "External", "priority": 1},
    # --- second priority ------------------------------------------------
    {"code": "unfpa", "name": "UNFPA", "name_zh": "联合国人口基金", "kind": "oracle_cx",
     "host": "estm.fa.em2.oraclecloud.com", "site": "CX_2003", "priority": 2},
    {"code": "unep", "name": "UNEP", "name_zh": "联合国环境规划署", "kind": "un_careers", "dept": "22302230", "priority": 2},
    {"code": "wfp", "name": "WFP", "name_zh": "世界粮食计划署", "kind": "workday",
     "host": "wfp.wd3.myworkdayjobs.com", "tenant": "wfp", "site": "job_openings", "priority": 2},
    {"code": "who", "name": "WHO", "name_zh": "世界卫生组织", "kind": "taleo",
     "host": "careers.who.int", "site": "ex", "portal": "101430233", "priority": 2},
    {"code": "iom", "name": "IOM", "name_zh": "国际移民组织", "kind": "oracle_cx",
     "host": "fa-evlj-saasfaprod1.fa.ocs.oraclecloud.com", "site": "CX_1001", "priority": 2},
    {"code": "itu", "name": "ITU", "name_zh": "国际电信联盟", "kind": "rss",
     "value": "https://jobs.itu.int/services/rss/category/?catid=8943055", "priority": 2},
    {"code": "unhabitat", "name": "UN-Habitat", "name_zh": "联合国人居署", "kind": "un_careers",
     "dept": "19801980", "priority": 2},
    {"code": "unctad", "name": "UNCTAD", "name_zh": "联合国贸发会议", "kind": "un_careers",
     "dept": "20442044", "priority": 2},
    {"code": "ohchr", "name": "OHCHR", "name_zh": "联合国人权高专办", "kind": "un_careers",
     "dept": "15201520", "priority": 2},
    {"code": "unops", "name": "UNOPS", "name_zh": "联合国项目事务署", "kind": "rss",
     "value": "https://careers.unops.org/careersmarketplace/SearchJobs/feed/?jobRecordsPerPage=50", "priority": 2},
    # --- third priority -------------------------------------------------
    {"code": "ilo", "name": "ILO", "name_zh": "国际劳工组织", "kind": "rss",
     "value": "https://jobs.ilo.org/services/rss/category/?catid=9589701", "priority": 3},
    {"code": "fao", "name": "FAO", "name_zh": "联合国粮农组织", "kind": "taleo",
     "host": "jobs.fao.org", "site": "fao_external", "portal": "8105120163", "priority": 3},
    {"code": "unido", "name": "UNIDO", "name_zh": "联合国工发组织", "kind": "successfactors_html",
     "value": "https://careers.unido.org/search/", "base": "https://careers.unido.org", "priority": 3},
    {"code": "oecd", "name": "OECD", "name_zh": "经济合作与发展组织", "kind": "smartrecruiters",
     "company": "OECD", "priority": 3},
    # UNV, the World Bank, IFAD and UNAIDS are deliberately absent: none of
    # them exposes a feed, a public JSON endpoint or a server-rendered list,
    # so there is nothing a standard-library collector can read day after day.
]

JOB_LINK_RE = re.compile(r'href="([^"]*?/job/[^"]*?|[^"]*?/jobs/[^"]*?|[^"]*?/JobDetail/[^"]*?)"', re.I)
# A full anchor, not just its href: UNDP and UN Women print the job title as
# the anchor text, and reading the 400 characters after an href instead picks
# up the next tag's attributes and stores them as a title.
ANCHOR_RE = re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
# Feeds that carry no vacancy still publish one placeholder item.
PLACEHOLDER_RE = re.compile(r"no jobs? (?:currently )?available|no (?:current )?vacanc", re.I)
OG_DESCRIPTION_RE = re.compile(
    r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', re.I
)
OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.I
)
SCRIPT_RE = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
JOB_ID_IN_URL_RE = re.compile(r"/(?:job|jobs)/(\d{3,})")
# UNICEF prints the requisition number and duty station inside the title:
# "Communication Officer, NO-2 #00138827, Bangkok - Thailand(6 months)".
UNICEF_LOCATION_RE = re.compile(r"#\d+,\s*(.+?)\s*(?:\([^)]*\))?\s*$")
# Each UNDP vacancy is one anchor holding five <span> cells in a fixed order.
UNDP_SPAN_RE = re.compile(r"<span[^>]*>(.*?)</span>", re.S)
# UN Women prints a plain table: title, type, country, city, deadline.
UNWOMEN_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
UNWOMEN_CELL_RE = re.compile(r'<td[^>]*class="([^"]*)"[^>]*>(.*?)</td>', re.S)


def http_get(
    url: str,
    data: bytes | None = None,
    headers: dict | None = None,
    timeout: int = REQUEST_TIMEOUT,
    retries: int = RETRIES,
) -> str:
    """One request with retries, gzip handling and a browser-like identity.

    Several of these career sites answer an unknown agent with 403 or drop the
    connection, and the UN Careers API intermittently returns 504, so a bounded
    retry is part of talking to them rather than an optimisation.
    """
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        "Accept-Language": "en",
    }
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, data=data, headers=request_headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw.decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - any transport failure retries
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{url} failed after {retries} attempts: {last_error}")


def http_json(url: str, data: bytes | None = None, headers: dict | None = None,
              timeout: int = REQUEST_TIMEOUT, retries: int = RETRIES) -> dict:
    return json.loads(http_get(url, data=data, headers=headers, timeout=timeout, retries=retries))


def html_text(page: str) -> str:
    """Strip a job page down to the words the rules can read."""
    page = SCRIPT_RE.sub(" ", page or "")
    text = TAG_RE.sub(" ", page)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()[:MAX_TEXT_CHARS]


def meta_content(page: str, pattern: re.Pattern) -> str:
    match = pattern.search(page or "")
    return html.unescape(match.group(1)).strip() if match else ""


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def job_id_from_url(url: str) -> str:
    match = JOB_ID_IN_URL_RE.search(url or "")
    return match.group(1) if match else ""


def record(source: dict, title: str, url: str, **extra) -> dict:
    """One opening in the shape the rest of the pipeline expects."""
    if not url or not title:
        raise ValueError("an opening needs both a title and a link")
    if not url.startswith("http"):
        url = (source.get("base") or "") + url
    item = {
        "org": source["code"],
        "org_name": source["name"],
        "org_zh": source["name_zh"],
        "priority": source.get("priority", 3),
        "title": clean(title),
        "url": url,
        "job_id": extra.get("job_id") or job_id_from_url(url),
        "location": clean(extra.get("location", "")) or location_from_title(title) or unicef_location(title)
        or opps_match.place_from_text(title),
        "department": clean(extra.get("department", "")),
        "posted": extra.get("posted", ""),
        "deadline": extra.get("deadline", ""),
        "description": html_text(extra.get("description", "")),
        "detail_url": extra.get("detail_url", ""),
    }
    return item


# --- Collectors ------------------------------------------------------------
# Several organisations are read through one shared backend. When that backend
# is down, the first source to fail records it here and the rest are skipped
# without a request, so a broken platform costs seconds instead of minutes.
_FAILED_HOSTS: set[str] = set()


def collect_un_careers(source: dict) -> list[dict]:
    """careers.un.org: the only source that returns the full text in one call.

    Its search backend intermittently answers POST with 504, and five of our
    organisations depend on it. One attempt each, and a shared short-circuit,
    keeps a bad day cheap.
    """
    host = "careers.un.org"
    if host in _FAILED_HOSTS:
        raise RuntimeError(f"{host} already failed in this run")
    payload = json.dumps(
        {
            "filterConfig": {
                "aoe": [], "aoi": [], "el": [], "ct": [], "ds": [], "jn": [], "jf": [],
                "jc": ["INT"],  # "INT" is the internship job category
                "jle": [], "dept": [source["dept"]] if source.get("dept") else [], "span": [],
            },
            "pagination": {"page": 0, "itemPerPage": 100, "sortBy": "startDate", "sortDirection": -1},
        }
    ).encode()
    try:
        body = http_json(
            "https://careers.un.org/api/public/opening/jo/list/filteredV2/en",
            data=payload,
            headers={"Referer": "https://careers.un.org/"},
            timeout=20,
            retries=1,
        )
    except Exception:
        _FAILED_HOSTS.add(host)
        raise
    results = []
    for job in (body.get("data") or {}).get("list") or []:
        job_id = str(job.get("jobId") or "")
        title = job.get("jobTitle") or job.get("postingTitle") or ""
        try:
            item = record(
                source,
                title,
                f"https://careers.un.org/job/{job_id}" if job_id else "",
                job_id=job_id,
                location=", ".join(
                    station.get("description", "") for station in job.get("dutyStation") or [] if station.get("description")
                ),
                department=(job.get("dept") or {}).get("name", ""),
                posted=opps_match.parse_date(str(job.get("startDate") or "")),
                deadline=opps_match.parse_date(str(job.get("endDate") or "")),
                description=job.get("jobDescription") or "",
            )
        except ValueError:
            continue
        results.append(item)
    return results


def collect_workday(source: dict) -> list[dict]:
    host, tenant, site = source["host"], source["tenant"], source["site"]
    payload = json.dumps({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "intern"}).encode()
    body = http_json(f"https://{host}/wday/cxs/{tenant}/{site}/jobs", data=payload)
    results = []
    for job in body.get("jobPostings") or []:
        path = job.get("externalPath") or ""
        if not path:
            continue
        bullets = job.get("bulletFields") or []
        try:
            item = record(
                source,
                job.get("title", ""),
                f"https://{host}/en-US/{site}{path}",
                job_id=bullets[0] if bullets else "",
                location=job.get("locationsText", ""),
                posted=opps_match.parse_date(job.get("postedOn", "")),
                detail_url=f"https://{host}/wday/cxs/{tenant}/{site}{path}",
            )
        except ValueError:
            continue
        results.append(item)
    return results


def collect_workday_detail(item: dict) -> str:
    body = http_json(item["detail_url"])
    info = body.get("jobPostingInfo") or {}
    return info.get("jobDescription") or ""


def collect_oracle_cx(source: dict) -> list[dict]:
    host, site = source["host"], source["site"]
    finder = f"findReqs;siteNumber={site},keyword=intern,limit=25,offset=0,sortBy=POSTING_DATES_DESC"
    url = (
        f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
        f"?onlyData=true&expand=requisitionList.secondaryLocations,flexFieldsFacet.values&finder={finder}"
    )
    body = http_json(url, headers={"Accept": "application/json"})
    results = []
    for job in ((body.get("items") or [{}])[0].get("requisitionList") or []):
        job_id = str(job.get("Id") or "")
        source_url = source.get("url_template") or (
            f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/requisitions/job/{job_id}"
        )
        try:
            item = record(
                source,
                job.get("Title", ""),
                source_url.replace("{id}", job_id).replace("{site}", site),
                job_id=job_id,
                location=" ".join(
                    part for part in [job.get("PrimaryLocation", ""), job.get("PrimaryLocationCountry", "")] if part
                ).strip(" ,"),
                posted=opps_match.parse_date(str(job.get("PostedDate") or "")),
                deadline=opps_match.parse_date(str(job.get("PostingEndDate") or "")),
                description=job.get("ShortDescriptionStr") or "",
                detail_url=(
                    f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
                    f"?onlyData=true&expand=all&finder=ById;Id={job_id},siteNumber={site}"
                ),
            )
        except ValueError:
            continue
        results.append(item)
    return results


def collect_oracle_cx_detail(item: dict) -> str:
    body = http_json(item["detail_url"], headers={"Accept": "application/json"})
    return ((body.get("items") or [{}])[0].get("ExternalDescriptionStr")) or ""


TALEO_BODY = {
    "multilineEnabled": False,
    "sortingSelection": {"sortBySelectionParam": "1", "ascendingSortingOrder": "false"},
    "fieldData": {"fields": {"KEYWORD": "intern", "LOCATION": ""}, "valid": True},
    "filterSelectionParam": {"searchFilterSelections": [
        {"id": name, "selectedValues": []}
        for name in ("LOCATION", "JOB_FIELD", "ORGANIZATION", "JOB_SCHEDULE", "JOB_TYPE", "JOB_LEVEL", "WILL_TRAVEL", "POSTING_DATE")
    ]},
    "advancedSearchFiltersSelectionParam": {"searchFilterSelections": [
        {"id": name, "selectedValues": []}
        for name in ("LOCATION", "JOB_FIELD", "ORGANIZATION", "JOB_NUMBER", "JOB_LEVEL", "JOB_SHIFT",
                     "JOB_SCHEDULE", "JOB_TYPE", "WILL_TRAVEL", "URGENT_JOB", "STUDY_LEVEL")
    ]},
    "pageNo": 1,
}


def collect_taleo(source: dict) -> list[dict]:
    """Taleo REST search.

    WHO's portal answers a keyword search for "intern" with nothing at all
    while its unfiltered listing is populated, so an empty keyword is tried
    before giving up: a wider list costs one request, a missed organisation
    costs the whole source.
    """
    items = _taleo_search(source, "intern")
    if not items:
        items = _taleo_search(source, "")
    return items


def _taleo_search(source: dict, keyword: str) -> list[dict]:
    host, site, portal = source["host"], source["site"], source["portal"]
    payload = json.loads(json.dumps(TALEO_BODY))
    payload["fieldData"]["fields"]["KEYWORD"] = keyword
    body = http_json(
        f"https://{host}/careersection/rest/jobboard/searchjobs?lang=en&portal={portal}",
        data=json.dumps(payload).encode(),
        headers={"tz": "GMT+00:00", "Referer": f"https://{host}/careersection/{site}/jobsearch.ftl"},
    )
    results = []
    for job in body.get("requisitionList") or []:
        columns = job.get("column") or []
        contest = str(job.get("contestNo") or job.get("jobId") or "")
        try:
            item = record(
                source,
                columns[0] if columns else "",
                f"https://{host}/careersection/{site}/jobdetail.ftl?job={contest}&lang=en",
                job_id=contest,
                location=clean(re.sub(r"[\[\]\"']", " ", columns[1] if len(columns) > 1 else "")),
                posted=opps_match.parse_date(columns[2] if len(columns) > 2 else ""),
            )
        except ValueError:
            continue
        results.append(item)
    return results


def collect_rss(source: dict) -> list[dict]:
    page = http_get(source["value"], headers={"Accept": "application/rss+xml, application/xml;q=0.9"})
    root = ET.fromstring(page)
    results = []
    for entry in root.findall(".//item"):
        title = entry.findtext("title", "") or ""
        link = (entry.findtext("link", "") or "").strip()
        if not link or PLACEHOLDER_RE.search(title):
            continue  # an empty category still publishes one "no jobs" item
        if urlparse(link).path in ("", "/"):
            continue  # the feed's own homepage, not a job
        try:
            item = record(
                source,
                title,
                link,
                posted=opps_match.parse_date(entry.findtext("pubDate", "") or ""),
                description=entry.findtext("description", "") or "",
            )
        except ValueError:
            continue
        results.append(item)
    return results


def location_from_title(title: str) -> str:
    """ITU and ILO feeds put the duty station in the title: "Intern (Geneva, Switzerland)"."""
    match = re.search(r"\(([^()]*,\s*[^()]*)\)\s*$", title or "")
    return match.group(1).strip() if match else ""


def unicef_location(title: str) -> str:
    """Duty station from UNICEF's "#requisition, station (duration)" suffix."""
    match = UNICEF_LOCATION_RE.search(title or "")
    if not match:
        return ""
    station = match.group(1).strip(" -")
    return re.sub(r"\s*-\s*", ", ", station) if " - " in station else station


def job_anchors(page: str) -> list[tuple[str, str]]:
    """Every link that looks like a job page, with its visible text."""
    found = []
    for match in ANCHOR_RE.finditer(page or ""):
        href, text = match.group(1), clean(match.group(2))
        if re.search(r"/job/|/jobs/|/JobDetail/", href, re.I):
            found.append((href, text))
    return found


def location_from_slug(url: str) -> str:
    """UNIDO puts the duty station first in the slug: /job/Vienna-Project-Associate/…"""
    for part in [p for p in url.split("?")[0].split("/") if p]:
        if part.isdigit() or part.lower() in ("job", "jobs", "search", "https:", "http:"):
            continue
        city = re.split(r"[-+]", part)[0].strip()
        if city.lower() == "home":
            return "Home-based"  # "Home-Based-…" means remote, so say so in full
        if city:
            return city
    return ""


def collect_successfactors_html(source: dict) -> list[dict]:
    """SuccessFactors career sites that render their listing as HTML."""
    page = http_get(source["value"])
    results = []
    seen: set[str] = set()
    for href, text in job_anchors(page):
        if href in seen:
            continue
        seen.add(href)
        try:
            item = record(source, text or slug_title(href), href,
                          location=location_from_slug(href), detail_url=href)
        except ValueError:
            continue
        results.append(item)
    return results


def slug_title(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    if slug.isdigit():
        slug = url.rstrip("/").split("/")[-2]
    return re.sub(r"[-_+]+", " ", slug).strip()


def collect_undp_html(source: dict) -> list[dict]:
    """jobs.undp.org: one anchor per vacancy, five <span> cells in a fixed order.

    Reading the anchor's whole text would store "Job Title … Post level … Apply
    by …" as the title, so the cells are taken one by one instead.
    """
    page = http_get(source["value"])
    results = []
    seen: set[str] = set()
    for match in ANCHOR_RE.finditer(page):
        href = match.group(1)
        job_id = job_id_from_url(href)
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        cells = [clean(span) for span in UNDP_SPAN_RE.findall(match.group(2))]
        if not cells:
            continue
        try:
            item = record(
                source,
                cells[0] or slug_title(href),
                href,
                job_id=job_id,
                location=cells[4] if len(cells) > 4 else "",
                department=cells[3] if len(cells) > 3 else "",
                deadline=opps_match.parse_date(cells[2] if len(cells) > 2 else ""),
                detail_url=href,
            )
        except ValueError:
            continue
        results.append(item)
    return results


def collect_unwomen_html(source: dict) -> list[dict]:
    """unwomen.org renders its vacancies as a table: title, type, country, city, deadline."""
    page = http_get(source["value"])
    results = []
    seen: set[str] = set()
    for row in UNWOMEN_ROW_RE.finditer(page):
        cells = {}
        for class_name, value in UNWOMEN_CELL_RE.findall(row.group(1)):
            cells[class_name.split()[-1]] = clean(value)
        href_match = re.search(r'href="([^"]+/job/[^"]*)"', row.group(1), re.I)
        if not href_match:
            continue
        href = href_match.group(1)
        job_id = job_id_from_url(href)
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        try:
            item = record(
                source,
                cells.get("views-field-title") or slug_title(href),
                href,
                job_id=job_id,
                location=cells.get("views-field-field-city") or cells.get("views-field-field-rss-country") or "",
                deadline=opps_match.parse_date(cells.get("views-field-field-deadline", "")),
                detail_url=href,
            )
        except ValueError:
            continue
        results.append(item)
    return results


def _smartrecruiters_search(company: str, query: str | None) -> dict:
    suffix = f"&q={query}" if query else ""
    return http_json(
        f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100&offset=0{suffix}",
        headers={"Accept": "application/json"},
    )


def collect_smartrecruiters(source: dict) -> list[dict]:
    """SmartRecruiters public API, with the same reasoning as Taleo: a keyword
    that finds nothing must not be mistaken for an empty career site."""
    company = source["company"]
    body = _smartrecruiters_search(company, "intern")
    if not (body.get("content") or []):
        body = _smartrecruiters_search(company, None)
    results = []
    for job in body.get("content") or []:
        location = (job.get("location") or {}).get("fullLocation", "") or (job.get("location") or {}).get("city", "")
        identifier = (job.get("company") or {}).get("identifier") or company
        posting_id = str(job.get("id") or "")
        # applyUrl and postingUrl are both null for some tenants; the public
        # careers page follows one stable shape, so build it rather than drop
        # the posting.
        url = job.get("applyUrl") or job.get("postingUrl") or (
            f"https://careers.smartrecruiters.com/{identifier}/{posting_id}" if posting_id else ""
        )
        try:
            item = record(
                source,
                job.get("name", ""),
                url,
                job_id=str(job.get("refNumber") or job.get("id") or ""),
                location=location,
                department=(job.get("department") or {}).get("label", ""),
                posted=opps_match.parse_date(job.get("releasedDate", "")),
                detail_url=f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{job.get('id')}",
            )
        except ValueError:
            continue
        results.append(item)
    return results


def collect_smartrecruiters_detail(item: dict) -> str:
    body = http_json(item["detail_url"], headers={"Accept": "application/json"})
    sections = ((body.get("jobAd") or {}).get("sections") or {})
    parts = []
    for key in ("jobDescription", "qualifications", "additionalInformation", "companyDescription"):
        parts.append((sections.get(key) or {}).get("text", ""))
    return " ".join(part for part in parts if part)


COLLECTORS = {
    "un_careers": collect_un_careers,
    "workday": collect_workday,
    "oracle_cx": collect_oracle_cx,
    "undp_html": collect_undp_html,
    "unwomen_html": collect_unwomen_html,
    "taleo": collect_taleo,
    "rss": collect_rss,
    "successfactors_html": collect_successfactors_html,
    "smartrecruiters": collect_smartrecruiters,
}

# Platforms whose listing call does not include the job text: the detail call
# is what turns a title-only record into one the rules can actually judge.
DETAIL_FETCHERS = {
    "workday": collect_workday_detail,
    "oracle_cx": collect_oracle_cx_detail,
    "smartrecruiters": collect_smartrecruiters_detail,
}


def enrich(source: dict, items: list[dict], budget: dict) -> None:
    """Fill in the job text for records whose listing lacked it.

    `budget` is a shared counter so that a chatty platform cannot spend the
    whole run: at most MAX_DETAIL_TOTAL detail requests per collection.
    """
    for item in items:
        if item.get("description"):
            continue
        if budget["used"] >= MAX_DETAIL_TOTAL or budget["per_source"].get(source["code"], 0) >= MAX_DETAIL_PER_SOURCE:
            continue
        fetcher = DETAIL_FETCHERS.get(source["kind"])
        url = item.get("detail_url") or item.get("url")
        try:
            if fetcher:
                text = fetcher(item)
            else:
                page = http_get(url)
                text = meta_content(page, OG_DESCRIPTION_RE) or html_text(page)
                if not item.get("title") or item["title"].startswith("Vacancy"):
                    item["title"] = meta_content(page, OG_TITLE_RE) or item["title"]
            item["description"] = html_text(text)
            budget["used"] += 1
            budget["per_source"][source["code"]] = budget["per_source"].get(source["code"], 0) + 1
        except Exception as exc:  # noqa: BLE001 - a detail page is optional
            print(f"warning: {source['name']}: detail unavailable ({exc})", file=sys.stderr)


def collect_all(sources: list[dict] | None = None, enrich_details: bool = True) -> list[dict]:
    """Fetch every source; a failing source is skipped, never fatal."""
    budget = {"used": 0, "per_source": {}}
    collected: list[dict] = []
    for source in sources or SOURCES:
        try:
            items = COLLECTORS[source["kind"]](source)
        except Exception as exc:  # noqa: BLE001 - one career site must not stop the run
            print(f"warning: {source['name']}: {exc}", file=sys.stderr)
            continue
        if enrich_details:
            enrich(source, items, budget)
        collected.extend(items)
        print(f"{source['name']}: {len(items)} openings", file=sys.stderr)
    return collected


def main() -> int:
    """Probe the registry: `python scripts/un_sources.py [source code ...]`."""
    codes = sys.argv[1:]
    sources = SOURCES if not codes else [s for s in SOURCES if s["code"] in codes]
    for source in sources:
        try:
            items = COLLECTORS[source["kind"]](source)
            print(f"{source['code']:10s} {len(items):3d}  {source['name']}")
            for item in items[:2]:
                print(f"    {item['title'][:70]} | {item['location'][:30]} | {item['url'][:80]}")
        except Exception as exc:  # noqa: BLE001
            print(f"{source['code']:10s}  ERR  {source['name']}: {str(exc)[:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

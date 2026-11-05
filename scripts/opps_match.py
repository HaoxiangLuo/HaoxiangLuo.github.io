#!/usr/bin/env python3
"""Match a United Nations opening against one research profile.

The Opportunities page used to show everything a UN feed happened to return.
This module is the other half of that change: it reads a job title and its
description and decides what the opening actually is, which of the profile's
research directions it touches, whether a doctoral candidate may apply, how it
is paid and when it closes — then reduces all of that to one 0-100 score plus
one to three short reasons in both languages.

Everything here is pure: no network, no model, no file access. The collector
(scripts/un_sources.py) fetches text and hands it over; the tests feed it
fixtures. Keeping the rules in one importable place is what makes the scoring
reviewable without running a collection.

Scoring follows the profile the site owner asked for (journalism and
communication, computational communication, international communication,
digital governance, AI and society):

    research direction    30
    job function          25
    topics in the text    20
    eligibility           15
    mode and location      5
    organisation           5

Openings below MIN_SCORE are never stored: the archive only grows, so a
wrongly admitted finance or logistics post would sit on the page for 180 days.
"""

from __future__ import annotations

import re
from datetime import date, datetime

MIN_SCORE = 60  # below this an opening is not shown at all

# --- Keyword groups --------------------------------------------------------
# Longer phrases come first so that "digital communication" is counted as
# itself and not merely as another hit for "communication".
AREA_KEYWORDS: dict[str, list[str]] = {
    "communication": [
        r"strategic communication",
        r"digital communication",
        r"public information",
        r"media relations",
        r"social media",
        r"digital media",
        r"content strategy",
        r"content creation",
        r"editorial",
        r"advocacy",
        r"outreach",
        r"public engagement",
        r"external relations",
        r"knowledge communication",
        r"science communication",
        r"communications?",
    ],
    "research": [
        r"research assistant",
        r"research intern",
        r"policy research",
        r"policy analysis",
        r"research and analysis",
        r"monitoring and evaluation",
        r"knowledge management",
        r"behavioural science",
        r"behavioral science",
        r"social research",
        r"evaluation",
        r"evidence",
        r"research",
    ],
    "data": [
        r"data analys(?:is|tics)",
        r"data science",
        r"digital analytics",
        r"social media analytics",
        r"audience analytics",
        r"digital research",
        r"machine learning",
        r"natural language processing",
        r"text analysis",
        r"network analysis",
        r"digital methods",
        r"information systems",
        r"information management",
        r"computational",
        r"data",
    ],
    "ai": [
        r"artificial intelligence",
        r"machine learning",
        r"natural language processing",
        r"\bNLP\b",
        r"\bAI\b",
    ],
    "governance": [
        r"information integrity",
        r"misinformation",
        r"disinformation",
        r"digital governance",
        r"internet governance",
        r"platform governance",
        r"artificial intelligence governance",
        r"ai governance",
        r"digital policy",
        r"information policy",
        r"media development",
        r"freedom of expression",
        r"digital transformation",
        r"technology policy",
        r"global communication",
        r"international communication",
    ],
    "media": [r"journalism", r"journalist", r"\bpress\b", r"\bnews\b", r"broadcast", r"\bmedia\b"],
    "policy": [r"public policy", r"policy", r"governance"],
}

# Topics that raise the score even when the job title says nothing about them.
TOPIC_KEYWORDS = [
    "social media",
    "misinformation",
    "disinformation",
    "information integrity",
    "journalism",
    "artificial intelligence",
    "digital platform",
    "algorithm",
    "online communication",
    "public opinion",
    "audience",
    "digital society",
    "technology governance",
    "internet governance",
    "digital transformation",
    "information environment",
    "communication research",
    "public communication",
    "strategic communication",
    "global communication",
    "international communication",
    "computational method",
    "data analysis",
    "text analysis",
    "network analysis",
]

# Fields the profile has nothing to do with. They only demote an opening: a
# post that also does communication work survives on its own merits.
EXCLUSION_KEYWORDS = [
    r"\bfinanc\w*\b",  # finance / financial / financing: "Financial Services" must match too
    r"\baccounting\b",
    r"\baccountant\b",
    r"procurement",
    r"human resources",
    r"\bHR\b",
    r"\blegal\b",
    r"\blawyer\b",
    r"engineering",
    r"\bmedical\b",
    r"clinical",
    r"logistics",
    r"supply chain",
    # "security" on its own would exclude food security, human security and
    # cybersecurity, which together are most of what these organisations
    # advertise; only the guards-and-facilities sense is off profile.
    r"security (?:services?|officer|guard|personnel|management)",
    r"facility management",
    r"\bpayroll\b",
]

TYPE_PATTERNS = [
    ("internship", r"\binternships?\b|\binterns?\b"),
    ("traineeship", r"traineeship|\btrainee\b"),
    ("fellowship", r"fellowship"),
    ("young_professional", r"young professional|junior professional|\bJPO\b|\bYPP\b"),
    ("consultancy", r"consultanc(?:y|ies)|\bconsultant\b|individual contractor"),
]

REMOTE_PATTERNS = [
    r"\bremote\b",
    r"home[- ]based",
    r"work from home",
    r"telecommut",
    r"telework",
    r"virtual assignment",
]
HYBRID_PATTERNS = [r"\bhybrid\b", r"partly remote", r"part[- ]time remote"]

# `\b` matters here: without it "undergraduate students" is read as a hit for
# "graduate student", which would credit a bachelor-only post as graduate-eligible.
ELIGIBILITY_PATTERNS = {
    "phd": r"\bph\.?\s?d\b|doctoral|doctorate",
    "master": r"\bmaster'?s\b|\bpostgraduate\b|\bgraduate\b|second[- ]level university degree|advanced university degree",
    "graduate": r"\bgraduate student\b|recent graduate|graduated within|final year|enrolled in a (?:degree|graduate) programme|be enrolled",
    "undergraduate_only": r"undergraduate (?:students?|degree) only|bachelor'?s? (?:students?|degree) only|first[- ]level university degree only",
}

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

DATE_PATTERNS = [
    # 2026-11-15 / 2026/11/15
    (r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", "ymd"),
    # 15 November 2026 / 15 Nov 2026
    (r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})\b", "dmy"),
    # November 15, 2026
    (r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b", "mdy"),
    # 31/Dec/2026
    (r"\b(\d{1,2})[-/]([A-Za-z]{3,9})[-/](\d{4})\b", "dmy"),
    # 08-10-2026: UN Women prints day-month-year, so a bare numeric date is
    # read day-first rather than guessed at.
    (r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", "dmy_num"),
    # 7-Oct-26 / Oct 7 26 / Oct-7-26: UNDP prints "Apply by Oct-7-26".
    (r"\b(\d{1,2})[-\s]([A-Za-z]{3,9})\.?[-\s](\d{2})\b", "dmy_short"),
    (r"\b([A-Za-z]{3,9})\.?[-\s](\d{1,2})[-\s](\d{2})\b", "mdy_short"),
]

DEADLINE_HINTS = [
    r"application deadline",
    r"deadline for applications",
    r"apply by",
    r"closing date",
    r"applications? (?:must|should) be (?:received|submitted) by",
    r"last date",
    r"\bdeadline\b",
]

UNPAID_PATTERNS = [
    r"\bunpaid\b",
    r"without (?:remuneration|compensation|pay)",
    r"no (?:remuneration|compensation|salary|stipend|financial compensation)",
    r"not remunerated",
    r"unremunerated",
    r"no funding",
]
PAID_PATTERNS = [
    r"stipend",
    r"monthly allowance",
    r"living allowance",
    r"travel allowance",
    r"subsistence allowance",
    r"remuneration",
    r"honorarium",
    r"\bsalary\b",
    r"\bDSA\b",
]
MONEY_RE = re.compile(
    r"(?:USD|US\$|EUR|CHF|GBP|CAD|AUD|\$|€|£)\s?\s?([\d,.]+)(?:\s?(?:per|/|a)\s?(month|year|week|day))?",
    re.I,
)

DURATION_RE = re.compile(
    r"\b(\d{1,2})\s?(?:-|–|to|or)?\s?(\d{1,2})?\s?(month|months|week|weeks|year|years)\b",
    re.I,
)

LANGUAGE_RE = re.compile(
    r"fluen(?:cy|t)\s+in\s+([A-Z][a-z]+(?:\s+or\s+[A-Z][a-z]+)?)|"
    r"(?:English|French|Spanish|Arabic|Chinese|Russian)\s*(?:and|or)\s*(?:English|French|Spanish|Arabic|Chinese|Russian)",
)

PRIORITY_CITIES = [
    "new york", "geneva", "paris", "washington", "vienna", "bangkok",
    "nairobi", "copenhagen", "rome", "brussels",
]

# Countries that appear as UN duty stations often enough to be worth naming;
# anything else keeps its raw country name and no region tag.
REGION_BY_COUNTRY = {
    "usa": "North America", "united states": "North America", "united states of america": "North America",
    "canada": "North America", "mexico": "North America",
    "switzerland": "Europe", "france": "Europe", "austria": "Europe", "italy": "Europe",
    "spain": "Europe", "denmark": "Europe", "germany": "Europe", "netherlands": "Europe",
    "belgium": "Europe", "sweden": "Europe", "norway": "Europe", "finland": "Europe",
    "united kingdom": "Europe", "uk": "Europe", "ireland": "Europe", "poland": "Europe",
    "portugal": "Europe", "greece": "Europe", "hungary": "Europe", "romania": "Europe",
    "serbia": "Europe", "ukraine": "Europe", "moldova": "Europe", "georgia": "Europe",
    "thailand": "Asia", "bangladesh": "Asia", "india": "Asia", "china": "Asia",
    "indonesia": "Asia", "pakistan": "Asia", "philippines": "Asia", "viet nam": "Asia",
    "vietnam": "Asia", "cambodia": "Asia", "myanmar": "Asia", "nepal": "Asia",
    "sri lanka": "Asia", "japan": "Asia", "republic of korea": "Asia", "korea": "Asia",
    "malaysia": "Asia", "mongolia": "Asia", "afghanistan": "Asia", "iran": "Asia",
    "iraq": "Asia", "jordan": "Asia", "lebanon": "Asia", "syria": "Asia",
    "turkey": "Asia", "kazakhstan": "Asia", "uzbekistan": "Asia",
    "kenya": "Africa", "ethiopia": "Africa", "nigeria": "Africa", "south africa": "Africa",
    "egypt": "Africa", "uganda": "Africa", "tanzania": "Africa", "ghana": "Africa",
    "senegal": "Africa", "cameroon": "Africa", "sudan": "Africa", "south sudan": "Africa",
    "somalia": "Africa", "zimbabwe": "Africa", "zambia": "Africa", "mozambique": "Africa",
    "malawi": "Africa", "rwanda": "Africa", "burundi": "Africa", "chad": "Africa",
    "niger": "Africa", "mali": "Africa", "libya": "Africa", "tunisia": "Africa",
    "morocco": "Africa", "algeria": "Africa", "congo": "Africa", "eswatini": "Africa",
    "brazil": "Latin America", "argentina": "Latin America", "chile": "Latin America",
    "colombia": "Latin America", "peru": "Latin America", "bolivia": "Latin America",
    "ecuador": "Latin America", "guatemala": "Latin America", "honduras": "Latin America",
    "haiti": "Latin America", "cuba": "Latin America", "panama": "Latin America",
    "uruguay": "Latin America", "paraguay": "Latin America", "venezuela": "Latin America",
    "australia": "Oceania", "new zealand": "Oceania", "fiji": "Oceania",
    "papua new guinea": "Oceania",
}

# Organisations whose communication, research or digital units match the
# profile particularly well (the site owner's own shortlist).
COMM_HEAVY_ORGS = {"un", "unesco", "unicef", "undp", "unwomen", "unhcr", "ohchr", "itu", "unep"}

AREA_LABELS = {
    "communication": ("communication", "传播"),
    "research": ("research", "研究"),
    "data": ("data", "数据"),
    "ai": ("AI", "人工智能"),
    "governance": ("digital governance", "数字治理"),
    "media": ("media", "传媒"),
    "policy": ("policy", "政策"),
}

# How strongly each direction matches the profile, out of the 30 direction
# points. Overlaps are the point: an opening touching three directions scores
# higher than one touching a single direction twice.
AREA_WEIGHTS = {
    "communication": 15,
    "research": 12,
    # Data and AI carry almost as much as research: computational
    # communication is one of the profile's own directions, so a post whose
    # title says "data analyst" is on-profile and not merely adjacent to it.
    "data": 14,
    "ai": 14,
    "governance": 10,
    "media": 9,
    "policy": 6,
}

# Bonus points are capped so that a perfect base score stays meaningful: the
# base can already reach 100, so the bonuses exist to lift an ordinary but
# well-fitting post, not to push everything into the top tier.
BONUS_CAP = 10


def compile_group(patterns: list[str]) -> re.Pattern:
    return re.compile("|".join(f"(?:{pattern})" for pattern in patterns), re.I)


AREA_RES = {area: compile_group(patterns) for area, patterns in AREA_KEYWORDS.items()}
EXCLUSION_RE = compile_group(EXCLUSION_KEYWORDS)
REMOTE_RE = compile_group(REMOTE_PATTERNS)
HYBRID_RE = compile_group(HYBRID_PATTERNS)
TYPE_RES = [(name, re.compile(pattern, re.I)) for name, pattern in TYPE_PATTERNS]
ELIGIBILITY_RES = {key: re.compile(pattern, re.I) for key, pattern in ELIGIBILITY_PATTERNS.items()}


def normalise_text(value: str) -> str:
    """Flatten HTML-ish text so the keyword groups see one clean line."""
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def hits(pattern: re.Pattern, text: str) -> int:
    return len(pattern.findall(text or ""))


def classify_type(title: str, description: str = "") -> str:
    """Internship > traineeship/fellowship > young professional > consultancy."""
    text = f"{title} {description[:400]}"
    for name, pattern in TYPE_RES:
        if pattern.search(title):
            return name
    for name, pattern in TYPE_RES:
        if pattern.search(text):
            return name
    return "other"


# Phrases that contain the word "communication" but mean something else. An ITU
# post about "information and communication technologies" is not a
# communication post, and counting it as one put cybersecurity internships at
# the top of the list. These are removed before the keyword groups run.
NOISE_PATTERNS = [
    r"information and communication technolog(?:y|ies)",
    r"information & communication technolog(?:y|ies)",
    r"\bict\b",
    r"telecommunication(?:s)?",
    # An organisation's own name is not a job direction. ITU is the
    # International Telecommunication Union and UNITAR the UN Institute for
    # Training and Research; left in place they make every ITU post look like
    # a communication post and every UNITAR post like a research post.
    r"international telecommunication union",
    r"institute for training and research",
    r"communication union",
    r"communication (?:equipment|infrastructure|network|technology|system|satellite|channel)s?\b",
    r"communication\s*/\s*(?:it|information technology)",
]
NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.I)


def strip_noise(text: str) -> str:
    """Blank out the false friends before the keyword groups read the text."""
    return NOISE_RE.sub(" ", text or "")


def match_areas(text: str) -> dict[str, int]:
    cleaned = strip_noise(text)
    return {area: hits(pattern, cleaned) for area, pattern in AREA_RES.items() if hits(pattern, cleaned)}


def match_topics(text: str) -> list[str]:
    lowered = strip_noise(text).lower()
    return [topic for topic in TOPIC_KEYWORDS if topic in lowered]


def extract_eligibility(text: str) -> dict:
    """What the opening says about who may apply."""
    found = {key: bool(pattern.search(text)) for key, pattern in ELIGIBILITY_RES.items()}
    return {
        "phd": found["phd"],
        "master": found["master"],
        "graduate": found["graduate"],
        "undergraduate_only": found["undergraduate_only"],
        "mentioned": any(found.values()),
    }


def extract_mode(text: str) -> str:
    if REMOTE_RE.search(text or ""):
        return "remote"
    if HYBRID_RE.search(text or ""):
        return "hybrid"
    return "onsite" if text else "unknown"


def parse_month(word: str) -> int:
    return MONTHS.get(word[:3].lower(), 0)


def expand_year(two_digit: int) -> int:
    """"Oct-7-26" means 2026, not 1926."""
    return 2000 + two_digit if two_digit <= 68 else 1900 + two_digit


def parse_date(text: str) -> str:
    """Return the first date in `text` as YYYY-MM-DD, or "" when none parses.

    Job boards print deadlines in at least four shapes, and a wrong deadline is
    worse than no deadline: the page hides an opening once it has passed, so an
    unparsed date simply leaves the opening open.
    """
    if not text:
        return ""
    for pattern, order in DATE_PATTERNS:
        for match in re.finditer(pattern, text, re.I):
            groups = match.groups()
            try:
                if order == "ymd":
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                elif order == "dmy_num":
                    day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                elif order == "dmy_short":
                    day, month, year = int(groups[0]), parse_month(groups[1]), expand_year(int(groups[2]))
                elif order == "mdy_short":
                    day, month, year = int(groups[1]), parse_month(groups[0]), expand_year(int(groups[2]))
                elif order == "dmy":
                    day, year, month = int(groups[0]), int(groups[2]), parse_month(groups[1])
                else:  # mdy
                    day, year, month = int(groups[1]), int(groups[2]), parse_month(groups[0])
            except (TypeError, ValueError):
                continue
            if not month:
                continue
            try:
                return date(year, month, day).isoformat()
            except ValueError:
                continue
    return ""


def extract_deadline(description: str) -> str:
    """Prefer a date that the text actually labels as the closing date."""
    text = normalise_text(description)
    for hint in DEADLINE_HINTS:
        for match in re.finditer(hint, text, re.I):
            window = text[match.end(): match.end() + 60]
            parsed = parse_date(window)
            if parsed:
                return parsed
    return ""


def days_left(deadline: str, today: date | None = None) -> int | None:
    if not deadline:
        return None
    try:
        target = datetime.strptime(deadline, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (target - (today or date.today())).days


def status_of(deadline: str, today: date | None = None) -> str:
    """open / closing (<= 7 days) / closed — never guesses without a date."""
    remaining = days_left(deadline, today)
    if remaining is None:
        return "open"
    if remaining < 0:
        return "closed"
    return "closing" if remaining <= 7 else "open"


DURATION_HINT_RE = re.compile(
    r"duration|period of|for a period|assignment|contract|tenure|last(?:s|ing)|initial", re.I
)


def extract_duration(text: str) -> str:
    """How long the assignment lasts.

    "5 years" on a job page is almost always experience, not the length of the
    post, so a year is only believed when the surrounding words talk about a
    duration. Months and weeks are unambiguous enough to take as they stand.
    """
    clean = normalise_text(text)
    for match in DURATION_RE.finditer(clean):
        first, second, unit = match.group(1), match.group(2), match.group(3)
        window = clean[max(0, match.start() - 60): match.end() + 20]
        if unit.lower().startswith("year") and not DURATION_HINT_RE.search(window):
            continue
        if second and second != first:
            return f"{first}-{second} {unit}"
        return f"{first} {unit}"
    return ""


def extract_stipend(text: str) -> dict:
    """Paid / unpaid / not stated, plus the amount if the page prints one.

    An unclear page stays "未说明": inventing a stipend would be worse than
    leaving the field empty.
    """
    clean = normalise_text(text)
    if any(re.search(pattern, clean, re.I) for pattern in UNPAID_PATTERNS):
        return {"paid": "unpaid", "amount": "", "note": "Unpaid"}
    amount_match = MONEY_RE.search(clean)
    paid = any(re.search(pattern, clean, re.I) for pattern in PAID_PATTERNS)
    if paid or amount_match:
        amount = amount_match.group(0).strip() if amount_match else ""
        return {"paid": "paid", "amount": amount, "note": amount or "Paid"}
    return {"paid": "unknown", "amount": "", "note": "未说明 / Not stated"}


def extract_language(text: str) -> str:
    match = LANGUAGE_RE.search(normalise_text(text))
    if not match:
        return ""
    return (match.group(1) or match.group(0)).strip()


def split_location(location: str) -> dict:
    """Split "Rome, Italy" into a city, a country and a region."""
    parts = [part.strip() for part in (location or "").split(",") if part.strip()]
    if not parts:
        return {"city": "", "country": "", "region": ""}
    city = parts[0]
    country = parts[-1] if len(parts) > 1 else parts[0]
    region = REGION_BY_COUNTRY.get(country.lower(), "")
    if not region:
        region = REGION_BY_COUNTRY.get(city.lower(), "")
    return {"city": city, "country": country, "region": region}


def is_priority_city(city: str) -> bool:
    return any(name in (city or "").lower() for name in PRIORITY_CITIES)


def _reason_pair(kind: str, *values: str) -> tuple[str, str]:
    """One reason, in English and in Chinese, built from fixed templates.

    The reasons are generated deliberately rather than translated: the page
    must read correctly in Chinese on the very first day, even when no
    translation provider is configured.
    """
    if kind == "area":
        area = values[0]
        en, zh = AREA_LABELS.get(area, (area, area))
        return (
            f"The post sits in {en}, which matches the profile directly.",
            f"岗位属于{zh}方向，与申请者背景直接对口。",
        )
    if kind == "topics":
        en_list, zh_list = values[0], values[1]
        return (
            f"The description covers {en_list}.",
            f"岗位职责涉及{zh_list}。",
        )
    if kind == "eligibility":
        return (
            "It accepts Master's / PhD students.",
            "明确接受硕士或博士在读学生。",
        )
    if kind == "phd":
        return (
            "Doctoral candidates are explicitly eligible.",
            "明确接受博士候选人申请。",
        )
    if kind == "remote":
        return (
            "The assignment can be carried out remotely.",
            "岗位支持远程工作。",
        )
    if kind == "hybrid":
        return (
            "The assignment allows a hybrid arrangement.",
            "岗位支持混合办公。",
        )
    if kind == "org":
        return (
            f"{values[0]} works on communication, research or digital policy here.",
            f"{values[0]}的本岗位方向与传播、研究或数字政策工作相关。",
        )
    if kind == "combo":
        return (
            f"It combines {values[0]}.",
            f"岗位同时涉及{values[1]}，属于交叉方向。",
        )
    if kind == "deadline":
        return (
            f"Applications close in {values[0]} days.",
            f"距离截止还有 {values[0]} 天。",
        )
    return ("", "")


TOPIC_ZH = {
    "social media": "社交媒体",
    "misinformation": "虚假信息",
    "disinformation": "虚假信息",
    "information integrity": "信息完整性",
    "journalism": "新闻业",
    "artificial intelligence": "人工智能",
    "digital platform": "数字平台",
    "algorithm": "算法",
    "online communication": "在线传播",
    "public opinion": "舆论",
    "audience": "受众",
    "digital society": "数字社会",
    "technology governance": "技术治理",
    "internet governance": "互联网治理",
    "digital transformation": "数字化转型",
    "information environment": "信息环境",
    "communication research": "传播研究",
    "public communication": "公共传播",
    "strategic communication": "战略传播",
    "global communication": "全球传播",
    "international communication": "国际传播",
    "computational method": "计算方法",
    "data analysis": "数据分析",
    "text analysis": "文本分析",
    "network analysis": "网络分析",
}


# --- Chinese labels ---------------------------------------------------------
# Everything below is written by hand rather than translated, so the Chinese
# page is complete the day this code ships even when no translation provider is
# configured. Only free text (the job title) is left to the translator.
TYPE_ZH = {
    "internship": "实习",
    "traineeship": "培训实习",
    "fellowship": "研究资助",
    "young_professional": "青年专业人员",
    "consultancy": "咨询顾问",
    "other": "其他",
}
TYPE_LABELS = {
    "internship": "Internship",
    "traineeship": "Traineeship",
    "fellowship": "Fellowship",
    "young_professional": "Young Professional",
    "consultancy": "Consultancy",
    "other": "Opening",
}
MODE_ZH = {"remote": "远程", "hybrid": "混合办公", "onsite": "现场办公", "unknown": "未说明"}
STATUS_ZH = {"open": "开放申请", "closing": "即将截止", "closed": "已截止", "unknown": "未说明"}
STIPEND_ZH = {"paid": "有津贴", "unpaid": "无津贴", "unknown": "津贴未说明"}
STIPEND_EN = {"paid": "Paid", "unpaid": "Unpaid", "unknown": "Stipend not stated"}
ELIGIBILITY_ZH = {
    "phd": "博士在读",
    "master": "硕士在读",
    "graduate": "应届毕业生",
    "undergraduate_only": "仅本科在读",
}
# Duty stations that appear often enough to be worth naming in Chinese.
COUNTRY_ZH = {
    "usa": "美国", "united states": "美国", "united states of america": "美国",
    "canada": "加拿大", "mexico": "墨西哥",
    "switzerland": "瑞士", "france": "法国", "austria": "奥地利", "italy": "意大利",
    "spain": "西班牙", "denmark": "丹麦", "germany": "德国", "netherlands": "荷兰",
    "belgium": "比利时", "sweden": "瑞典", "norway": "挪威", "finland": "芬兰",
    "united kingdom": "英国", "uk": "英国", "ireland": "爱尔兰", "poland": "波兰",
    "portugal": "葡萄牙", "greece": "希腊", "hungary": "匈牙利", "romania": "罗马尼亚",
    "serbia": "塞尔维亚", "ukraine": "乌克兰", "moldova": "摩尔多瓦", "georgia": "格鲁吉亚",
    "thailand": "泰国", "bangladesh": "孟加拉国", "india": "印度", "china": "中国",
    "indonesia": "印度尼西亚", "pakistan": "巴基斯坦", "philippines": "菲律宾",
    "viet nam": "越南", "vietnam": "越南", "cambodia": "柬埔寨", "myanmar": "缅甸",
    "nepal": "尼泊尔", "sri lanka": "斯里兰卡", "japan": "日本",
    "republic of korea": "韩国", "korea": "韩国", "malaysia": "马来西亚",
    "mongolia": "蒙古", "afghanistan": "阿富汗", "iran": "伊朗", "iraq": "伊拉克",
    "jordan": "约旦", "lebanon": "黎巴嫩", "syria": "叙利亚", "turkey": "土耳其",
    "kazakhstan": "哈萨克斯坦", "uzbekistan": "乌兹别克斯坦",
    "kenya": "肯尼亚", "ethiopia": "埃塞俄比亚", "nigeria": "尼日利亚",
    "south africa": "南非", "egypt": "埃及", "uganda": "乌干达", "tanzania": "坦桑尼亚",
    "ghana": "加纳", "senegal": "塞内加尔", "cameroon": "喀麦隆", "sudan": "苏丹",
    "south sudan": "南苏丹", "somalia": "索马里", "zimbabwe": "津巴布韦",
    "zambia": "赞比亚", "mozambique": "莫桑比克", "malawi": "马拉维", "rwanda": "卢旺达",
    "burundi": "布隆迪", "chad": "乍得", "niger": "尼日尔", "mali": "马里",
    "libya": "利比亚", "tunisia": "突尼斯", "morocco": "摩洛哥", "algeria": "阿尔及利亚",
    "congo": "刚果", "eswatini": "斯威士兰",
    "brazil": "巴西", "argentina": "阿根廷", "chile": "智利", "colombia": "哥伦比亚",
    "peru": "秘鲁", "bolivia": "玻利维亚", "ecuador": "厄瓜多尔", "guatemala": "危地马拉",
    "honduras": "洪都拉斯", "haiti": "海地", "cuba": "古巴", "panama": "巴拿马",
    "uruguay": "乌拉圭", "paraguay": "巴拉圭", "venezuela": "委内瑞拉",
    "australia": "澳大利亚", "new zealand": "新西兰", "fiji": "斐济",
    "papua new guinea": "巴布亚新几内亚",
}
CITY_ZH = {
    "new york": "纽约", "geneva": "日内瓦", "paris": "巴黎",
    "washington": "华盛顿", "washington, d.c.": "华盛顿", "vienna": "维也纳",
    "bangkok": "曼谷", "nairobi": "内罗毕", "copenhagen": "哥本哈根",
    "rome": "罗马", "brussels": "布鲁塞尔", "london": "伦敦", "berlin": "柏林",
    "madrid": "马德里", "amsterdam": "阿姆斯特丹", "stockholm": "斯德哥尔摩",
    "oslo": "奥斯陆", "helsinki": "赫尔辛基", "budapest": "布达佩斯", "warsaw": "华沙",
    "tokyo": "东京", "seoul": "首尔", "beijing": "北京", "shanghai": "上海",
    "hong kong": "中国香港", "singapore": "新加坡", "kuala lumpur": "吉隆坡",
    "jakarta": "雅加达", "manila": "马尼拉", "delhi": "德里", "new delhi": "新德里",
    "cairo": "开罗", "addis ababa": "亚的斯亚贝巴", "dakar": "达喀尔",
    "johannesburg": "约翰内斯堡", "pretoria": "比勒陀利亚", "accra": "阿克拉",
    "kampala": "坎帕拉", "dar es salaam": "达累斯萨拉姆", "lagos": "拉各斯",
    "mexico city": "墨西哥城", "bogota": "波哥大", "lima": "利马",
    "santiago": "圣地亚哥", "buenos aires": "布宜诺斯艾利斯",
    "sao paulo": "圣保罗", "rio de janeiro": "里约热内卢",
    "sydney": "悉尼", "melbourne": "墨尔本", "canberra": "堪培拉",
    "doha": "多哈", "dubai": "阿联酋迪拜", "abu dhabi": "阿布扎比",
    "istanbul": "伊斯坦布尔", "ankara": "安卡拉", "moscow": "莫斯科",
    "home-based": "远程（居家）", "home": "远程（居家）", "remote": "远程",
    "multiple": "多个地点", "multiple locations": "多个地点",
    "various locations": "多个地点", "10 locations": "多个地点",
}


REMOTE_PLACE_RE = re.compile(r"home[- ]based|home\b|remote|virtual", re.I)


def location_zh(city: str, country: str) -> str:
    """"Paris, France" -> "法国巴黎"; unknown places keep their own spelling."""
    if REMOTE_PLACE_RE.search(f"{city} {country}"):
        return "远程（居家）"
    city_zh = CITY_ZH.get((city or "").strip().lower(), "")
    country_zh = COUNTRY_ZH.get((country or "").strip().lower(), "")
    if city_zh and country_zh and city_zh != country_zh:
        return f"{country_zh}{city_zh}"
    if country_zh:
        return country_zh
    if city_zh:
        return city_zh
    return ", ".join(part for part in (city, country) if part)


# Titles that carry their duty station as free prose — UNICEF writes
# "Planning, Monitoring and Evaluation Internship, Mbabane, Eswatini" — are
# matched against the known countries and cities instead of guessed at.
PLACE_STOPWORDS = {
    "home-based", "home", "remote", "multiple", "multiple locations",
    "various locations", "10 locations", "virtual",
}
PLACE_CITIES = sorted((name for name in CITY_ZH if name not in PLACE_STOPWORDS and len(name) > 3), key=len, reverse=True)
PLACE_COUNTRIES = sorted(REGION_BY_COUNTRY, key=len, reverse=True)
_COUNTRY_RE = re.compile(r"\b(" + "|".join(re.escape(name) for name in PLACE_COUNTRIES) + r")\b", re.I)
_CITY_RE = re.compile(r"\b(" + "|".join(re.escape(name) for name in PLACE_CITIES) + r")\b", re.I)


def place_from_text(text: str) -> str:
    """Pull a duty station out of a free-text title when nothing else has one."""
    match = _COUNTRY_RE.search(text or "")
    if match:
        country = match.group(1)
        preceding = re.search(r"([A-Z][\w.'-]*(?:[ \-][A-Z][\w.'-]*){0,2})\s*,\s*$", text[: match.start()])
        city = preceding.group(1).strip() if preceding else ""
        return f"{city}, {country}" if city else country
    city_match = _CITY_RE.search(text or "")
    return city_match.group(1) if city_match else ""


def areas_zh(areas: list[str]) -> str:
    return "、".join(AREA_LABELS.get(area, (area, area))[1] for area in areas)


def score_opening(
    title: str,
    description: str = "",
    org_code: str = "",
    org_priority: int = 2,
    department: str = "",
    location: str = "",
    today: date | None = None,
) -> dict:
    """Turn one opening into its classified fields, score and reasons."""
    clean_title = normalise_text(title)
    body = normalise_text(description)
    text = f"{clean_title} {body}"

    type_name = classify_type(clean_title, body)
    title_areas = match_areas(clean_title)
    body_areas = match_areas(body)
    areas = {area: title_areas.get(area, 0) + body_areas.get(area, 0) for area in set(title_areas) | set(body_areas)}
    topics = match_topics(body)
    eligibility = extract_eligibility(text)
    mode = extract_mode(text)
    deadline = extract_deadline(text)
    stipend = extract_stipend(text)
    duration = extract_duration(text)
    language = extract_language(text)
    place = split_location(location)
    # An off-profile post is judged on its title: a finance or HR internship
    # whose boilerplate happens to mention communication is still a finance
    # internship, so the escape hatch looks at the title's own direction, not
    # at words buried in the description.
    excluded = bool(EXCLUSION_RE.search(clean_title)) and not title_areas

    # --- direction (30) ---
    direction = sum(AREA_WEIGHTS.get(area, 0) for area in areas)
    if len(areas) >= 3:
        direction += 3  # an interdisciplinary post is worth more than a narrow one
    direction = min(direction, 30)

    # --- function (25) ---
    function = 0
    if title_areas:
        function += 12
    if len(title_areas) >= 2:
        function += 5
    if body_areas:
        function += 8
    elif title_areas:
        # An opening whose title already names its direction is not made
        # weaker by a short description: feeds often carry only a title, and
        # "Data Analyst Intern" says enough on its own.
        function += 5
    if len(topics) >= 3:
        function += 3
    function += {"internship": 5, "traineeship": 4, "fellowship": 4, "young_professional": 3}.get(type_name, 0)
    function = min(function, 25)

    # --- topics (20) ---
    topic_score = min(len(topics) * 5, 20)

    # --- eligibility (15) ---
    if not eligibility["mentioned"]:
        eligibility_score = 10  # nothing said: neutral, do not punish the post
    else:
        eligibility_score = 6
        if eligibility["master"]:
            eligibility_score += 4
        if eligibility["phd"]:
            eligibility_score += 4
        if eligibility["graduate"]:
            eligibility_score += 2
    if eligibility["undergraduate_only"]:
        eligibility_score -= 6
    eligibility_score = max(min(eligibility_score, 15), 0)

    # --- mode and place (5) ---
    mode_score = {"remote": 5, "hybrid": 4, "onsite": 3}.get(mode, 2)
    if is_priority_city(place.get("city", "")):
        mode_score += 1
    mode_score = min(mode_score, 5)

    # --- organisation (5) ---
    org_score = {1: 5, 2: 4, 3: 3}.get(org_priority, 3)
    if org_code in COMM_HEAVY_ORGS:
        org_score += 1
    org_score = min(org_score, 5)

    # The total is taken after the caps below, not here: a cap that changed
    # `direction` or `function` after the sum had been taken would change
    # nothing at all.
    score = 0

    # --- bonuses -------------------------------------------------------
    bonus = 0
    reasons: list[tuple[str, str]] = []
    combos: list[tuple[str, str]] = []
    if "communication" in areas and "data" in areas:
        bonus += 5
        combos.append(("communication and data analysis", "传播与数据分析"))
    if "communication" in areas and "ai" in areas:
        bonus += 5
        combos.append(("communication and artificial intelligence", "传播与人工智能"))
    if "communication" in areas and "research" in areas:
        bonus += 4
        combos.append(("communication and research", "传播与研究"))
    if re.search(r"digital communication|strategic communication|public information", text, re.I):
        bonus += 3
        combos.append(("digital or strategic communication", "数字传播与战略传播"))
    if re.search(r"information integrity|misinformation|disinformation", text, re.I):
        bonus += 5
        combos.append(("information integrity work", "信息完整性与虚假信息治理"))
    if re.search(r"social media analytics|audience analytics", text, re.I):
        bonus += 4
        combos.append(("social media analytics", "社交媒体分析"))
    if re.search(r"digital governance|internet governance|platform governance|ai governance", text, re.I):
        bonus += 4
        combos.append(("digital governance", "数字治理"))
    if re.search(r"media development|freedom of expression", text, re.I):
        bonus += 3
        combos.append(("media development", "媒体发展"))
    # A data or AI post counts even when the title never says "communication"
    # (the profile covers computational communication), so it is lifted rather
    # than dropped on the strength of those areas alone.
    if "data" in areas or "ai" in areas:
        bonus += 4
        combos.append(("data or AI work", "数据与人工智能工作"))
    if eligibility["phd"]:
        bonus += 4
    if mode == "remote":
        bonus += 3
    if org_code in COMM_HEAVY_ORGS and areas:
        bonus += 3

    # --- penalties -----------------------------------------------------
    if type_name == "consultancy":
        bonus -= 12
    if excluded:
        bonus -= 20
    # What the title says outranks what the boilerplate mentions in passing.
    # Every long description contains "communication", "research" or "data"
    # somewhere — as a required skill, as an organisation's name, as a
    # procedure — so a body hit alone may only ever add a little. A post whose
    # title names no relevant direction reaches the middle of the range only
    # when its description carries a topic of its own, and otherwise stays
    # below the cut-off: the promise is to miss an unrelated post rather than
    # to admit a finance or engineering internship.
    if title_areas:
        pass  # the title decides what the post is about
    elif topics:
        direction = min(direction, 20)
        function = min(function, 16)
        bonus = min(bonus, 5)
    else:
        direction = min(direction, 10)
        function = min(function, 10)
        bonus = min(bonus, 2)
    bonus = max(min(bonus, BONUS_CAP), -20)

    score = max(
        min(
            direction + function + topic_score + eligibility_score + mode_score + org_score + bonus,
            100,
        ),
        0,
    )

    # --- reasons (up to three, strongest signal first) ------------------
    ranked = sorted(areas.items(), key=lambda pair: AREA_WEIGHTS.get(pair[0], 0), reverse=True)
    if ranked:
        reasons.append(_reason_pair("area", ranked[0][0]))
    if topics:
        shown = topics[:3]
        reasons.append(
            _reason_pair(
                "topics",
                ", ".join(shown),
                "、".join(TOPIC_ZH.get(topic, topic) for topic in shown),
            )
        )
    if eligibility["phd"]:
        reasons.append(_reason_pair("phd"))
    elif eligibility["master"] or eligibility["graduate"]:
        reasons.append(_reason_pair("eligibility"))
    for combo in combos[:1]:
        reasons.append(_reason_pair("combo", combo[0], combo[1]))
    if mode == "remote":
        reasons.append(_reason_pair("remote"))
    elif mode == "hybrid":
        reasons.append(_reason_pair("hybrid"))
    if org_code in COMM_HEAVY_ORGS and len(reasons) < 3:
        reasons.append(_reason_pair("org", org_code.upper()))

    remaining = days_left(deadline, today)
    status = status_of(deadline, today)
    if status == "closing" and remaining is not None and len(reasons) < 3:
        reasons.append(_reason_pair("deadline", str(remaining)))

    reasons = [pair for pair in reasons if pair[0]][:3]

    return {
        "type": type_name,
        "areas": sorted(areas.keys()),
        "score": score,
        "tier": tier_of(score),
        "tier_zh": tier_zh(score),
        "reasons": [pair[0] for pair in reasons],
        "reasons_zh": [pair[1] for pair in reasons],
        "mode": mode,
        "deadline": deadline,
        "days_left": remaining,
        "status": status,
        "duration": duration,
        "stipend": stipend["paid"],
        "stipend_amount": stipend["amount"],
        "stipend_note": stipend["note"],
        "eligibility": [key for key in ("phd", "master", "graduate", "undergraduate_only") if eligibility[key]],
        "phd_ok": eligibility["phd"],
        "language": language,
        "excluded": excluded,
        "city": place["city"],
        "country": place["country"],
        "region": place["region"],
    }


def tier_of(score: int) -> str:
    if score >= 90:
        return "exceptional"
    if score >= 80:
        return "high"
    if score >= 70:
        return "good"
    if score >= MIN_SCORE:
        return "possible"
    return "hidden"


def tier_zh(score: int) -> str:
    return {
        "exceptional": "极高匹配",
        "high": "高度匹配",
        "good": "较高匹配",
        "possible": "可考虑",
        "hidden": "不予展示",
    }[tier_of(score)]


TIER_EN = {
    "exceptional": "Exceptional match",
    "high": "Strong match",
    "good": "Good match",
    "possible": "Worth a look",
    "hidden": "Not shown",
}


def tier_en(score: int) -> str:
    return TIER_EN[tier_of(score)]


def dedupe_key(org_code: str, job_id: str, url: str, title: str) -> tuple[str, str]:
    """Two keys for one opening: a stable id and a human-readable fallback.

    A job id is authoritative — the same post listed on the organisation's own
    site and on an aggregator carries the same id. Without one we fall back to
    the organisation plus a normalised title, and finally to the URL, because
    the archive is append-only and a duplicate would live there for months.
    """
    identity = ""
    if job_id:
        identity = f"{org_code}:{job_id}"
    url_clean = re.sub(r"[#?].*$", "", (url or "").rstrip("/").lower())
    if not identity:
        slug = re.sub(r"[^a-z0-9]+", "", (title or "").lower())
        identity = f"{org_code}:{slug}" if slug else url_clean
    return identity, (url_clean or identity)

import asyncio
import html
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from hashlib import sha1
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag
from dotenv import load_dotenv
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "1800"))
SEND_EXISTING = os.getenv("SEND_EXISTING", "0") == "1"
HEADLESS = os.getenv("HEADLESS", "1") == "1"
DEBUG = os.getenv("DEBUG", "0") == "1"

DB_FILE = os.getenv("DB_FILE", "banks_promos.db")
SOURCES_FILE = os.getenv("SOURCES_FILE", "sources.json")
BROWSER_PROFILE_DIR = os.getenv("BROWSER_PROFILE_DIR", "browser_profile")
PAGE_WAIT_MS = int(os.getenv("PAGE_WAIT_MS", "4500"))
MAX_ITEMS_PER_SOURCE = int(os.getenv("MAX_ITEMS_PER_SOURCE", "25"))

DATE_RE = re.compile(
    r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}[./-]\d{1,2}[./-]\d{1,2})"
)

UA_MONTH_DATE_RE = re.compile(
    r"\d{1,2}\s+"
    r"(?:січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня|"
    r"января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"
    r"\s+\d{4}\s*р?\.?",
    re.IGNORECASE,
)

SECURITY_MARKERS = [
    "Additional security check",
    "Request unsuccessful",
    "Incapsula incident ID",
    "Why am I seeing this page?",
    "hCaptcha",
    "Imperva",
    "Just a moment",
    "Performing security verification",
    "security verification",
    "Cloudflare",
    "Ray ID",
]

PROMO_KEYWORDS = [
    "акці",
    "акция",
    "акційн",
    "зниж",
    "скидк",
    "кешбек",
    "cashback",
    "спецпропоз",
    "спеціальна пропозиція",
    "специальное предложение",
    "пропозиці",
    "предложени",
    "бонус",
    "подар",
    "розіграш",
    "розыгрыш",
    "вигра",
    "выигр",
    "перемаг",
    "промокод",
    "promo",
    "sale",
    "black friday",
    "mastercard",
    "master card",
    "visa",
    "карт",
    "депозит",
    "вклад",
    "розстроч",
    "рассроч",
    "партнер",
    "розігру",
    "винагород",
    "оплатою частинами",
    "оплата частинами",
    "переказ",
    "перекази",
    "вигідн",
    "економ",
    "заощадж",
    "безкоштов",
    "приз",
    "грн за",
    "uah",
    "loyalty",
    "loyalty program",
]

STRONG_PROMO_KEYWORDS = [
    "акці",
    "зниж",
    "кешбек",
    "cashback",
    "спецпропоз",
    "спеціальна пропозиція",
    "розіграш",
    "вигра",
    "перемаг",
    "промокод",
    "подар",
    "бонус",
    "розігру",
    "винагород",
    "оплатою частинами",
    "оплата частинами",
    "вигідн",
    "економ",
    "заощадж",
    "безкоштов",
    "грн за",
    "uah",
]

PRIVATE_KEYWORDS = [
    "приватн",
    "фізич",
    "физичес",
    "клієнт",
    "клиент",
    "покуп",
    "карт",
    "кешбек",
    "cashback",
    "депозит",
    "вклад",
    "магазин",
    "подорож",
    "путешеств",
    "рестора",
    "аптек",
    "пальн",
    "топлив",
    "квитк",
    "білет",
    "переказ",
    "перекази",
    "технік",
    "відпоч",
]

NEGATIVE_KEYWORDS = [
    "графік роботи",
    "график работы",
    "технічні роботи",
    "технические работы",
    "регламент",
    "зміни тариф",
    "изменение тариф",
    "звіт",
    "отчет",
    "фінансов",
    "финансов",
    "акціонер",
    "акционер",
    "ваканс",
    "тендер",
    "облігац",
    "облигац",
    "збори акціонерів",
    "собрание акционеров",
    "відключення",
    "отключение",
    "профілактич",
    "профилактич",
    "корпоративн",
    "юридич",
    "юридичес",
    "бізнесу",
    "бизнесу",
    "мсб",
    "акцію завершено",
    "акция завершена",
    "завершено",
]

TITLE_NEGATIVE_KEYWORDS = [
    "графік роботи",
    "технічні роботи",
    "зміни тариф",
    "звіт",
    "акціонер",
    "ваканс",
    "тендер",
    "облігац",
    "відключення",
    "профілактич",
    "корпоративн",
    "акцію завершено",
    "завершено",
]

NAV_TITLES = {
    "головна",
    "новини",
    "акції",
    "акции",
    "акції банку",
    "про банк",
    "контакти",
    "private individuals",
    "приватним особам",
    "business",
    "ua",
    "en",
    "ru",
    "...",
}

GENERIC_LINK_TITLES = {
    "детальніше",
    "детальнiше",
    "докладніше",
    "докладнiше",
    "читати новину",
    "читати більше",
    "читати бiльше",
    "читати",
    "перейти",
    "деталі",
    "деталi",
    "подробнее",
    "далі",
    "далi",
    "details",
    "more",
    "read more",
}

FILTER_TITLES = {
    "всі категорії",
    "усі категорії",
    "всі акції",
    "усі акції",
    "архів акцій",
    "архів",
    "постійні",
    "преміум",
    "бізнесу",
    "корпоративним клієнтам",
    "приватним особам",
    "преміум клієнтам",
    "юніорам",
    "фоп",
    "малий бізнес",
    "оформити депозит онлайн",
    "оформити картку онлайн",
    "відправити заявку на картку",
    "відправити заявку",
    "пресцентр",
    "прес-центр",
    "всі новини",
    "архів новин",
    "інформація для клієнтів",
    "діючі акції",
    "акції партнерів",
    "завершені акцїї",
    "завершені акції",
    "архівні акції",
    "підпишіться",
    "підписатися",
    "ваш e-mail",
    "всього знайдено акцій",
}

TEXT_ADAPTER_SOURCES = {
    "creditdnepr",
    "globusbank",
    "procreditbank",
    "universalbank",
    "otpbank",
    "credit_agricole",
    "pumb",
}

LINK_ADAPTER_SOURCES = {
    "credit_agricole",
    "otpbank",
    "procreditbank",
    "universalbank",
}

DEDICATED_ADAPTER_SOURCES = {
    "creditdnepr",
    "globusbank",
    "procreditbank",
    "universalbank",
    "otpbank",
    "credit_agricole",
    "pumb",
}

TEXT_ADAPTER_REQUIRES_LINK = {
    "creditdnepr",
    "globusbank",
    "universalbank",
    "otpbank",
    "credit_agricole",
    "pumb",
}

TEXT_ADAPTER_BREAKS_ON_NEXT_TITLE = {
    "globusbank",
    "procreditbank",
    "otpbank",
    "credit_agricole",
}

STRICT_ZERO_ITEM_SOURCES = {
    "creditdnepr",
    "globusbank",
    "procreditbank",
    "universalbank",
    "otpbank",
    "credit_agricole",
    "pumb",
}

CONTENT_PATH_HINTS = [
    "news",
    "nov",
    "novini",
    "novyny",
    "promo",
    "promotions",
    "offers",
    "offer",
    "akci",
    "akts",
    "akc",
    "action",
    "actions",
    "special",
    "stores",
    "blog",
    "press",
    "category",
]

SERVICE_PATH_PARTS = [
    "contacts",
    "contact",
    "career",
    "vacancy",
    "login",
    "auth",
    "search",
    "map",
    "sitemap",
    "privacy",
    "cookie",
    "offices",
    "atm",
    "requisites",
    "management",
    "financial-reports",
]

NOISE_TAGS = {"header", "footer", "nav", "aside"}
NOISE_CLASS_HINTS = [
    "header",
    "footer",
    "navbar",
    "nav",
    "menu",
    "breadcrumb",
    "pagination",
    "social",
    "cookie",
    "modal",
    "sidebar",
]

CARD_CLASS_HINTS = [
    "card",
    "item",
    "news",
    "promo",
    "offer",
    "post",
    "article",
    "publication",
    "blog",
    "action",
    "stock",
    "tile",
    "slide",
]


@dataclass
class Source:
    id: str
    name: str
    url: str
    kind: str
    allowed_hosts: list[str]
    path_hints: list[str]
    root_cards: bool = False
    allow_external_cards: bool = False


@dataclass
class Item:
    source_id: str
    bank_name: str
    source_url: str
    item_url: str
    title: str
    date: str = ""
    summary: str = ""
    is_promo: bool = False
    score: int = 0
    reason: str = ""


def clean_text(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def debug(message: str) -> None:
    if DEBUG:
        print(message)


def now_ts() -> int:
    return int(time.time())


def init_db() -> None:
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                bank_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                item_url TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                date_text TEXT,
                summary TEXT,
                status TEXT NOT NULL,
                is_promo INTEGER NOT NULL,
                score INTEGER NOT NULL,
                reason TEXT,
                first_seen_at INTEGER NOT NULL,
                processed_at INTEGER NOT NULL,
                sent_at INTEGER,
                error TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_status ON items(status)")


def total_seen_items() -> int:
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("SELECT COUNT(*) FROM items").fetchone()
        return int(row[0])


def total_seen_items_for_source(source_id: str) -> int:
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("SELECT COUNT(*) FROM items WHERE source_id = ?", (source_id,)).fetchone()
        return int(row[0])


def was_seen(item_url: str) -> bool:
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("SELECT 1 FROM items WHERE item_url = ?", (item_url,)).fetchone()
    return row is not None


def save_item(item: Item, status: str, error: str = "") -> None:
    sent_at = now_ts() if status == "sent" else None

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO items (
                source_id, bank_name, source_url, item_url, title, date_text,
                summary, status, is_promo, score, reason, first_seen_at,
                processed_at, sent_at, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.source_id,
                item.bank_name,
                item.source_url,
                item.item_url,
                item.title,
                item.date,
                item.summary,
                status,
                1 if item.is_promo else 0,
                item.score,
                item.reason,
                now_ts(),
                now_ts(),
                sent_at,
                error,
            ),
        )


def load_sources() -> list[Source]:
    with open(SOURCES_FILE, "r", encoding="utf-8") as file:
        raw_sources: list[dict[str, Any]] = json.load(file)

    sources = []
    for raw in raw_sources:
        host = urlparse(raw["url"]).netloc.lower()
        host_without_www = host[4:] if host.startswith("www.") else host
        allowed_hosts = raw.get("allowed_hosts") or [host, host_without_www, f"www.{host_without_www}"]

        sources.append(
            Source(
                id=raw["id"],
                name=raw["name"],
                url=raw["url"],
                kind=raw.get("kind", "news"),
                allowed_hosts=[h.lower() for h in allowed_hosts],
                path_hints=[hint.lower() for hint in raw.get("path_hints", [])],
                root_cards=bool(raw.get("root_cards", False)),
                allow_external_cards=bool(raw.get("allow_external_cards", False)),
            )
        )

    return sources


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc.lower(),
            path,
            "",
            urlencode(query),
            parsed.fragment,
        )
    )


def same_allowed_host(url: str, source: Source) -> bool:
    host = urlparse(url).netloc.lower()
    return not host or host in source.allowed_hosts


def host_allowed_for_item(url: str, source: Source) -> bool:
    return same_allowed_host(url, source) or source.allow_external_cards


def source_base_path(source: Source) -> str:
    path = urlparse(source.url).path.lower().rstrip("/")
    if path.endswith(".html") or path.endswith(".htm"):
        path = path.rsplit("/", 1)[0]
    return path


def is_bad_href(href: str) -> bool:
    lower = href.lower().strip()
    return (
        not lower
        or lower.startswith("#")
        or lower.startswith("mailto:")
        or lower.startswith("tel:")
        or lower.startswith("javascript:")
        or lower.endswith(".pdf")
        or lower.endswith(".doc")
        or lower.endswith(".docx")
        or lower.endswith(".xls")
        or lower.endswith(".xlsx")
    )


def is_inside_noise_area(tag: Tag) -> bool:
    for parent in [tag, *list(tag.parents)]:
        if not isinstance(parent, Tag):
            continue

        if parent.name in NOISE_TAGS:
            return True

        classes = " ".join(parent.get("class", [])).lower()
        element_id = str(parent.get("id", "")).lower()
        marker = f"{classes} {element_id}"

        if any(hint in marker for hint in NOISE_CLASS_HINTS):
            return True

    return False


def has_card_hint(tag: Tag) -> bool:
    for parent in [tag, *list(tag.parents)[:5]]:
        if not isinstance(parent, Tag):
            continue

        if parent.name in {"article", "li"}:
            return True

        classes = " ".join(parent.get("class", [])).lower()
        element_id = str(parent.get("id", "")).lower()
        marker = f"{classes} {element_id}"

        if any(hint in marker for hint in CARD_CLASS_HINTS):
            return True

    return False


def has_content_path_hint(source: Source, item_url: str) -> bool:
    path = urlparse(item_url).path.lower().rstrip("/")
    base_path = source_base_path(source)

    if base_path and base_path != "/" and path.startswith(base_path + "/"):
        return True

    hints = set(CONTENT_PATH_HINTS) | set(source.path_hints)
    return any(hint and hint in path for hint in hints)


def is_probably_year_filter(text: str) -> bool:
    parts = text.split()
    if len(parts) < 4:
        return False
    years = [part for part in parts if part.isdigit() and 2000 <= int(part) <= 2100]
    return len(years) >= 4 and len(years) >= len(parts) // 2


def looks_like_url_or_code(text: str) -> bool:
    lower = text.lower().strip()
    return (
        lower.startswith("[")
        or lower.startswith("{")
        or lower.endswith("]")
        or lower.endswith("}")
        or bool(re.fullmatch(r"(?:https?://)?(?:www\.)?[\w.-]+\.[a-z]{2,}(?:/.*)?", lower))
        or bool(re.fullmatch(r"[\w.-]+@[\w.-]+\.[a-z]{2,}", lower))
    )


def is_filter_or_archive_link(source: Source, item_url: str, title: str) -> bool:
    parsed = urlparse(item_url)
    source_parsed = urlparse(source.url)
    path = parsed.path.lower().rstrip("/") or "/"
    source_path = source_parsed.path.lower().rstrip("/") or "/"
    lower_title = title.lower().strip()

    if lower_title.startswith("#") or lower_title in FILTER_TITLES:
        return True

    if path == source_path and parsed.query:
        return True

    query = parsed.query.lower()
    return "archive=" in query or "searchtag=" in query or "filter=" in query


def has_service_path(item_url: str) -> bool:
    path = urlparse(item_url).path.lower()
    return any(part in path for part in SERVICE_PATH_PARTS)


def synthetic_url(source: Source, title: str, text: str) -> str:
    digest = sha1(f"{source.id}|{title}|{text[:500]}".encode("utf-8")).hexdigest()[:16]
    return normalize_url(f"{source.url.rstrip('/')}#promo-{digest}")


def is_security_page(page_html: str) -> bool:
    page_lower = page_html.lower()
    return any(marker.lower() in page_lower for marker in SECURITY_MARKERS)


def find_item_container(link: Tag) -> Tag:
    best = link

    for parent in link.parents:
        if not isinstance(parent, Tag):
            continue

        if parent.name in {"html", "body", "main"}:
            break

        if is_inside_noise_area(parent):
            break

        text = clean_text(parent.get_text(" ", strip=True))
        if not text:
            continue

        if len(text) <= 2200:
            best = parent

        if has_card_hint(parent) and 30 <= len(text) <= 2200:
            return parent

        if DATE_RE.search(text) and 40 <= len(text) <= 2200:
            return parent

        if UA_MONTH_DATE_RE.search(text) and 40 <= len(text) <= 2200:
            return parent

    return best


def title_candidates(link: Tag | None, container: Tag) -> list[str]:
    candidates = []

    if link:
        candidates.append(clean_text(link.get_text(" ", strip=True)))

    for selector in [
        "h1",
        "h2",
        "h3",
        "h4",
        ".title",
        ".name",
        "[class*='title']",
        "[class*='name']",
    ]:
        for node in container.select(selector)[:3]:
            candidates.append(clean_text(node.get_text(" ", strip=True)))

    text = clean_text(container.get_text(" ", strip=True))
    if text:
        for part in re.split(r"\s{2,}|(?<=\.)\s+", text):
            part = clean_text(part)
            if part:
                candidates.append(part)
                break

    return candidates


def pick_title(link: Tag | None, container: Tag) -> str:
    for candidate in title_candidates(link, container):
        lower = candidate.lower()
        if (
            5 <= len(candidate) <= 220
            and lower not in NAV_TITLES
            and lower not in GENERIC_LINK_TITLES
            and lower not in FILTER_TITLES
            and not candidate.isdigit()
        ):
            return candidate

    return ""


def is_plausible_title(text: str) -> bool:
    lower = text.lower().strip()
    return (
        5 <= len(text) <= 240
        and lower not in NAV_TITLES
        and lower not in GENERIC_LINK_TITLES
        and lower not in FILTER_TITLES
        and not text.isdigit()
        and not is_probably_year_filter(text)
        and not looks_like_url_or_code(text)
        and not lower.startswith("image:")
    )


def extract_date(text: str) -> str:
    match = DATE_RE.search(text)
    if match:
        return match.group(0)

    match = UA_MONTH_DATE_RE.search(text)
    if match:
        return match.group(0)

    return ""


def strip_dates_from_title(text: str) -> str:
    text = DATE_RE.sub(" ", text)
    text = UA_MONTH_DATE_RE.sub(" ", text)
    text = re.sub(r"^\s*[-–—]+\s*", "", text)
    text = re.sub(r"\s*[-–—]+\s*$", "", text)
    return clean_text(text)


def strip_generic_suffix(text: str) -> str:
    result = clean_text(text)
    for generic in sorted(GENERIC_LINK_TITLES, key=len, reverse=True):
        result = clean_text(re.sub(rf"\s+{re.escape(generic)}\s*$", "", result, flags=re.IGNORECASE))
    return result


def normalize_title_text(text: str) -> str:
    return strip_dates_from_title(strip_generic_suffix(text))


def find_matching_link(source: Source, soup: BeautifulSoup, title: str) -> str:
    title_lower = title.lower()

    for link in soup.find_all("a", href=True):
        link_text = clean_text(link.get_text(" ", strip=True))
        link_lower = link_text.lower()

        if not link_text:
            continue

        if link_lower in GENERIC_LINK_TITLES:
            continue

        if not (link_lower in title_lower or title_lower in link_lower):
            continue

        href = str(link.get("href", "")).strip()
        if is_bad_href(href):
            continue

        absolute_url = urljoin(source.url, href)
        if not host_allowed_for_item(absolute_url, source):
            continue

        item_url = normalize_url(absolute_url)
        if item_url == normalize_url(source.url):
            continue

        if is_filter_or_archive_link(source, item_url, title):
            continue

        return item_url

    return ""


def find_line_index(lines: list[str], marker: str, use_last: bool = False, exact: bool = False) -> int:
    marker_lower = marker.lower()
    found = -1

    for index, line in enumerate(lines):
        lower = line.lower()
        matched = lower == marker_lower if exact else marker_lower in lower
        if matched:
            found = index
            if not use_last:
                break

    return found


def content_lines_for_source(source: Source, lines: list[str]) -> list[str]:
    start = 0
    stop = len(lines)

    if source.id == "globusbank":
        index = find_line_index(lines, "Акції та програми лояльності", use_last=True)
        if index >= 0:
            start = index + 1
        stop_index = find_line_index(lines[start:], "ФГВФО")
        if stop_index >= 0:
            stop = start + stop_index

    elif source.id == "otpbank":
        index = find_line_index(lines, "Всього знайдено акцій")
        if index >= 0:
            start = index + 1
        stop_index = find_line_index(lines[start:], "Підпишіться")
        if stop_index >= 0:
            stop = start + stop_index

    elif source.id == "credit_agricole":
        index = find_line_index(lines, "Рік  2026")
        if index < 0:
            index = find_line_index(lines, "Рік 2026")
        if index < 0:
            index = find_line_index(lines, "Прес-центр", use_last=True)
        if index >= 0:
            start = index + 1
        stop_index = find_line_index(lines[start:], "Показати більше")
        if stop_index >= 0:
            stop = start + stop_index

    elif source.id == "pumb":
        index = find_line_index(lines, "Акції", use_last=True, exact=True)
        if index >= 0:
            start = index + 1
        stop_index = find_line_index(lines[start:], "Підтримка клієнтів")
        if stop_index >= 0:
            stop = start + stop_index

    elif source.id == "creditdnepr":
        index = find_line_index(lines, "Акції", exact=True)
        if index >= 0:
            start = index + 1

    elif source.id == "procreditbank":
        index = find_line_index(lines, "Акційні пропозиції", use_last=True)
        if index >= 0:
            start = index + 1

    elif source.id == "universalbank":
        index = find_line_index(lines, "Акції", use_last=True)
        if index >= 0:
            start = index + 1

    return lines[start:stop]


def likely_text_item_start(source: Source, line: str) -> bool:
    if not is_plausible_title(line):
        return False

    lower = line.lower()
    if any(word in lower for word in TITLE_NEGATIVE_KEYWORDS):
        return False

    if source.id == "creditdnepr":
        return any(
            marker in lower
            for marker in [
                "акція",
                "призупинення",
                "зміна умов",
                "подовження строку",
            ]
        )

    if source.id == "globusbank":
        return any(
            marker in lower
            for marker in [
                "детальніше",
                "mastercard",
                "вигода",
                "розіграш",
                "lounge",
                "купуй",
                "кордонів",
            ]
        )

    if source.id == "procreditbank":
        return any(
            token in lower
            for token in [
                "uah",
                "депозит",
                "програма",
                "пропозиція",
                "активність",
                "винагороду",
                "реферальна",
                "запросіть бізнес",
            ]
        )

    if source.id == "universalbank":
        return any(word in lower for word in STRONG_PROMO_KEYWORDS)

    if source.id == "otpbank":
        return bool(DATE_RE.search(line)) and not any(marker in lower for marker in ["завершені", "архівні"])

    if source.id == "credit_agricole":
        return bool(UA_MONTH_DATE_RE.search(line)) and not any(marker in lower for marker in ["місяць", "показати"])

    if source.id == "pumb":
        if any(
            lower.startswith(prefix)
            for prefix in [
                "приймайте",
                "шановні",
                "оформлюйте",
                "ми підготували",
                "лише два",
                "персональна",
                "візьміть",
                "потрібно",
            ]
        ):
            return False

        return any(
            marker in lower
            for marker in [
                "грн",
                "акці",
                "бонус",
                "розігру",
                "марафон",
                "пумб",
            ]
        )

    return any(word in lower for word in STRONG_PROMO_KEYWORDS)


def split_possible_titles(source: Source, line: str) -> list[str]:
    line = clean_text(line)

    if source.id == "globusbank" and "детальніше" in line.lower():
        parts = re.split(r"\s*Детальніше\s*", line, flags=re.IGNORECASE)
        return [normalize_title_text(part) for part in parts if is_plausible_title(normalize_title_text(part))]

    title = normalize_title_text(line)
    return [title] if is_plausible_title(title) else []


def parse_text_adapter_items(source: Source, soup: BeautifulSoup) -> list[Item]:
    if source.id not in TEXT_ADAPTER_SOURCES:
        return []

    lines = [
        clean_text(line)
        for line in soup.get_text("\n", strip=True).splitlines()
        if clean_text(line)
    ]
    lines = content_lines_for_source(source, lines)

    items: list[Item] = []
    seen_titles: set[str] = set()

    for index, line in enumerate(lines):
        for title in split_possible_titles(source, line):
            if title.lower() in seen_titles:
                continue

            if not likely_text_item_start(source, title):
                continue

            tail = lines[index + 1 : index + 12]
            date = extract_date(line)
            summary_parts: list[str] = []

            for part in tail:
                if not date:
                    date = extract_date(part)

                if part.lower() in GENERIC_LINK_TITLES:
                    continue

                if is_probably_year_filter(part):
                    continue

                if likely_text_item_start(source, part) and (
                    source.id in TEXT_ADAPTER_BREAKS_ON_NEXT_TITLE or len(summary_parts) >= 1
                ):
                    break

                summary_parts.append(part)

                if date and len(summary_parts) >= 3:
                    break

            text = clean_text(" ".join([title, *summary_parts]))
            summary = build_summary(text, title, date)
            is_promo, score, reason = classify_item(title, summary, source.kind)
            is_promo, score, reason = apply_source_policy(source, title, summary, is_promo, score, reason)

            item_url = find_matching_link(source, soup, title)
            if not item_url:
                item_url = synthetic_url(source, title, text)
                if source.id in TEXT_ADAPTER_REQUIRES_LINK:
                    continue

            items.append(
                Item(
                    source_id=source.id,
                    bank_name=source.name,
                    source_url=source.url,
                    item_url=item_url,
                    title=title,
                    date=date,
                    summary=summary,
                    is_promo=is_promo,
                    score=score,
                    reason=reason,
                )
            )
            seen_titles.add(title.lower())

            if len(items) >= MAX_ITEMS_PER_SOURCE:
                return items

    return items


def link_adapter_accepts(source: Source, item_url: str, raw_title: str, title: str) -> bool:
    path = urlparse(item_url).path.lower().rstrip("/")
    raw_lower = raw_title.lower()

    if not is_plausible_title(title):
        return False

    if source.id == "credit_agricole":
        return "/o-banke/pres-centr/novini/" in path

    if source.id == "otpbank":
        return path.startswith("/action/") and path != "/action"

    if source.id == "procreditbank":
        return (
            "aktsi" in path
            or "akci" in path
            or "propozy" in path
            or likely_text_item_start(source, title)
        )

    if source.id == "universalbank":
        return path.startswith("/offers/") or (
            not is_filter_or_archive_link(source, item_url, title)
            and any(word in raw_lower for word in STRONG_PROMO_KEYWORDS)
        )

    return False


def parse_link_adapter_items(source: Source, soup: BeautifulSoup) -> list[Item]:
    if source.id not in LINK_ADAPTER_SOURCES:
        return []

    items: list[Item] = []
    seen_urls: set[str] = set()

    for link in soup.find_all("a", href=True):
        raw_title = clean_text(link.get_text(" ", strip=True))
        title = normalize_title_text(raw_title)
        href = str(link.get("href", "")).strip()

        if not raw_title or is_bad_href(href):
            continue

        absolute_url = urljoin(source.url, href)
        if not host_allowed_for_item(absolute_url, source):
            continue

        item_url = normalize_url(absolute_url)
        if item_url == normalize_url(source.url) or item_url in seen_urls:
            continue

        if not link_adapter_accepts(source, item_url, raw_title, title):
            continue

        container = find_item_container(link)
        text = clean_text(container.get_text(" ", strip=True))
        if len(text) < len(raw_title):
            text = raw_title

        date = extract_date(raw_title) or extract_date(text)
        summary = build_summary(text, title, date)
        is_promo, score, reason = classify_item(title, summary, source.kind)
        is_promo, score, reason = apply_source_policy(source, title, summary, is_promo, score, reason)

        items.append(
            Item(
                source_id=source.id,
                bank_name=source.name,
                source_url=source.url,
                item_url=item_url,
                title=title,
                date=date,
                summary=summary,
                is_promo=is_promo,
                score=score,
                reason=reason,
            )
        )
        seen_urls.add(item_url)

        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break

    return items


def build_summary(text: str, title: str, date: str) -> str:
    summary = text

    if title and summary.startswith(title):
        summary = clean_text(summary[len(title):])

    if date:
        summary = clean_text(summary.replace(date, "", 1))

    for generic in GENERIC_LINK_TITLES:
        summary = clean_text(re.sub(rf"\b{re.escape(generic)}\b", "", summary, flags=re.IGNORECASE))

    if len(summary) > 500:
        summary = summary[:497].rstrip() + "..."

    return summary


def classify_item(title: str, summary: str, source_kind: str) -> tuple[bool, int, str]:
    text = f"{title} {summary}".lower()
    title_lower = title.lower()

    promo_hits = [word for word in PROMO_KEYWORDS if word.lower() in text]
    strong_title_hits = [word for word in STRONG_PROMO_KEYWORDS if word.lower() in title_lower]
    private_hits = [word for word in PRIVATE_KEYWORDS if word.lower() in text]
    negative_hits = [word for word in NEGATIVE_KEYWORDS if word.lower() in text]
    title_negative_hits = [word for word in TITLE_NEGATIVE_KEYWORDS if word.lower() in title_lower]

    score = len(promo_hits) * 2 + len(strong_title_hits) * 3 + len(private_hits) - len(negative_hits) * 2

    if source_kind == "promo":
        is_promo = bool(strong_title_hits) or score >= 2
    else:
        is_promo = bool(strong_title_hits) and score >= 3

    if title_negative_hits and not strong_title_hits:
        is_promo = False

    if "бізнес" in title_lower and not any(hit in title_lower for hit in ["кешбек", "зниж", "акці", "розіграш"]):
        is_promo = False

    reason_parts = []
    if promo_hits:
        reason_parts.append("promo: " + ", ".join(sorted(set(promo_hits))[:6]))
    if strong_title_hits:
        reason_parts.append("title: " + ", ".join(sorted(set(strong_title_hits))[:5]))
    if private_hits:
        reason_parts.append("private: " + ", ".join(sorted(set(private_hits))[:5]))
    if negative_hits:
        reason_parts.append("negative: " + ", ".join(sorted(set(negative_hits))[:5]))

    return is_promo, score, "; ".join(reason_parts)


def append_reason(reason: str, extra: str) -> str:
    return f"{reason}; {extra}" if reason else extra


def is_completed_or_expired(title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()
    markers = (
        "\u0430\u043a\u0446\u0456\u044e \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e",
        "\u0430\u043a\u0446\u0456\u044f \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430",
        "\u0430\u043a\u0446\u0438\u044f \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430",
        "\u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e",
        "\u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430",
        "ended",
        "expired",
    )
    return any(marker in text for marker in markers)


def apply_source_policy(
    source: Source,
    title: str,
    summary: str,
    is_promo: bool,
    score: int,
    reason: str,
) -> tuple[bool, int, str]:
    if source.kind != "promo":
        return is_promo, score, reason

    if is_completed_or_expired(title, summary):
        return False, min(score, -1), append_reason(reason, "completed/expired")

    return True, max(score, 1), append_reason(reason, "direct promo page")


def is_likely_content_item(
    source: Source,
    tag: Tag,
    item_url: str,
    title: str,
    text: str,
    date: str,
    score: int,
) -> bool:
    lower_title = title.lower()
    path = urlparse(item_url).path.lower().rstrip("/")
    base_path = source_base_path(source)
    path_matches_source = bool(base_path and base_path != "/" and path.startswith(base_path + "/"))
    content_path = path_matches_source or has_content_path_hint(source, item_url)

    if lower_title in NAV_TITLES or lower_title in GENERIC_LINK_TITLES or lower_title in FILTER_TITLES:
        return False

    if is_inside_noise_area(tag):
        return False

    if is_filter_or_archive_link(source, item_url, title):
        return False

    if has_service_path(item_url) and not content_path and not source.root_cards:
        return False

    if len(text) < 25 and score <= 0:
        return False

    if source.kind == "news":
        return content_path and (bool(date) or score >= 1 or has_card_hint(tag))

    if source.kind == "promo":
        if content_path:
            return True
        if source.root_cards or has_card_hint(tag):
            return bool(date) or score >= 1

    if source.root_cards and score >= 1:
        return True

    if content_path:
        return bool(date) or score >= 0 or has_card_hint(tag)

    return score >= 3 and has_card_hint(tag)


def link_item_from_anchor(source: Source, link: Tag) -> Item | None:
    href = str(link.get("href", "")).strip()
    if is_bad_href(href):
        return None

    absolute_url = urljoin(source.url, href)
    if not host_allowed_for_item(absolute_url, source):
        return None

    item_url = normalize_url(absolute_url)
    if item_url == normalize_url(source.url):
        return None

    container = find_item_container(link)
    title = pick_title(link, container)
    if not title:
        return None

    text = clean_text(container.get_text(" ", strip=True))
    if len(text) < len(title):
        text = title

    date = extract_date(text)
    summary = build_summary(text, title, date)
    is_promo, score, reason = classify_item(title, summary, source.kind)

    if not is_likely_content_item(source, link, item_url, title, text, date, score):
        debug(f"Службове посилання: {source.name}: {title} -> {item_url}")
        return None

    is_promo, score, reason = apply_source_policy(source, title, summary, is_promo, score, reason)

    return Item(
        source_id=source.id,
        bank_name=source.name,
        source_url=source.url,
        item_url=item_url,
        title=title,
        date=date,
        summary=summary,
        is_promo=is_promo,
        score=score,
        reason=reason,
    )


def best_link_for_card(source: Source, card: Tag, title: str) -> str:
    for link in card.find_all("a", href=True):
        href = str(link.get("href", "")).strip()
        if is_bad_href(href):
            continue

        absolute_url = urljoin(source.url, href)
        if not host_allowed_for_item(absolute_url, source):
            continue

        item_url = normalize_url(absolute_url)
        if item_url == normalize_url(source.url):
            continue

        if is_filter_or_archive_link(source, item_url, title):
            continue

        return item_url

    text = clean_text(card.get_text(" ", strip=True))
    return synthetic_url(source, title, text)


def item_from_card(source: Source, card: Tag) -> Item | None:
    if is_inside_noise_area(card):
        return None

    text = clean_text(card.get_text(" ", strip=True))
    if not 35 <= len(text) <= 2600:
        return None

    if not (has_card_hint(card) or source.root_cards):
        return None

    title = pick_title(None, card)
    if not title:
        first_link = card.find("a")
        title = pick_title(first_link, card) if isinstance(first_link, Tag) else ""

        if not title:
            return None

    if not is_plausible_title(title):
        return None

    date = extract_date(text)
    summary = build_summary(text, title, date)
    is_promo, score, reason = classify_item(title, summary, source.kind)

    if source.kind == "news" and not (date or score >= 1):
        return None

    item_url = best_link_for_card(source, card, title)

    if not is_likely_content_item(source, card, item_url, title, text, date, score):
        if not (source.root_cards and score >= 1):
            return None

    is_promo, score, reason = apply_source_policy(source, title, summary, is_promo, score, reason)

    return Item(
        source_id=source.id,
        bank_name=source.name,
        source_url=source.url,
        item_url=item_url,
        title=title,
        date=date,
        summary=summary,
        is_promo=is_promo,
        score=score,
        reason=reason,
    )


def parse_items(source: Source, page_html: str) -> list[Item]:
    soup = BeautifulSoup(page_html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    items: list[Item] = []
    seen_urls: set[str] = set()

    for item in parse_link_adapter_items(source, soup):
        if item.item_url in seen_urls:
            continue

        items.append(item)
        seen_urls.add(item.item_url)

        if len(items) >= MAX_ITEMS_PER_SOURCE:
            return items

    for item in parse_text_adapter_items(source, soup):
        if item.item_url in seen_urls:
            continue

        items.append(item)
        seen_urls.add(item.item_url)

        if len(items) >= MAX_ITEMS_PER_SOURCE:
            return items

    if source.id in DEDICATED_ADAPTER_SOURCES:
        return items

    for link in soup.find_all("a", href=True):
        item = link_item_from_anchor(source, link)
        if not item or item.item_url in seen_urls:
            continue

        items.append(item)
        seen_urls.add(item.item_url)

        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break

    if len(items) < MAX_ITEMS_PER_SOURCE:
        card_selectors = "article, li, section[class], div[class]"
        for card in soup.select(card_selectors):
            existing_card_url = ""
            for link in card.find_all("a", href=True):
                href = str(link.get("href", "")).strip()
                if is_bad_href(href):
                    continue

                absolute_url = urljoin(source.url, href)
                if not host_allowed_for_item(absolute_url, source):
                    continue

                normalized = normalize_url(absolute_url)
                if normalized in seen_urls:
                    existing_card_url = normalized
                    break

            if existing_card_url:
                continue

            item = item_from_card(source, card)
            if not item or item.item_url in seen_urls:
                continue

            items.append(item)
            seen_urls.add(item.item_url)

            if len(items) >= MAX_ITEMS_PER_SOURCE:
                break

    return items


def page_text_excerpt(page_html: str, limit: int = 900) -> str:
    soup = BeautifulSoup(page_html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    return clean_text(soup.get_text(" ", strip=True))[:limit]


async def fetch_page_html(context: Any, source: Source) -> str:
    page = await context.new_page()

    try:
        await page.goto(source.url, wait_until="domcontentloaded", timeout=60000)
        content = ""

        for attempt in range(7):
            await page.wait_for_timeout(PAGE_WAIT_MS if attempt == 0 else 5000)
            content = await page.content()

            if not is_security_page(content):
                if source.id in STRICT_ZERO_ITEM_SOURCES:
                    try:
                        body_text = clean_text(await page.locator("body").inner_text(timeout=3000))
                    except Exception:
                        body_text = ""

                    if not body_text and attempt < 6:
                        try:
                            await page.wait_for_load_state("networkidle", timeout=5000)
                        except PlaywrightTimeoutError:
                            pass
                        continue

                return content

            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except PlaywrightTimeoutError:
                pass

        return content
    except PlaywrightTimeoutError:
        content = await page.content()
        if content:
            return content
        raise
    finally:
        await page.close()


def send_telegram_message(chat_id: str, message: str, disable_preview: bool = False) -> None:
    response = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview,
        },
        timeout=30,
    )
    response.raise_for_status()


def send_admin_error(source: Source, error: Exception) -> None:
    if not ADMIN_CHAT_ID:
        return

    message = (
        "<b>Помилка джерела</b>"
        f"\n\nБанк: {html.escape(source.name)}"
        f"\nURL: {html.escape(source.url)}"
        f"\nПомилка: {html.escape(str(error)[:1200])}"
    )
    send_telegram_message(ADMIN_CHAT_ID, message, disable_preview=True)


def send_to_telegram(item: Item) -> None:
    message = f"<b>{html.escape(item.title)}</b>"
    message += f"\n\nБанк: {html.escape(item.bank_name)}"

    if item.date:
        message += f"\nДата: {html.escape(item.date)}"

    if item.summary:
        message += f"\n\n{html.escape(item.summary)}"

    message += f"\n\n<a href=\"{html.escape(item.item_url)}\">Детальніше</a>"
    send_telegram_message(CHANNEL_ID, message)


async def process_source(context: Any, source: Source, first_run_without_send: bool) -> tuple[int, int, int]:
    print(f"Перевіряю: {source.name}")

    page_html = await fetch_page_html(context, source)

    if is_security_page(page_html):
        raise RuntimeError("джерело показало сторінку захисту/CAPTCHA")

    items = parse_items(source, page_html)
    if source.id in STRICT_ZERO_ITEM_SOURCES and not items:
        excerpt = page_text_excerpt(page_html)
        raise RuntimeError(
            "Не знайшов жодної акції у контентній зоні сторінки. "
            "Ймовірно, сайт змінив структуру, не довантажив контент або показав службову сторінку. "
            f"Фрагмент тексту: {excerpt}"
        )

    new_items = [item for item in items if not was_seen(item.item_url)]
    promo_candidates = sum(1 for item in items if item.is_promo)

    sent_count = 0
    ignored_count = 0

    for item in reversed(new_items):
        if first_run_without_send:
            save_item(item, "remembered" if item.is_promo else "ignored")
            continue

        if not item.is_promo:
            save_item(item, "ignored")
            ignored_count += 1
            debug(f"Ігнор: {item.bank_name}: {item.title} ({item.reason})")
            continue

        try:
            send_to_telegram(item)
            save_item(item, "sent")
            sent_count += 1
            print(f"Надіслано: {item.bank_name}: {item.title}")
            time.sleep(2)
        except Exception as error:
            save_item(item, "error", str(error))
            print(f"Помилка Telegram для {item.bank_name}: {error}")

    print(
        f"{source.name}: кандидатів {len(items)}, промо-кандидатів {promo_candidates}, "
        f"нових {len(new_items)}, проігноровано {ignored_count}, надіслано {sent_count}"
    )
    return len(items), len(new_items), sent_count


async def run_once() -> None:
    sources = load_sources()
    first_run_without_send = total_seen_items() == 0 and not SEND_EXISTING

    if first_run_without_send:
        print("Перший запуск: поточні записи будуть тільки запам'ятані.")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_PROFILE_DIR,
            headless=HEADLESS,
            viewport={"width": 1365, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
        )

        total_new = 0
        total_sent = 0

        for source in sources:
            try:
                source_first_run_without_send = (
                    first_run_without_send
                    or (not SEND_EXISTING and total_seen_items_for_source(source.id) == 0)
                )
                _, new_count, sent_count = await process_source(
                    context,
                    source,
                    source_first_run_without_send,
                )
                total_new += new_count
                total_sent += sent_count
            except Exception as error:
                print(f"Помилка джерела {source.name}: {error}")
                try:
                    send_admin_error(source, error)
                except Exception as admin_error:
                    print(f"Не вдалося надіслати admin-помилку: {admin_error}")

        await context.close()

    print(f"Цикл завершено. Нових записів: {total_new}, надіслано: {total_sent}")


async def main() -> None:
    if not BOT_TOKEN or not CHANNEL_ID:
        raise RuntimeError("Заповни BOT_TOKEN і CHANNEL_ID у .env")

    init_db()

    while True:
        await run_once()
        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())

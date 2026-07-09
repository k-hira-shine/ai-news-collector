"""Gemini専用 — 公式RSS / スクレイピング / X 収集 + 分類 → data/gemini/"""

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from utils import clamp_max_items

logger = logging.getLogger("ai-news.gemini_collector")

GEMINI_DIR = "gemini"
JST = ZoneInfo("Asia/Tokyo")
LAST_RSS_HEALTH: dict[str, Any] = {}

GEMINI_KEYWORDS = [
    "gemini", "ジェミニ", "google ai studio", "ai studio", "veo", "imagen",
    "lyria", "nano banana", "deep think", "gemini live", "gemini app",
    "gemini api", "gemini flash", "gemini pro", "gemini ultra", "gemini drop",
    "antigravity", "bard", "google ai", "deepmind",
]

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["available_now", "coming_soon", "deprecation", "unknown"],
                    },
                    "title_ja": {"type": "string"},
                    "summary_ja": {"type": "string"},
                    "scheduled_date": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["item_id", "status", "title_ja", "summary_ja", "scheduled_date", "reason"],
            },
        }
    },
    "required": ["items"],
}

TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "title_ja": {"type": "string"},
                    "summary_ja": {"type": "string"},
                },
                "required": ["item_id", "title_ja", "summary_ja"],
            },
        }
    },
    "required": ["items"],
}

_DEPRECATION_RE = re.compile(
    r"shut\s*down|stops?\s+serving|deprecated|deprecation\s+announcement|"
    r"are now shut down|will be shut down|has been shut down|廃止|停止",
    re.I,
)

_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _month_day_year_to_iso(month: str, day: str, year: str) -> str:
    try:
        dt = datetime.strptime(f"{month} {int(day)}, {year}", "%B %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return ""


def extract_scheduled_date(text: str) -> str:
    """本文から利用開始日・停止予定日を抽出（YYYY-MM-DD）"""
    if not text:
        return ""
    month_pat = "|".join(_MONTH_NAMES)
    patterns = [
        rf"(?:will be )?shut\s*down(?:\s+on)?\s+({month_pat})\s+(\d{{1,2}}),?\s+(\d{{4}})",
        rf"(?:stops?(?:\s+serving)?(?:\s+requests)?\s+on|ends?\s+on|until|by)\s+"
        rf"({month_pat})\s+(\d{{1,2}}),?\s+(\d{{4}})",
        rf"(?:available|launch(?:ing)?|roll(?:ing)?\s*out(?:\s+starting)?|starting(?:\s+on)?|"
        rf"releases?\s+on|from)\s+({month_pat})\s+(\d{{1,2}}),?\s+(\d{{4}})",
        rf"\b(20\d{{2}})\.(\d{{2}})\.(\d{{2}})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        if len(m.groups()) == 3 and m.group(1).isdigit():
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        iso = _month_day_year_to_iso(m.group(1), m.group(2), m.group(3))
        if iso:
            return iso
    return ""


def _is_valid_iso_date(raw: str) -> bool:
    if not raw or len(raw) < 10:
        return False
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", raw[:10]):
        return False
    try:
        datetime.strptime(raw[:10], "%Y-%m-%d")
        return True
    except ValueError:
        return False


def apply_status_guardrails(item: dict) -> None:
    """AI判定後の安全装置（廃止検出・未来日ガード・予定日補完）"""
    text = " ".join([
        item.get("title") or "",
        item.get("content") or "",
        item.get("title_ja") or "",
        item.get("summary_ja") or "",
    ])
    now = datetime.now(timezone.utc)

    sd_raw = (item.get("scheduled_date") or "").strip()
    if _is_valid_iso_date(sd_raw):
        item["scheduled_date"] = sd_raw[:10]
    else:
        item.pop("scheduled_date", None)
        extracted = extract_scheduled_date(text)
        if extracted:
            item["scheduled_date"] = extracted

    if _DEPRECATION_RE.search(text):
        item["status"] = "deprecation"
        return

    pub = _parse_date_from_string(item.get("published_at") or "")
    if pub and pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    if pub and pub > now and item.get("status") == "available_now":
        item["status"] = "coming_soon"

    sd = _parse_date_from_string(item.get("scheduled_date") or "")
    if sd and sd.tzinfo is None:
        sd = sd.replace(tzinfo=timezone.utc)
    if sd and sd > now and item.get("status") == "available_now":
        item["status"] = "coming_soon"


def _base_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir(name: str) -> str:
    return os.path.join(_base_dir(), "data", name)


def _load_config() -> dict:
    path = os.path.join(_base_dir(), "config.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _make_id(url: str) -> str:
    return "gemini_" + hashlib.md5(url.encode()).hexdigest()[:16]


def _load_saved_urls(days: int = 30) -> set[str]:
    """jsonl に保存済みの URL（収集スキップ用）"""
    from glob import glob
    urls: set[str] = set()
    out_dir = _data_dir(GEMINI_DIR)
    if not os.path.isdir(out_dir):
        return urls
    files = sorted(glob(os.path.join(out_dir, "*.jsonl")), reverse=True)
    for fpath in files[:days]:
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    url = json.loads(line).get("url")
                    if url:
                        urls.add(url)
                except Exception:
                    pass
    return urls


def _age_cutoff(config: dict) -> datetime:
    days = int(config.get("gemini_collection", {}).get("max_age_days", 14))
    return datetime.now(timezone.utc) - timedelta(days=days)


def _parse_date_from_string(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    if len(raw) >= 10:
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _parse_rss_entry_date(entry: Any) -> datetime | None:
    pub = entry.get("published_parsed") or entry.get("updated_parsed")
    if pub:
        try:
            import calendar
            return datetime.fromtimestamp(calendar.timegm(pub), tz=timezone.utc)
        except Exception:
            pass
    for key in ("published", "updated"):
        dt = _parse_date_from_string(entry.get(key) or "")
        if dt:
            return dt
    return None


def _extract_published_from_html(html: str) -> datetime | None:
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1))
            candidates = data if isinstance(data, list) else [data]
            for obj in candidates:
                if not isinstance(obj, dict):
                    continue
                for key in ("datePublished", "dateModified", "uploadDate"):
                    dt = _parse_date_from_string(str(obj.get(key) or ""))
                    if dt:
                        return dt
        except Exception:
            continue
    for pat in (
        r'property="article:published_time"\s+content="([^"]+)"',
        r'name="date"\s+content="([^"]+)"',
        r'"datePublished"\s*:\s*"([^"]+)"',
    ):
        m = re.search(pat, html, re.I)
        if m:
            dt = _parse_date_from_string(m.group(1))
            if dt:
                return dt
    return None


_fetch_date_cache: dict[str, datetime | None] = {}


def _fetch_article_published_at(url: str) -> datetime | None:
    if not url or not url.startswith("http"):
        return None
    if url in _fetch_date_cache:
        return _fetch_date_cache[url]
    dt: datetime | None = None
    try:
        import requests
        resp = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "ai-news-collector/1.0 (Gemini tracker)"},
        )
        resp.raise_for_status()
        dt = _extract_published_from_html(resp.text)
    except Exception as e:
        logger.debug("Article date fetch failed [%s]: %s", url[:70], e)
    _fetch_date_cache[url] = dt
    return dt


def _resolve_published_at(entry: Any, link: str) -> datetime | None:
    pub_dt = _parse_rss_entry_date(entry)
    if pub_dt:
        return pub_dt
    if link:
        return _fetch_article_published_at(link)
    return None


def _contains_gemini(text: str) -> bool:
    lower = (text or "").lower()
    return any(kw in lower for kw in GEMINI_KEYWORDS)


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    html = re.sub(r"<[^>]+>", "\n", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def collect_rss(config: dict) -> list[dict]:
    global LAST_RSS_HEALTH
    cfg = config.get("gemini_collection", {})
    if not cfg.get("enabled", True):
        LAST_RSS_HEALTH = {"feeds_total": 0, "feeds_ok": 0, "feeds_failed": 0, "failures": []}
        return []

    try:
        import feedparser
    except ImportError:
        logger.error("feedparser not installed")
        return []

    cutoff = _age_cutoff(config)
    saved = _load_saved_urls()
    collected_at = datetime.now(timezone.utc).isoformat()
    items: list[dict] = []
    run_seen: set[str] = set()
    health = {
        "feeds_total": 0,
        "feeds_ok": 0,
        "feeds_failed": 0,
        "failures": [],
    }

    for feed_cfg in cfg.get("rss_feeds", []):
        url = feed_cfg.get("url", "")
        label = feed_cfg.get("label", url)
        limit = int(feed_cfg.get("max_items", 30))
        need_filter = bool(feed_cfg.get("gemini_filter"))
        if not url:
            continue
        health["feeds_total"] += 1
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries[:limit]:
                link = entry.get("link", "")
                if not link or link in saved or link in run_seen:
                    continue

                pub_dt = _resolve_published_at(entry, link)
                if pub_dt and pub_dt < cutoff:
                    continue

                content = ""
                if entry.get("content"):
                    content = entry.content[0].get("value", "")
                elif entry.get("summary"):
                    content = entry.summary
                content = _strip_html(content)[:2000]
                title = (entry.get("title") or "").strip()

                if need_filter and not _contains_gemini(title + " " + content):
                    continue

                item = {
                    "id": _make_id(link),
                    "source": "rss",
                    "source_label": label,
                    "title": title,
                    "url": link,
                    "content": content,
                    "published_at": pub_dt.isoformat() if pub_dt else "",
                    "collected_at": collected_at,
                }
                items.append(item)
                run_seen.add(link)
                count += 1
            logger.info("Gemini RSS [%s]: %d items", label, count)
            health["feeds_ok"] += 1
        except Exception as e:
            logger.warning("Gemini RSS failed [%s]: %s", label, e)
            health["feeds_failed"] += 1
            health["failures"].append({"label": label, "error": str(e)[:200]})

    LAST_RSS_HEALTH = health
    return items


def _parse_release_notes(
    text: str, base_url: str, label: str, max_items: int, cutoff: datetime | None = None,
) -> list[dict]:
    """Gemini Release Notes（日本語/英語）から日付ブロックを抽出"""
    items: list[dict] = []
    collected_at = datetime.now(timezone.utc).isoformat()

    # Markdown形式 (## 2026.05.19) または プレーンテキスト (2026.05.19 Title...)
    sections = re.split(r"(?m)^##\s+(\d{4}\.\d{2}\.\d{2})\s*$", text)
    if len(sections) >= 3:
        i = 1
        while i < len(sections) - 1 and len(items) < max_items:
            date_str = sections[i].strip()
            body = sections[i + 1]
            i += 2
            try:
                pub_dt = datetime.strptime(date_str, "%Y.%m.%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if cutoff and pub_dt < cutoff:
                continue
            blocks = re.split(r"(?m)^###\s+", body)
            for block in blocks[1:]:
                if len(items) >= max_items:
                    return items
                lines = block.strip().split("\n", 1)
                title = lines[0].strip()
                content = lines[1].strip() if len(lines) > 1 else title
                content = re.sub(r"\s+", " ", content)[:2000]
                slug = hashlib.md5(f"{date_str}:{title}".encode()).hexdigest()[:12]
                url = f"{base_url}#{date_str}-{slug}"
                items.append({
                    "id": _make_id(url),
                    "source": "scrape",
                    "source_label": label,
                    "title": title,
                    "url": url,
                    "content": content,
                    "published_at": pub_dt.isoformat(),
                    "collected_at": collected_at,
                })
        return items

    parts = re.split(r"(?=\b20\d{2}\.\d{2}\.\d{2}\b)", text)
    for part in parts:
        if len(items) >= max_items:
            break
        m = re.match(r"\s*(20\d{2}\.\d{2}\.\d{2})\s+(.*)", part, re.S)
        if not m:
            continue
        date_str, body = m.group(1), m.group(2).strip()
        if len(body) < 40:
            continue
        try:
            pub_dt = datetime.strptime(date_str, "%Y.%m.%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if cutoff and pub_dt < cutoff:
            continue

        split_body = re.split(r"更新内容\s*[:：]|What\s*:", body, maxsplit=1, flags=re.I)
        title_part = split_body[0].strip()
        content = split_body[1].strip() if len(split_body) > 1 else body
        title = re.split(r"[。.\n]", title_part)[0].strip()[:200] or title_part[:120]
        content = re.sub(r"\s+", " ", content)[:2000]
        if not title:
            continue

        slug = hashlib.md5(f"{date_str}:{title}".encode()).hexdigest()[:12]
        url = f"{base_url}#{date_str}-{slug}"
        items.append({
            "id": _make_id(url),
            "source": "scrape",
            "source_label": label,
            "title": title,
            "url": url,
            "content": content,
            "published_at": pub_dt.isoformat(),
            "collected_at": collected_at,
        })
    return items


def _is_changelog_section_date(text: str, start: int, end: int) -> bool:
    """本文中の停止予定日など、見出しではない日付を除外"""
    before_tail = text[max(0, start - 30):start].lower()
    after_head = text[end:end + 40].strip()
    if re.search(r"(?:will be )?shut down on?\s*$", before_tail):
        return False
    if before_tail.rstrip().endswith("shut down"):
        return False
    if after_head.startswith(":") and re.match(r":\s*gemini-", after_head, re.I):
        return False
    if not re.match(r"[A-Z(]", after_head):
        return False
    return True


def _is_valid_changelog_chunk(chunk: str) -> bool:
    if len(chunk) < 20:
        return False
    if re.match(r"^:\s*gemini-[\w.-]+(\s+gemini-[\w.-]+)*\s*$", chunk, re.I):
        return False
    return True


def _parse_api_changelog(
    text: str, base_url: str, label: str, max_items: int, cutoff: datetime | None = None,
) -> list[dict]:
    """Gemini API Changelog から日付見出し＋本文を抽出（新しい順）"""
    items: list[dict] = []
    collected_at = datetime.now(timezone.utc).isoformat()
    pattern = r"(?is)(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})"
    match_list = [
        m for m in re.finditer(pattern, text)
        if _is_changelog_section_date(text, m.start(), m.end())
    ]
    dated: list[tuple[datetime, int]] = []
    now = datetime.now(timezone.utc)
    for idx, m in enumerate(match_list):
        month_name, day, year = m.group(1), m.group(2), m.group(3)
        try:
            pub_dt = datetime.strptime(f"{month_name} {day}, {year}", "%B %d, %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if pub_dt > now:
            continue
        dated.append((pub_dt, idx))
    dated.sort(key=lambda x: x[0], reverse=True)

    for pub_dt, idx in dated:
        if len(items) >= max_items:
            break
        if cutoff and pub_dt < cutoff:
            continue
        m = match_list[idx]
        month_name, day, year = m.group(1), m.group(2), m.group(3)
        start = m.end()
        end = match_list[idx + 1].start() if idx + 1 < len(match_list) else len(text)
        chunk = text[start:end].strip()
        chunk = re.sub(r"\s+", " ", chunk)[:2000]
        if not _is_valid_changelog_chunk(chunk):
            continue
        title = chunk[:120].strip()
        if not _contains_gemini(title + " " + chunk):
            continue
        slug = hashlib.md5(f"{pub_dt.date()}-{idx}".encode()).hexdigest()[:12]
        url = f"{base_url}#{year}-{month_name}-{day}-{slug}"
        items.append({
            "id": _make_id(url),
            "source": "scrape",
            "source_label": label,
            "title": title,
            "url": url,
            "content": chunk,
            "published_at": pub_dt.isoformat(),
            "collected_at": collected_at,
        })
    return items


def collect_scrape_pages(config: dict) -> list[dict]:
    cfg = config.get("gemini_collection", {})
    if not cfg.get("enabled", True):
        return []

    try:
        import requests
    except ImportError:
        logger.error("requests not installed")
        return []

    saved = _load_saved_urls()
    cutoff = _age_cutoff(config)
    items: list[dict] = []
    run_seen: set[str] = set()

    for page in cfg.get("scrape_pages", []):
        url = page.get("url", "")
        label = page.get("label", url)
        max_items = int(page.get("max_items", 30))
        if not url:
            continue
        try:
            resp = requests.get(
                url,
                timeout=30,
                headers={"User-Agent": "ai-news-collector/1.0 (Gemini tracker)"},
            )
            resp.raise_for_status()
            text = resp.text
            plain = _strip_html(text)

            if "release-notes" in url:
                parsed = _parse_release_notes(plain, url, label, max_items, cutoff=cutoff)
            else:
                parsed = _parse_api_changelog(plain, url, label, max_items, cutoff=cutoff)

            count = 0
            for item in parsed:
                key = item.get("url", "")
                if key in saved or key in run_seen:
                    continue
                items.append(item)
                run_seen.add(key)
                count += 1
            logger.info("Gemini scrape [%s]: %d items", label, count)
        except Exception as e:
            logger.warning("Gemini scrape failed [%s]: %s", label, e)

    return items


def collect_x_accounts(config: dict) -> list[dict]:
    cfg = config.get("gemini_collection", {})
    if not cfg.get("enabled", True):
        return []

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        logger.warning("APIFY_TOKEN not set — skipping Gemini X collection")
        return []

    accounts = cfg.get("x_accounts", [])
    if not accounts:
        return []

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.error("apify-client not installed")
        return []

    x_cfg = config.get("x_twitter", {})
    actor_id = x_cfg.get("apify_actor", "xquik/x-tweet-scraper")

    max_items = clamp_max_items(
        cfg.get("max_items_per_account", 20),
        "gemini_collection.max_items_per_account",
    )
    max_age_days = int(cfg.get("max_age_days", 14))
    keyword_handles = {h.lower() for h in cfg.get("x_keyword_filter_handles", [])}
    since_date = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime("%Y-%m-%d")

    handles = [a["handle"] for a in accounts if a.get("handle")]
    label_map = {a["handle"].lower(): a.get("label", a["handle"]) for a in accounts}

    from utils import apify_actor_call, apify_run_get

    client = ApifyClient(token)
    run_input = {
        "searchTerms": [f"from:{h} -filter:replies" for h in handles],
        "queryType": "Latest",
        "maxItems": max_items,
        "includeSearchTerms": True,
        "since": since_date,
    }

    items: list[dict] = []
    collected_at = datetime.now(timezone.utc).isoformat()
    saved = _load_saved_urls()
    run_seen: set[str] = set()

    try:
        run = apify_actor_call(client.actor(actor_id), run_input=run_input, wait_seconds=300)
        status = apify_run_get(run, "status", "")
        cost = float(apify_run_get(run, "usageTotalUsd") or 0)
        if status != "SUCCEEDED":
            logger.error("Gemini X batch status=%s cost=$%.4f", status, cost)
            return []
        logger.info("Gemini X batch cost=$%.4f", cost)

        for tweet in client.dataset(apify_run_get(run, "defaultDatasetId")).iterate_items():
            author_obj = tweet.get("author") or {}
            username = (
                author_obj.get("userName")
                or author_obj.get("username")
                or tweet.get("username")
                or ""
            )
            if not username:
                st = tweet.get("searchTerm") or ""
                m = re.search(r"from:(\w+)", st)
                if m:
                    username = m.group(1)

            text = tweet.get("text") or tweet.get("fullText") or ""
            url = tweet.get("url") or tweet.get("tweetUrl") or tweet.get("twitterUrl") or ""
            if not url or url in saved or url in run_seen:
                continue

            if username.lower() in keyword_handles and not _contains_gemini(text):
                continue

            label = label_map.get(username.lower(), f"@{username}")
            pub_raw = tweet.get("createdAt") or ""
            items.append({
                "id": _make_id(url),
                "source": "x",
                "source_label": label,
                "title": text[:200],
                "url": url,
                "content": text[:2000],
                "author": username,
                "published_at": pub_raw,
                "collected_at": collected_at,
            })
            run_seen.add(url)
        logger.info("Gemini X: %d items", len(items))
    except Exception as e:
        logger.error("Gemini X collection failed: %s", e)

    return items


def deduplicate_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for item in sorted(
        items,
        key=lambda x: x.get("published_at") or x.get("collected_at") or "",
        reverse=True,
    ):
        key = item.get("url") or item.get("id") or ""
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def classify_items(items: list[dict], config: dict, *, titles_only: bool = False) -> list[dict]:
    if not items:
        return []

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — skipping classification")
        for item in items:
            item.setdefault("status", "unknown")
            item.setdefault("title_ja", (item.get("title") or "")[:80])
            item.setdefault("summary_ja", (item.get("title") or "")[:80])
            item.setdefault("reason", "API key not set")
        return items

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.warning("google-genai not installed")
        return items

    models = config.get("analysis", {}).get("models", {})
    if titles_only:
        from translation_config import get_translation_model

        model_name = get_translation_model()
        thinking_budget = 0
    else:
        model_name = models.get("fallback", "gemini-2.5-flash")
        thinking_budget = 128
    client = genai.Client(api_key=api_key)
    batch_size = 25
    id_map = {item["id"]: item for item in items if item.get("id")}

    for start in range(0, len(items), batch_size):
        batch = items[start: start + batch_size]
        items_text = ""
        for item in batch:
            items_text += f"""
[ID: {item.get('id', '')}]
タイトル: {item.get('title', '')}
ソース: {item.get('source_label', '')}
本文: {(item.get('content') or '')[:700]}
---"""

        if titles_only:
            prompt = f"""以下はGoogle Gemini公式情報源から収集した記事・投稿です。
各項目について title_ja / summary_ja のみ日本語化してください（status は変更しない）。

## 日本語出力（必須）
- title_ja: 50字以内。**一覧を見た新入社員が「何の機能・製品か」すぐ分かる見出し**
  - 製品名・機能名・連携先・何ができるかを具体的に書く
  - 抽象語・マーケ語だけにしない（×「インテリジェントなアイウェア」→ ○「Geminiアプリ連携のオーディオグラス（Samsung共同）」）
  - 英語キャッチコピーの直訳ではなく、内容を平易に言い換える
  - summary_ja と同文にしない（title=何、summary=どう便利か/詳細）
- summary_ja: 80字以内の日本語要約。何の機能・発表かを平易に説明

## 対象
{items_text}"""
            schema = TRANSLATE_SCHEMA
        else:
            prompt = f"""以下はGoogle Gemini公式情報源から収集した記事・投稿です。
各項目について status / title_ja / summary_ja / scheduled_date / reason を判定してください。

## 判定基準
- available_now: すでに利用可能、正式リリース、GA、generally available、公開済み、rolling out now など
- coming_soon: coming soon、近日、予定、preview、beta、trusted testers、rollout starting、in the coming weeks など
- deprecation: モデル停止・廃止予告・Deprecation announcement・shut down など（新機能リリースではない）
- unknown: Gemini機能の新着情報か判断できない、または上記どれにも当てはまらない

## scheduled_date（YYYY-MM-DD）
- coming_soon: 本文に書かれた利用開始予定日（なければ空文字 ""）
- deprecation: 停止予定日（なければ空文字 ""）
- それ以外: 空文字 ""
- プレースホルダ（YYYY-MM-DD 等）は禁止。確実な日付のみ。

## 日本語出力（必須）
- title_ja: 50字以内。**一覧を見た新入社員が「何の機能・製品か」すぐ分かる見出し**
  - 製品名・機能名・連携先・何ができるかを具体的に書く
  - 抽象語・マーケ語だけにしない（×「インテリジェントなアイウェア」→ ○「Geminiアプリ連携のオーディオグラス（Samsung共同）」）
  - 英語キャッチコピーの直訳ではなく、内容を平易に言い換える
  - summary_ja と同文にしない（title=何、summary=どう便利か/詳細）
- summary_ja: 80字以内の日本語要約。何の機能・発表かを平易に説明（分類理由ではなく内容の要約）
- reason: 分類理由を1文（日本語）。UIには表示しない内部用

## 対象
{items_text}"""
            schema = CLASSIFY_SCHEMA

        raw: dict | None = None
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                        thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
                        max_output_tokens=8192,
                    ),
                )
                from gemini_usage import log_usage
                log_usage("gemini_collector", model_name, response)
                raw = json.loads(response.text)
                break
            except Exception as e:
                last_err = e
                err_text = str(e)
                retryable = "503" in err_text or "UNAVAILABLE" in err_text or "429" in err_text
                if retryable and attempt < 3:
                    wait = min(2 * (2 ** attempt), 30)
                    logger.warning(
                        "Gemini classification retry %d/3 in %ds: %s",
                        attempt + 1, wait, e,
                    )
                    time.sleep(wait)
                    continue
                break
        if raw is None:
            logger.error("Gemini classification failed: %s", last_err)
            for item in batch:
                item.setdefault("status", "unknown")
                item.setdefault("title_ja", (item.get("title") or "")[:80])
                item.setdefault("summary_ja", (item.get("title") or "")[:80])
                item.setdefault("reason", "classification failed")
            continue

        for row in raw.get("items", []):
            item_id = row.get("item_id", "")
            base = id_map.get(item_id)
            if not base:
                continue
            if not titles_only:
                base["status"] = row.get("status", "unknown")
                base["reason"] = row.get("reason", "")[:200]
                sd = (row.get("scheduled_date") or "").strip()
                if _is_valid_iso_date(sd):
                    base["scheduled_date"] = sd[:10]
                else:
                    base.pop("scheduled_date", None)
            base["title_ja"] = row.get("title_ja", "")[:50]
            base["summary_ja"] = row.get("summary_ja", "")[:160]
            base["classified_at"] = datetime.now(timezone.utc).isoformat()
            apply_status_guardrails(base)

    for item in items:
        item.setdefault("status", "unknown")
        item.setdefault("title_ja", (item.get("title") or "")[:80])
        item.setdefault("summary_ja", (item.get("title") or "")[:80])
        item.setdefault("reason", "")
        apply_status_guardrails(item)

    return items


def save_gemini_jsonl(items: list[dict]) -> str:
    if not items:
        return ""
    out_dir = _data_dir(GEMINI_DIR)
    os.makedirs(out_dir, exist_ok=True)
    today = datetime.now(JST).strftime("%Y-%m-%d")
    path = os.path.join(out_dir, f"{today}.jsonl")

    existing_ids: set[str] = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing_ids.add(json.loads(line).get("id", ""))
                    except Exception:
                        pass

    new_items = [i for i in items if i.get("id") not in existing_ids]
    if not new_items:
        logger.info("All Gemini items already saved")
        return path

    with open(path, "a", encoding="utf-8") as f:
        for item in new_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("Saved %d Gemini items → %s", len(new_items), path)
    return path


def load_all_gemini_items(days: int = 14) -> list[dict]:
    out_dir = _data_dir(GEMINI_DIR)
    if not os.path.isdir(out_dir):
        return []
    from glob import glob
    files = sorted(glob(os.path.join(out_dir, "*.jsonl")), reverse=True)
    items: list[dict] = []
    for fpath in files[:days]:
        with open(fpath, encoding="utf-8") as f:
            for line in f.read().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
    return items


def rewrite_gemini_jsonl(items: list[dict]) -> str:
    """分類・翻訳し直した全件を本日ファイルに上書き保存"""
    out_dir = _data_dir(GEMINI_DIR)
    os.makedirs(out_dir, exist_ok=True)
    today = datetime.now(JST).strftime("%Y-%m-%d")
    path = os.path.join(out_dir, f"{today}.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info("Rewrote %d Gemini items → %s", len(items), path)
    return path


def backfill_published_dates(items: list[dict] | None = None, days: int = 30) -> list[dict]:
    """published_at が空の項目について記事ページから公開日を取得"""
    if items is None:
        items = deduplicate_items(load_all_gemini_items(days))
    updated = 0
    for item in items:
        if item.get("published_at"):
            continue
        url = item.get("url") or ""
        if not url.startswith("http"):
            continue
        dt = _fetch_article_published_at(url)
        if dt:
            item["published_at"] = dt.isoformat()
            updated += 1
    logger.info("Backfilled published_at for %d / %d items", updated, len(items))
    return items


def apply_guardrails_to_all(days: int = 14) -> list[dict]:
    """既存データにルールベースのガードレールと予定日抽出を適用（API不要）"""
    items = deduplicate_items(load_all_gemini_items(days))
    for item in items:
        apply_status_guardrails(item)
    rewrite_gemini_jsonl(items)
    return items


def reclassify_recent(config: dict | None = None, days: int = 14) -> list[dict]:
    if config is None:
        config = _load_config()
    items = deduplicate_items(load_all_gemini_items(days))
    logger.info("Reclassifying %d Gemini items...", len(items))
    items = classify_items(items, config, titles_only=False)
    rewrite_gemini_jsonl(items)
    return items


def retranslate_recent(config: dict | None = None, days: int = 14) -> list[dict]:
    if config is None:
        config = _load_config()
    items = deduplicate_items(load_all_gemini_items(days))
    logger.info("Retranslating %d Gemini items...", len(items))
    items = classify_items(items, config, titles_only=True)
    rewrite_gemini_jsonl(items)
    return items


def restore_statuses_from_snapshot(items: list[dict], snapshot_path: str) -> int:
    """スナップショット jsonl から status / reason を復元（title_ja は現行を維持）"""
    if not os.path.isfile(snapshot_path):
        logger.warning("Snapshot not found: %s", snapshot_path)
        return 0
    by_id: dict[str, dict] = {}
    with open(snapshot_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            item_id = row.get("id")
            if item_id:
                by_id[item_id] = row
    restored = 0
    for item in items:
        snap = by_id.get(item.get("id", ""))
        if not snap:
            continue
        if snap.get("status"):
            item["status"] = snap["status"]
            restored += 1
        if snap.get("reason"):
            item["reason"] = snap["reason"]
    logger.info("Restored status for %d / %d items from %s", restored, len(items), snapshot_path)
    return restored


def collect_all(config: dict | None = None) -> list[dict]:
    if config is None:
        config = _load_config()
    raw: list[dict] = []
    raw.extend(collect_rss(config))
    raw.extend(collect_scrape_pages(config))
    raw.extend(collect_x_accounts(config))
    items = deduplicate_items(raw)
    items = classify_items(items, config)
    save_gemini_jsonl(items)
    return items


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Gemini公式情報収集")
    parser.add_argument(
        "--apply-guardrails",
        action="store_true",
        help="既存データに廃止検出・予定日抽出・未来日ガードを適用（API不要）",
    )
    parser.add_argument(
        "--reclassify",
        action="store_true",
        help="既存データを新スキーマで再分類（scheduled_date / deprecation 対応）",
    )
    parser.add_argument(
        "--retranslate",
        action="store_true",
        help="既存データの見出し・要約のみ日本語化（status は維持）",
    )
    parser.add_argument(
        "--fix-dates",
        action="store_true",
        help="published_at が空の項目に記事ページから公開日を補完",
    )
    args = parser.parse_args()

    cost_mode = not (args.apply_guardrails or args.fix_dates)
    if cost_mode and os.environ.get("ALLOW_LEGACY_COSTS") != "true":
        logger.error("Legacy Gemini tracker is cost-disabled. Set ALLOW_LEGACY_COSTS=true to run.")
        raise SystemExit(2)

    if args.fix_dates:
        items = backfill_published_dates()
        rewrite_gemini_jsonl(items)
    elif args.apply_guardrails:
        items = apply_guardrails_to_all()
    elif args.reclassify:
        items = reclassify_recent()
    elif args.retranslate:
        items = retranslate_recent()
    else:
        items = collect_all()

    now = sum(1 for i in items if i.get("status") == "available_now")
    soon = sum(1 for i in items if i.get("status") == "coming_soon")
    dep = sum(1 for i in items if i.get("status") == "deprecation")
    unk = sum(1 for i in items if i.get("status") == "unknown")
    logger.info(
        "Gemini done: total=%d now=%d soon=%d deprecation=%d unknown=%d",
        len(items), now, soon, dep, unk,
    )
    if not any((args.fix_dates, args.apply_guardrails, args.reclassify, args.retranslate)):
        from utils import log_run

        failed = int(LAST_RSS_HEALTH.get("feeds_failed", 0))
        failures = LAST_RSS_HEALTH.get("failures") or []
        log_run(
            "gemini",
            "warning" if failed else "success",
            items_collected=len(items),
            error="; ".join(
                f"{row.get('label')}: {row.get('error')}" for row in failures
            ),
            extra={
                "rss_feeds_total": LAST_RSS_HEALTH.get("feeds_total", 0),
                "rss_feeds_ok": LAST_RSS_HEALTH.get("feeds_ok", 0),
                "rss_feeds_failed": failed,
                "rss_failures": failures,
                "available_now": now,
                "coming_soon": soon,
                "deprecation": dep,
                "unknown": unk,
            },
        )


if __name__ == "__main__":
    main()

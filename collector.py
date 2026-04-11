"""3ソースから AI ニュースを収集し、重複排除して JSONL に保存"""

import json
import logging
import os
import re
import ssl
import urllib.request
from calendar import timegm
from datetime import datetime, timedelta, timezone

import feedparser

from utils import data_dir, hash_url, now_iso, parse_datetime, retry, today_str

logger = logging.getLogger("ai-news.collector")

ssl._create_default_https_context = ssl._create_unverified_context


# ━━━━━━━━━━━━━━━━ X/Twitter (Apify) ━━━━━━━━━━━━━━━━


def _get_apify_usage(token: str) -> dict | None:
    """Apify 月間使用量 API から通算コストを取得"""
    try:
        req = urllib.request.Request(
            "https://api.apify.com/v2/users/me/usage/monthly",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read()).get("data", {})
        return {
            "total": data.get("totalUsageCreditsUsdAfterVolumeDiscount", 0),
            "cycle_end": data.get("usageCycle", {}).get("endAt", ""),
        }
    except Exception:
        return None


def _default_x_runtime_meta() -> dict:
    return {
        "has_apify": False,
        "has_cookies": False,
        "search_queries_configured": 0,
        "search_total": 0,
        "search_error_count": 0,
        "apify_cost_usd": 0.0,
        "apify_runs": 0,
    }


def _should_warn_x_cookies(meta: dict) -> bool:
    """Cookie expiry warning is only valid for clean zero-result searches."""
    return bool(
        meta.get("has_apify")
        and meta.get("has_cookies")
        and meta.get("search_queries_configured", 0) > 0
        and meta.get("search_error_count", 0) == 0
        and meta.get("search_total", 0) == 0
    )


def _collect_x_twitter_with_meta(config: dict) -> tuple[list[dict], dict]:
    meta = _default_x_runtime_meta()
    items = collect_x_twitter(config, runtime_meta=meta)
    return items, meta


def collect_x_twitter(config: dict, runtime_meta: dict | None = None) -> list[dict]:
    """Apify 経由で X/Twitter を収集 (検索 + 必須アカウント)"""
    meta = runtime_meta if runtime_meta is not None else _default_x_runtime_meta()
    token = os.environ.get("APIFY_TOKEN")
    cookies = os.environ.get("X_COOKIES", "")
    meta["has_apify"] = bool(token)
    meta["has_cookies"] = bool(cookies and "auth_token=" in cookies)
    if not token:
        logger.warning("APIFY_TOKEN not set — skipping X/Twitter")
        return []

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.warning("apify-client not installed — skipping X/Twitter")
        return []

    client = ApifyClient(token)
    x_cfg = config.get("x_twitter", {})
    actor_id = x_cfg.get("apify_actor", "get-leads/all-in-one-x-scraper")
    search_queries = x_cfg.get("search_queries", [])
    meta["search_queries_configured"] = len(search_queries)
    items: list[dict] = []
    has_cookies = meta["has_cookies"]

    usage_before = _get_apify_usage(token)

    if has_cookies:
        if not search_queries:
            logger.info("X search queries not configured — skipping search queries")
        for query in search_queries:
            try:
                run_input: dict = {
                    "scrapeMode": "x-tweet-scraper",
                    "searchQueries": [query],
                    "sort": "Top",
                    "maxResults": x_cfg.get("max_results_per_query", 40),
                    "loginCookies": cookies,
                }

                run = client.actor(actor_id).call(run_input=run_input, timeout_secs=120)
                meta["apify_runs"] += 1
                count = 0
                for tweet in client.dataset(run["defaultDatasetId"]).iterate_items():
                    items.append(_normalize_tweet(tweet))
                    count += 1
                meta["search_total"] += count
                logger.info("X search '%s…': %d tweets", query[:40], count)
            except Exception as e:
                meta["search_error_count"] += 1
                logger.error("X search '%s…' failed: %s", query[:40], e)

        if _should_warn_x_cookies(meta):
            logger.warning(
                "⚠️ X search returned 0 results with cookies — "
                "cookies may be expired. Update X_COOKIES secret."
            )
    else:
        logger.info("X_COOKIES not set — skipping search queries (timeline only)")

    must_follow = x_cfg.get("must_follow_accounts", [])
    if must_follow:
        try:
            handles = [acct["handle"] for acct in must_follow]
            priority_map = {acct["handle"].lower(): acct for acct in must_follow}
            run_input: dict = {
                "scrapeMode": "x-timeline-scraper",
                "profiles": handles,
                "maxResults": 10,
                "loginCookies": cookies,
            }

            run = client.actor(actor_id).call(run_input=run_input, timeout_secs=300)
            meta["apify_runs"] += 1
            for tweet in client.dataset(run["defaultDatasetId"]).iterate_items():
                item = _normalize_tweet(tweet)
                author_lower = item["author"].lower()
                acct_cfg = priority_map.get(author_lower, {})
                item["is_must_follow"] = True
                item["is_official"] = acct_cfg.get("priority") == "critical"
                item["priority"] = acct_cfg.get("priority", "normal")
                items.append(item)
            logger.info("X must-follow batch (%d profiles): OK", len(handles))
        except Exception as e:
            logger.error("X must-follow batch failed: %s", e)

    min_eng = x_cfg.get("min_engagement", 0)
    if min_eng > 0:
        before = len(items)
        items = [
            it for it in items
            if it.get("is_must_follow")
            or (it["engagement"].get("likes", 0) + it["engagement"].get("retweets", 0)) >= min_eng
        ]
        logger.info("X engagement filter (>=%d): %d → %d", min_eng, before, len(items))

    if meta["apify_runs"] > 0:
        usage_after = _get_apify_usage(token)
        if usage_before is not None and usage_after is not None:
            meta["apify_cost_usd"] = usage_after["total"] - usage_before["total"]
            meta["apify_cycle_total_usd"] = usage_after["total"]
            meta["apify_cycle_end"] = usage_after.get("cycle_end", "")

    logger.info("X/Twitter total: %d items (Apify: %d runs, $%.4f)", len(items), meta["apify_runs"], meta["apify_cost_usd"])
    return items


def _normalize_tweet(tweet: dict) -> dict:
    url = tweet.get("url") or tweet.get("tweetUrl") or ""
    author_obj = tweet.get("author") or {}
    username = author_obj.get("userName") or tweet.get("username") or "unknown"
    return {
        "id": hash_url(url),
        "source": "x",
        "url": url,
        "title": (tweet.get("text") or "")[:200],
        "content": tweet.get("text") or "",
        "author": username,
        "published_at": tweet.get("createdAt") or "",
        "collected_at": now_iso(),
        "engagement": {
            "likes": tweet.get("likeCount") or tweet.get("likes") or 0,
            "retweets": tweet.get("retweetCount") or tweet.get("retweets") or 0,
            "replies": tweet.get("replyCount") or tweet.get("replies") or 0,
            "views": tweet.get("viewCount") or tweet.get("views") or 0,
            "bookmarks": tweet.get("bookmarkCount") or tweet.get("bookmarks") or 0,
            "quotes": tweet.get("quoteCount") or tweet.get("quotes") or 0,
        },
        "source_name": f"@{username}",
        "priority": "normal",
        "is_official": False,
        "is_must_follow": False,
    }


# ━━━━━━━━━━━━━━━━ RSS ━━━━━━━━━━━━━━━━


def collect_rss(config: dict) -> list[dict]:
    """RSS フィードから収集 (直近 24h)"""
    items: list[dict] = []
    feeds_config = config.get("rss_feeds", {})
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    all_feeds: list[dict] = []
    for group_name, feeds in feeds_config.items():
        for feed in feeds:
            all_feeds.append({**feed, "_group": group_name})

    for fi in all_feeds:
        try:
            entries = _fetch_rss_feed(fi, cutoff)
            items.extend(entries)
            logger.info("RSS '%s': %d entries", fi["name"], len(entries))
        except Exception as e:
            logger.error("RSS '%s' failed: %s", fi["name"], e)

    logger.info("RSS total: %d items", len(items))
    return items


@retry(max_retries=2, base_delay=3)
def _fetch_rss_feed(feed_info: dict, cutoff: datetime) -> list[dict]:
    url = feed_info["url"]
    req = urllib.request.Request(url, headers={"User-Agent": "AI-News-Collector/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read()

    parsed = feedparser.parse(content)
    is_official = feed_info.get("_group") == "official"
    priority = feed_info.get("priority", "normal")
    items: list[dict] = []

    max_entries = feed_info.get("max_entries", 0)
    for entry in parsed.entries:
        if max_entries and len(items) >= max_entries:
            break
        pub_date = _parse_feed_date(entry)
        if pub_date and pub_date < cutoff:
            continue

        entry_url = entry.get("link", "")
        raw = getattr(entry, "summary", "") or getattr(entry, "description", "")
        content_text = re.sub(r"<[^>]+>", "", raw)

        items.append(
            {
                "id": hash_url(entry_url),
                "source": "rss",
                "url": entry_url,
                "title": entry.get("title", ""),
                "content": content_text[:2000],
                "author": entry.get("author", ""),
                "published_at": pub_date.isoformat() if pub_date else "",
                "collected_at": now_iso(),
                "engagement": {},
                "source_name": feed_info["name"],
                "priority": priority,
                "is_official": is_official,
                "is_must_follow": False,
            }
        )
    return items


def _parse_feed_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime.fromtimestamp(timegm(t), tz=timezone.utc)
            except (ValueError, OverflowError):
                pass
    return None


# ━━━━━━━━━━━━━━━━ YouTube ━━━━━━━━━━━━━━━━


def collect_youtube(config: dict) -> list[dict]:
    """YouTube Data API で AI 関連動画を収集"""
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        logger.warning("YOUTUBE_API_KEY not set — skipping YouTube")
        return []

    try:
        from googleapiclient.discovery import build
    except ImportError:
        logger.warning("google-api-python-client not installed — skipping YouTube")
        return []

    youtube = build("youtube", "v3", developerKey=api_key)
    yt_cfg = config.get("youtube", {})
    items: list[dict] = []
    published_after = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    for kw in yt_cfg.get("search_keywords", []):
        try:
            resp = (
                youtube.search()
                .list(
                    q=kw,
                    type="video",
                    publishedAfter=published_after,
                    maxResults=yt_cfg.get("max_results_per_keyword", 20),
                    part="snippet",
                    order="viewCount",
                    relevanceLanguage="en",
                )
                .execute()
            )
            for it in resp.get("items", []):
                items.append(_normalize_video(it))
            logger.info("YouTube '%s': %d videos", kw, len(resp.get("items", [])))
        except Exception as e:
            logger.error("YouTube search '%s' failed: %s", kw, e)

    for ch in yt_cfg.get("must_follow_channels", []):
        try:
            resp = (
                youtube.search()
                .list(
                    channelId=ch["id"],
                    type="video",
                    publishedAfter=published_after,
                    maxResults=10,
                    part="snippet",
                    order="date",
                )
                .execute()
            )
            for it in resp.get("items", []):
                v = _normalize_video(it)
                v["is_must_follow"] = True
                v["source_name"] = ch.get("name", v["source_name"])
                v["priority"] = "high"
                items.append(v)
        except Exception as e:
            logger.error("YouTube channel %s failed: %s", ch.get("name", ch["id"]), e)

    logger.info("YouTube total: %d items", len(items))
    return items


def _normalize_video(item: dict) -> dict:
    vid = item["id"]["videoId"]
    sn = item["snippet"]
    url = f"https://www.youtube.com/watch?v={vid}"
    return {
        "id": hash_url(url),
        "source": "youtube",
        "url": url,
        "title": sn.get("title", ""),
        "content": sn.get("description", "")[:2000],
        "author": sn.get("channelTitle", ""),
        "published_at": sn.get("publishedAt", ""),
        "collected_at": now_iso(),
        "engagement": {},
        "source_name": sn.get("channelTitle", ""),
        "priority": "normal",
        "is_official": False,
        "is_must_follow": False,
    }


# ━━━━━━━━━━━━━━━━ 重複排除 & 永続化 ━━━━━━━━━━━━━━━━


class SeenURLsCache:
    def __init__(self, retention_days: int = 7):
        self.path = data_dir("cache", "seen_urls.json")
        self.retention_days = retention_days
        self.cache = self._load()

    def _load(self) -> dict[str, str]:
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).strftime(
            "%Y-%m-%d"
        )
        return {k: v for k, v in data.items() if v >= cutoff}

    def is_seen(self, url_hash: str) -> bool:
        return url_hash in self.cache

    def mark_seen(self, url_hash: str) -> None:
        self.cache[url_hash] = today_str()

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.cache, f)
        os.replace(tmp, self.path)


def deduplicate(items: list[dict], cache: SeenURLsCache) -> list[dict]:
    unique: list[dict] = []
    seen_in_batch: set[str] = set()

    for item in items:
        uid = item["id"]
        if uid in seen_in_batch or cache.is_seen(uid):
            continue
        seen_in_batch.add(uid)
        cache.mark_seen(uid)
        unique.append(item)

    logger.info("Dedup: %d → %d items (%d removed)", len(items), len(unique), len(items) - len(unique))
    return unique


def _filter_old_items(items: list[dict], max_age_days: int = 7) -> list[dict]:
    """published_at が max_age_days 以上前のアイテムを除外する"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    before = len(items)
    filtered = []
    for item in items:
        pub = parse_datetime(item.get("published_at", ""))
        if pub is None or pub >= cutoff:
            filtered.append(item)
    removed = before - len(filtered)
    if removed:
        logger.info("Age filter (>%dd): %d → %d (%d removed)", max_age_days, before, len(filtered), removed)
    return filtered


def save_daily_jsonl(items: list[dict]) -> str:
    path = data_dir("daily", f"{today_str()}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info("Saved %d items → %s", len(items), path)
    return path


# ━━━━━━━━━━━━━━━━ JSONL 読み込み ━━━━━━━━━━━━━━━━


def _load_latest_daily() -> list[dict]:
    """直近の daily JSONL を読み込んで返す (--analyze-only 用)"""
    daily_dir = data_dir("daily")
    if not os.path.isdir(daily_dir):
        return []
    files = sorted(
        [f for f in os.listdir(daily_dir) if f.endswith(".jsonl")], reverse=True
    )
    if not files:
        return []
    path = os.path.join(daily_dir, files[0])
    items: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    logger.info("Loaded %d items from %s", len(items), path)
    return items


# ━━━━━━━━━━━━━━━━ オーケストレータ ━━━━━━━━━━━━━━━━


def collect_all(config: dict, skip_sources: set[str] | None = None) -> tuple[list[dict], dict]:
    """全ソースから収集し、重複排除して保存"""
    skip = skip_sources or set()
    cache = SeenURLsCache(
        retention_days=config.get("cache", {}).get("seen_urls_retention_days", 7)
    )

    items: list[dict] = []
    runtime_meta = {"x": _default_x_runtime_meta()}
    sources = [
        (lambda: _collect_x_twitter_with_meta(config), "X/Twitter", "x"),
        (lambda: collect_rss(config), "RSS", "rss"),
        (lambda: collect_youtube(config), "YouTube", "youtube"),
    ]

    for source_fn, name, key in sources:
        if key in skip:
            logger.info("Skipping %s (--skip-%s)", name, key)
            continue
        try:
            collected = source_fn()
            if key == "x":
                source_items, runtime_meta["x"] = collected
            else:
                source_items = collected
            items.extend(source_items)
        except Exception as e:
            logger.error("%s collection completely failed: %s", name, e)

    items = deduplicate(items, cache)
    items = _filter_old_items(items, max_age_days=config.get("collection", {}).get("max_age_days", 7))
    save_daily_jsonl(items)
    cache.save()
    return items, runtime_meta

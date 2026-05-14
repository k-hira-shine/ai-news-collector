"""AIツール・機能リリース追跡 — RSS収集モジュール

RSSフィードからAI関連ニュースを取得し data/tools/YYYY-MM-DD.jsonl に保存する。
既存のX/HNデータからツール系記事を抽出する機能も提供する。
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("ai-news.tools_collector")

TOOLS_DIR_NAME = "tools"
SEEN_URLS_CACHE = "tools_seen_urls.json"


def _data_dir(name: str) -> str:
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    return os.path.join(base, name)


def _cache_path() -> str:
    return os.path.join(_data_dir("cache"), SEEN_URLS_CACHE)


def _load_seen_urls() -> set[str]:
    path = _cache_path()
    if not os.path.exists(path):
        return set()
    try:
        data = json.loads(open(path, encoding="utf-8").read())
        return set(data.get("urls", []))
    except Exception:
        return set()


def _save_seen_urls(urls: set[str]) -> None:
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"urls": list(urls)}, f, ensure_ascii=False)
    os.replace(tmp, path)


def _make_id(url: str) -> str:
    return "tool_" + hashlib.md5(url.encode()).hexdigest()[:16]


def collect_rss_feeds(config: dict) -> list[dict]:
    """設定したRSSフィードからニュースを収集して返す"""
    tools_cfg = config.get("tools_tracking", {})
    if not tools_cfg.get("enabled", True):
        logger.info("tools_tracking disabled — skipping RSS collection")
        return []

    try:
        import feedparser  # noqa: F401
    except ImportError:
        logger.error("feedparser not installed — run: pip install feedparser")
        return []

    import feedparser

    feeds = tools_cfg.get("rss_feeds", [])
    max_per_feed = tools_cfg.get("max_items_per_feed", 30)
    max_age_days = tools_cfg.get("max_age_days", 7)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    seen_urls = _load_seen_urls()
    new_items: list[dict] = []
    collected_at = datetime.now(timezone.utc).isoformat()

    for feed_cfg in feeds:
        url = feed_cfg.get("url", "")
        label = feed_cfg.get("label", url)
        if not url:
            continue
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries[:max_per_feed]:
                link = entry.get("link", "")
                if not link or link in seen_urls:
                    continue

                # 日付チェック
                pub = entry.get("published_parsed") or entry.get("updated_parsed")
                pub_dt: datetime | None = None
                if pub:
                    try:
                        import time as _time
                        pub_dt = datetime.fromtimestamp(_time.mktime(pub), tz=timezone.utc)
                    except Exception:
                        pass
                if pub_dt and pub_dt < cutoff:
                    continue

                content = ""
                if entry.get("content"):
                    content = entry.content[0].get("value", "")
                elif entry.get("summary"):
                    content = entry.summary

                # HTMLタグを簡易除去
                import re
                content = re.sub(r"<[^>]+>", " ", content).strip()
                content = re.sub(r"\s+", " ", content)[:2000]

                item: dict[str, Any] = {
                    "id": _make_id(link),
                    "source": "rss",
                    "source_label": label,
                    "title": entry.get("title", "").strip(),
                    "url": link,
                    "content": content,
                    "author": entry.get("author", ""),
                    "published_at": pub_dt.isoformat() if pub_dt else "",
                    "collected_at": collected_at,
                }
                new_items.append(item)
                seen_urls.add(link)
                count += 1

            logger.info("RSS [%s]: %d new items", label, count)
        except Exception as e:
            logger.warning("RSS fetch failed [%s]: %s", label, e)

    _save_seen_urls(seen_urls)
    logger.info("RSS collection total: %d new items", len(new_items))
    return new_items


def collect_reddit_posts(config: dict) -> list[dict]:
    """Reddit Data APIからAI関連subredditの投稿を収集して返す。

    必要なSecrets:
      REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET / REDDIT_USERNAME / REDDIT_PASSWORD
    未設定または承認前の場合は安全にスキップする。
    """
    tools_cfg = config.get("tools_tracking", {})
    reddit_cfg = tools_cfg.get("reddit", {})
    if not reddit_cfg.get("enabled", False):
        return []

    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    username = os.environ.get("REDDIT_USERNAME")
    password = os.environ.get("REDDIT_PASSWORD")
    if not all([client_id, client_secret, username, password]):
        logger.info("Reddit credentials not set — skipping Reddit collection")
        return []

    try:
        import requests
    except ImportError:
        logger.error("requests not installed — skipping Reddit collection")
        return []

    user_agent = reddit_cfg.get(
        "user_agent",
        f"python:ai-news-collector:v1.0 (by /u/{username})",
    )
    headers = {"User-Agent": user_agent}

    try:
        token_resp = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(client_id, client_secret),
            data={
                "grant_type": "password",
                "username": username,
                "password": password,
            },
            headers=headers,
            timeout=20,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json().get("access_token")
        if not access_token:
            logger.warning("Reddit token response missing access_token")
            return []
    except Exception as e:
        logger.warning("Reddit OAuth failed — likely pending approval or invalid credentials: %s", e)
        return []

    api_headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": user_agent,
    }
    subreddits = reddit_cfg.get("subreddits", [])
    max_items = int(reddit_cfg.get("max_items_per_subreddit", 25))
    sort = reddit_cfg.get("sort", "new")
    time_filter = reddit_cfg.get("time_filter", "day")

    seen_urls = _load_seen_urls()
    new_items: list[dict] = []
    collected_at = datetime.now(timezone.utc).isoformat()

    for subreddit in subreddits:
        subreddit = str(subreddit).strip().lstrip("r/")
        if not subreddit:
            continue
        endpoint = f"https://oauth.reddit.com/r/{subreddit}/{sort}"
        params: dict[str, Any] = {"limit": max_items}
        if sort == "top":
            params["t"] = time_filter

        try:
            resp = requests.get(endpoint, headers=api_headers, params=params, timeout=20)
            resp.raise_for_status()
            children = (resp.json().get("data") or {}).get("children") or []
            count = 0
            for child in children:
                data = child.get("data") or {}
                permalink = data.get("permalink") or ""
                url = f"https://www.reddit.com{permalink}" if permalink else data.get("url", "")
                if not url or url in seen_urls:
                    continue

                created_utc = data.get("created_utc")
                published_at = ""
                if created_utc:
                    try:
                        published_at = datetime.fromtimestamp(float(created_utc), tz=timezone.utc).isoformat()
                    except Exception:
                        published_at = ""

                title = (data.get("title") or "").strip()
                selftext = (data.get("selftext") or "").strip()
                link_url = data.get("url") or ""
                content = selftext or title
                if link_url and link_url != url:
                    content = f"{content}\n\nLink: {link_url}".strip()

                item: dict[str, Any] = {
                    "id": "reddit_" + data.get("id", _make_id(url)),
                    "source": "reddit",
                    "source_label": f"Reddit r/{subreddit}",
                    "title": title,
                    "url": url,
                    "content": content[:2000],
                    "author": data.get("author", ""),
                    "published_at": published_at,
                    "collected_at": collected_at,
                    "reddit_score": data.get("score", 0),
                    "reddit_comments": data.get("num_comments", 0),
                    "reddit_subreddit": subreddit,
                }
                new_items.append(item)
                seen_urls.add(url)
                count += 1
            logger.info("Reddit [r/%s]: %d new items", subreddit, count)
        except Exception as e:
            logger.warning("Reddit fetch failed [r/%s]: %s", subreddit, e)

    _save_seen_urls(seen_urls)
    logger.info("Reddit collection total: %d new items", len(new_items))
    return new_items


def extract_from_x(x_items: list[dict]) -> list[dict]:
    """既存のX収集データからツール・リリース系っぽい記事を抽出する（簡易キーワードフィルタ）"""
    TOOL_KEYWORDS = [
        "launch", "release", "update", "new feature", "now available", "announcing",
        "introduce", "リリース", "発表", "新機能", "アップデート", "登場", "公開",
        "claude", "chatgpt", "gemini", "copilot", "cursor", "perplexity",
        "gpt-", "claude-", "llama", "mistral", "grok", "sora", "dall-e",
        "openai", "anthropic", "google deepmind", "meta ai",
    ]
    results = []
    collected_at = datetime.now(timezone.utc).isoformat()
    for item in x_items:
        text = (item.get("content") or item.get("text") or "").lower()
        title = (item.get("title") or "").lower()
        combined = text + " " + title
        if any(kw in combined for kw in TOOL_KEYWORDS):
            results.append({
                "id": "xtool_" + item.get("id", _make_id(item.get("url", ""))),
                "source": "x",
                "source_label": "X (Twitter)",
                "title": item.get("title") or (item.get("content") or "")[:80],
                "url": item.get("url", ""),
                "content": (item.get("content") or "")[:2000],
                "author": item.get("author") or item.get("author_display") or "",
                "published_at": item.get("published_at") or item.get("collected_at") or "",
                "collected_at": collected_at,
            })
    logger.info("X tool extraction: %d items", len(results))
    return results


def extract_from_hn(hn_items: list[dict]) -> list[dict]:
    """既存のHN/arxivデータからツール・リリース系記事を抽出する"""
    TOOL_KEYWORDS = [
        "launch", "release", "new model", "new version", "open source", "api",
        "benchmark", "claude", "gpt", "gemini", "llama", "mistral", "openai",
        "anthropic", "google", "meta", "microsoft", "nvidia",
    ]
    results = []
    collected_at = datetime.now(timezone.utc).isoformat()
    for item in hn_items:
        title = (item.get("title") or item.get("title_en") or "").lower()
        content = (item.get("content") or item.get("arxiv_summary") or "").lower()
        combined = title + " " + content
        if any(kw in combined for kw in TOOL_KEYWORDS):
            source = item.get("source", "hn")
            results.append({
                "id": "hntool_" + item.get("id", _make_id(item.get("url", ""))),
                "source": source,
                "source_label": "HackerNews" if source == "hn" else "arxiv",
                "title": item.get("title") or item.get("title_en") or "",
                "url": item.get("url") or item.get("hn_item_url") or "",
                "content": (item.get("content") or item.get("arxiv_summary") or "")[:2000],
                "author": item.get("author") or "",
                "published_at": item.get("published_at") or "",
                "collected_at": collected_at,
            })
    logger.info("HN tool extraction: %d items", len(results))
    return results


def deduplicate_tools(items: list[dict]) -> list[dict]:
    """URLベースで重複排除"""
    seen: set[str] = set()
    result = []
    for item in items:
        url = item.get("url", "")
        key = url or item.get("id", "")
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def save_tools_jsonl(items: list[dict]) -> str:
    """data/tools/YYYY-MM-DD.jsonl に追記保存して保存パスを返す"""
    if not items:
        return ""
    out_dir = _data_dir(TOOLS_DIR_NAME)
    os.makedirs(out_dir, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(out_dir, f"{today}.jsonl")

    # 既存のIDを読んで重複を避ける
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

    new_items = [i for i in items if i.get("id", "") not in existing_ids]
    if not new_items:
        logger.info("All %d items already saved", len(items))
        return path

    with open(path, "a", encoding="utf-8") as f:
        for item in new_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("Saved %d new tools items → %s", len(new_items), path)
    return path


def load_all_tools_items(days: int = 30) -> list[dict]:
    """data/tools/ から直近 days 日分を全件ロードして返す"""
    out_dir = _data_dir(TOOLS_DIR_NAME)
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

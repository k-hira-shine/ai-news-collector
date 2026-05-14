"""SNS成功者マインド・思考法コレクター

Xキーワード検索で「SNSで成功した人の思考法・習慣・マインドセット」に関する
ポストを収集し、data/sns_success/ に蓄積する。
"""

import json
import logging
import os
from datetime import datetime, timezone

import requests

from collector import _normalize_tweet
from utils import data_dir, today_str

logger = logging.getLogger("ai-news.sns_collector")

SNS_CACHE_PATH = data_dir("cache", "sns_seen_urls.json")
SNS_ARTICLE_CACHE_PATH = data_dir("cache", "sns_x_articles.json")
SNS_DATA_DIR = data_dir("sns_success")


def collect_sns_success(config: dict) -> tuple[list[dict], dict]:
    """SNS成功者マインド関連ポストを収集する"""
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        logger.warning("APIFY_TOKEN not set — skipping sns_success collection")
        return [], {"error": "no_token"}

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.warning("apify-client not installed — skipping sns_success collection")
        return [], {"error": "no_apify_client"}

    client = ApifyClient(token)
    sns_cfg = config.get("sns_success", {})
    actor_id = config.get("x_twitter", {}).get("apify_actor", "xquik/x-tweet-scraper")

    accounts = sns_cfg.get("accounts", [])
    max_items_per_account = sns_cfg.get("max_items_per_account", 150)
    search_queries = sns_cfg.get("search_queries", [])
    max_items_per_query = sns_cfg.get("max_items_per_query", 100)
    search_since_days = sns_cfg.get("search_since_days", 90)
    account_since_days = sns_cfg.get("account_since_days", 365)

    if not accounts and not search_queries:
        logger.warning("No sns_success accounts or search_queries configured")
        return [], {"error": "no_queries"}

    import threading
    meta = {"apify_runs": 0, "apify_cost_usd": 0.0, "total_fetched": 0}
    _meta_lock = threading.Lock()
    article_cache = _load_article_cache()
    all_items: list[dict] = []

    def _run_apify(search_terms: list[str], max_items_each: int, label: str, query_type: str = "Top", since_days: int | None = 90) -> list[dict]:
        """Apifyを1回起動してツイートを取得し正規化して返す"""
        from datetime import timedelta
        run_input = {
            "searchTerms": search_terms,
            "queryType": query_type,
            "maxItems": max_items_each,
            "includeSearchTerms": True,
        }
        if since_days:
            run_input["since"] = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")
        logger.info(
            "SNS collection [%s]: %d queries × up to %d posts (%s, since_days=%s)",
            label, len(search_terms), max_items_each, query_type, since_days or "none",
        )
        run = client.actor(actor_id).call(run_input=run_input, timeout_secs=600)
        with _meta_lock:
            meta["apify_runs"] += 1
            meta["apify_cost_usd"] += float((run or {}).get("usageTotalUsd") or 0)
        run_status = (run or {}).get("status", "")
        if run_status != "SUCCEEDED":
            logger.error("SNS collection [%s] run status=%s", label, run_status)
            return []
        items = []
        for tweet in client.dataset(run["defaultDatasetId"]).iterate_items():
            item = _normalize_tweet(tweet)
            item["sns_source"] = True
            author_obj = tweet.get("author") or {}
            item["author_display"] = author_obj.get("name") or item["author"]
            item["author_followers"] = author_obj.get("followers") or author_obj.get("followersCount") or 0
            _enrich_x_article(item, tweet, article_cache)
            media = []
            for m in tweet.get("media") or []:
                murl = m.get("url") or m.get("previewUrl") or ""
                if murl:
                    media.append({"type": m.get("type", "photo"), "url": murl})
            item["media"] = media
            items.append(item)
        logger.info("SNS collection [%s]: got %d posts", label, len(items))
        return items

    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if accounts:
            account_queries = [f"from:{acct['handle']} -filter:retweets" for acct in accounts]
            all_items += _run_apify(
                account_queries,
                max_items_per_account,
                "accounts",
                query_type="Latest",
                since_days=account_since_days,
            )

        ja_queries = [q for q in search_queries if "lang:en" not in q]
        en_queries = [q for q in search_queries if "lang:en" in q]

        batches: list[tuple[list[str], int, str]] = []

        batch_size = 3
        for i in range(0, len(ja_queries), batch_size):
            batches.append((ja_queries[i:i + batch_size], max_items_per_query, f"ja_{i//batch_size+1}"))

        for i in range(0, len(en_queries), batch_size):
            batches.append((en_queries[i:i + batch_size], max_items_per_query, f"en_{i//batch_size+1}"))

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_run_apify, q, n, lbl, "Top", search_since_days): lbl for q, n, lbl in batches}
            for fut in futures:
                lbl = futures[fut]
                try:
                    all_items += fut.result()
                except Exception as e:
                    logger.error("Batch %s failed: %s", lbl, e)

        meta["total_fetched"] = len(all_items)
        logger.info("SNS collection total: %d posts (cost=$%.4f)", len(all_items), meta["apify_cost_usd"])

    except Exception as e:
        logger.error("SNS collection failed: %s", e)
        meta["error"] = str(e)[:200]

    _save_article_cache(article_cache)
    return all_items, meta


def _find_x_article_url(tweet: dict) -> str:
    """Apifyの生tweetから x.com/i/article/... URL を探す。"""
    entities = tweet.get("entities") or {}
    for url_obj in entities.get("urls") or []:
        expanded = url_obj.get("expanded_url") or url_obj.get("expandedUrl") or ""
        if "x.com/i/article/" in expanded or "twitter.com/i/article/" in expanded:
            return expanded.replace("http://", "https://")
    return ""


def _article_blocks_to_text(blocks: list[dict]) -> str:
    """Xquik Article API の content blocks を読みやすい本文に変換する。"""
    lines: list[str] = []
    for block in blocks or []:
        text = (block.get("text") or "").strip()
        if not text:
            continue
        block_type = block.get("type", "")
        if block_type.startswith("header-"):
            lines.append(f"\n{text}\n")
        elif block_type == "ordered-list-item":
            lines.append(f"1. {text}")
        elif block_type == "unordered-list-item":
            lines.append(f"- {text}")
        elif block_type == "blockquote":
            lines.append(f"> {text}")
        else:
            lines.append(text)
    return "\n".join(lines).strip()


def _fetch_x_article(tweet_id: str) -> dict:
    """X Article本文をXquik APIで取得する。APIキーまたはX_COOKIESがない場合は空dict。"""
    api_key = os.environ.get("XQUIK_API_KEY")
    x_cookies = os.environ.get("X_COOKIES")
    if not api_key and not x_cookies:
        return {}

    url = f"https://xquik.com/api/v1/x/articles/{tweet_id}"
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    if x_cookies:
        headers["Cookie"] = x_cookies
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json() or {}
    except Exception as e:
        logger.warning("Failed to fetch X Article %s: %s", tweet_id, e)
        return {}


def _enrich_x_article(item: dict, tweet: dict, article_cache: dict) -> None:
    """X Articleリンク付き投稿なら本文を取得し、content/titleを記事本文で補完する。"""
    article_url = _find_x_article_url(tweet)
    if not article_url:
        return

    tweet_id = str(tweet.get("id") or item.get("url", "").rsplit("/", 1)[-1])
    item["article_url"] = article_url
    item["article_source"] = "x_article"

    article = article_cache.get(tweet_id)
    if not article:
        article = _fetch_x_article(tweet_id)
        if article:
            article_cache[tweet_id] = article

    if not article:
        return

    article_obj = article.get("article") or article
    title = article_obj.get("title") or ""
    preview = article_obj.get("previewText") or article_obj.get("preview_text") or ""
    full_text = article_obj.get("full_text") or ""
    if not full_text:
        full_text = _article_blocks_to_text(article_obj.get("contents") or [])

    if full_text:
        item["article_title"] = title
        item["article_preview"] = preview
        item["article_content"] = full_text
        item["title"] = title or preview or item.get("title", "")
        item["content"] = full_text


def deduplicate_sns(items: list[dict]) -> list[dict]:
    """sns_success専用の重複排除キャッシュ（長期保持）"""
    cache = _load_sns_cache()
    unique = []
    seen_in_batch: set[str] = set()
    for item in items:
        uid = item["id"]
        if uid in seen_in_batch or uid in cache:
            continue
        seen_in_batch.add(uid)
        cache[uid] = today_str()
        unique.append(item)
    _save_sns_cache(cache)
    logger.info("SNS dedup: %d → %d (removed %d)", len(items), len(unique), len(items) - len(unique))
    return unique


def _load_sns_cache() -> dict[str, str]:
    try:
        with open(SNS_CACHE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_sns_cache(cache: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(SNS_CACHE_PATH), exist_ok=True)
    tmp = SNS_CACHE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cache, f)
    os.replace(tmp, SNS_CACHE_PATH)


def _load_article_cache() -> dict:
    try:
        with open(SNS_ARTICLE_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_article_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(SNS_ARTICLE_CACHE_PATH), exist_ok=True)
    tmp = SNS_ARTICLE_CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, SNS_ARTICLE_CACHE_PATH)


def save_sns_jsonl(items: list[dict]) -> str:
    """data/sns_success/YYYY-MM-DD.jsonl に追記保存"""
    os.makedirs(SNS_DATA_DIR, exist_ok=True)
    path = os.path.join(SNS_DATA_DIR, f"{today_str()}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info("Saved %d sns items → %s", len(items), path)
    return path


def load_all_sns_items() -> list[dict]:
    """data/sns_success/ の全 JSONL を読み込んで返す（ページ生成用）"""
    if not os.path.isdir(SNS_DATA_DIR):
        return []
    items: list[dict] = []
    for fname in sorted(os.listdir(SNS_DATA_DIR)):
        if not fname.endswith(".jsonl"):
            continue
        path = os.path.join(SNS_DATA_DIR, fname)
        with open(path, encoding="utf-8") as f:
            for line in f.read().split("\n"):
                line = line.strip()
                if line:
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    logger.info("Loaded %d total sns items from %s", len(items), SNS_DATA_DIR)
    return items

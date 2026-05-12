"""AIマネタイズ事例コレクター

@fiction_log など指定アカウントのポストを取得し、
data/money/ に蓄積する（since制限なし・リポスト除外）。
"""

import json
import logging
import os
from datetime import datetime, timezone

from collector import SeenURLsCache, _normalize_tweet
from utils import data_dir, hash_url, today_str

logger = logging.getLogger("ai-news.money_collector")

MONEY_CACHE_PATH = data_dir("cache", "money_seen_urls.json")
MONEY_DATA_DIR = data_dir("money")


def collect_money_cases(config: dict) -> tuple[list[dict], dict]:
    """AIマネタイズ事例アカウントのポストを収集する"""
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        logger.warning("APIFY_TOKEN not set — skipping money collection")
        return [], {"error": "no_token"}

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.warning("apify-client not installed — skipping money collection")
        return [], {"error": "no_apify_client"}

    client = ApifyClient(token)
    money_cfg = config.get("money_collection", {})
    actor_id = config.get("x_twitter", {}).get("apify_actor", "xquik/x-tweet-scraper")

    accounts = money_cfg.get("accounts", [{"handle": "fiction_log", "label": "ろじん|Levela CXO"}])
    max_items = money_cfg.get("max_items_per_account", 500)

    meta = {"apify_runs": 0, "apify_cost_usd": 0.0, "total_fetched": 0}
    all_items: list[dict] = []

    # アカウントごとに取得（リポスト除外: -filter:retweets）
    account_queries = [f"from:{acct['handle']} -filter:retweets" for acct in accounts]

    try:
        run_input = {
            "searchTerms": account_queries,
            "queryType": "Latest",
            "maxItems": max_items,
            "includeSearchTerms": True,
            # since なし → 期間制限なし
        }
        logger.info("Money collection: fetching %d accounts × up to %d posts", len(accounts), max_items)
        run = client.actor(actor_id).call(run_input=run_input, timeout_secs=600)
        meta["apify_runs"] += 1
        meta["apify_cost_usd"] += float((run or {}).get("usageTotalUsd") or 0)

        run_status = (run or {}).get("status", "")
        if run_status != "SUCCEEDED":
            logger.error("Money collection run status=%s", run_status)
            meta["error"] = f"run_status={run_status}"
            return [], meta

        for tweet in client.dataset(run["defaultDatasetId"]).iterate_items():
            item = _normalize_tweet(tweet)
            item["money_source"] = True
            # 投稿者情報を保持
            author_obj = tweet.get("author") or {}
            item["author_display"] = author_obj.get("name") or item["author"]
            item["author_followers"] = author_obj.get("followers") or author_obj.get("followersCount") or 0
            # 画像・動画のURLを保持
            media = []
            for m in tweet.get("media") or []:
                url = m.get("url") or m.get("previewUrl") or ""
                if url:
                    media.append({"type": m.get("type", "photo"), "url": url})
            item["media"] = media
            all_items.append(item)

        meta["total_fetched"] = len(all_items)
        logger.info("Money collection: fetched %d posts (cost=$%.4f)", len(all_items), meta["apify_cost_usd"])

    except Exception as e:
        logger.error("Money collection failed: %s", e)
        meta["error"] = str(e)[:200]

    return all_items, meta


def deduplicate_money(items: list[dict]) -> list[dict]:
    """money専用の重複排除キャッシュ（長期保持）"""
    cache = _load_money_cache()
    unique = []
    seen_in_batch: set[str] = set()
    for item in items:
        uid = item["id"]
        if uid in seen_in_batch or uid in cache:
            continue
        seen_in_batch.add(uid)
        cache[uid] = today_str()
        unique.append(item)
    _save_money_cache(cache)
    logger.info("Money dedup: %d → %d (removed %d)", len(items), len(unique), len(items) - len(unique))
    return unique


def _load_money_cache() -> dict[str, str]:
    try:
        with open(MONEY_CACHE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_money_cache(cache: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(MONEY_CACHE_PATH), exist_ok=True)
    tmp = MONEY_CACHE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cache, f)
    os.replace(tmp, MONEY_CACHE_PATH)


def save_money_jsonl(items: list[dict]) -> str:
    """data/money/YYYY-MM-DD.jsonl に追記保存"""
    os.makedirs(MONEY_DATA_DIR, exist_ok=True)
    path = os.path.join(MONEY_DATA_DIR, f"{today_str()}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info("Saved %d money items → %s", len(items), path)
    return path


def load_all_money_items() -> list[dict]:
    """data/money/ の全 JSONL を読み込んで返す（ページ生成用）"""
    if not os.path.isdir(MONEY_DATA_DIR):
        return []
    items: list[dict] = []
    for fname in sorted(os.listdir(MONEY_DATA_DIR)):
        if not fname.endswith(".jsonl"):
            continue
        path = os.path.join(MONEY_DATA_DIR, fname)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    logger.info("Loaded %d total money items from %s", len(items), MONEY_DATA_DIR)
    return items

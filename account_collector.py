"""Money/SNSで共有するXアカウント差分コレクター。"""

import json
import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from collector import _normalize_tweet
from utils import apify_actor_call, apify_run_get, clamp_max_items, data_dir

logger = logging.getLogger("ai-news.account_collector")

STATE_PATH = data_dir("cache", "shared_account_collection_state.json")


def _load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"accounts": {}}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, STATE_PATH)


def _account_since_date(last_success: str | None, overlap_days: int, initial_days: int) -> str:
    if last_success:
        return (date.fromisoformat(last_success) - timedelta(days=overlap_days)).isoformat()
    return (datetime.now(timezone.utc).date() - timedelta(days=initial_days)).isoformat()


def _normalize_account_tweet(tweet: dict) -> dict:
    item = _normalize_tweet(tweet)
    author = tweet.get("author") or {}
    item["author_display"] = author.get("name") or item["author"]
    item["author_followers"] = author.get("followers") or author.get("followersCount") or 0
    item["media"] = [
        {"type": media.get("type", "photo"), "url": url}
        for media in (tweet.get("media") or [])
        if (url := media.get("url") or media.get("previewUrl") or "")
    ]
    item["_raw_tweet"] = tweet
    return item


def collect_shared_accounts(config: dict, accounts: list[dict]) -> tuple[list[dict], dict]:
    """指定アカウントを最終成功日から差分取得する。"""
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        return [], {"error": "no_token", "apify_runs": 0, "apify_cost_usd": 0.0}

    try:
        from apify_client import ApifyClient
    except ImportError:
        return [], {"error": "no_apify_client", "apify_runs": 0, "apify_cost_usd": 0.0}

    unique_accounts = {}
    for account in accounts:
        handle = account.get("handle", "").strip().lstrip("@")
        if handle:
            unique_accounts.setdefault(handle.lower(), handle)
    if not unique_accounts:
        return [], {"apify_runs": 0, "apify_cost_usd": 0.0, "total_fetched": 0}

    settings = config.get("shared_account_collection", {})
    overlap_days = max(1, int(settings.get("overlap_days", 2)))
    initial_days = max(overlap_days, int(settings.get("initial_lookback_days", 365)))
    max_items = clamp_max_items(settings.get("max_items_per_account", 100), "shared_account_collection.max_items_per_account")
    actor_id = config.get("x_twitter", {}).get("apify_actor", "xquik/x-tweet-scraper")
    state = _load_state()
    account_state = state.setdefault("accounts", {})

    groups: dict[str, list[str]] = defaultdict(list)
    for key, handle in unique_accounts.items():
        last_success = (account_state.get(key) or {}).get("last_success_date")
        groups[_account_since_date(last_success, overlap_days, initial_days)].append(handle)

    client = ApifyClient(token)
    items = []
    meta = {"apify_runs": 0, "apify_cost_usd": 0.0, "total_fetched": 0}
    success_date = datetime.now(timezone.utc).date().isoformat()

    for since_date, handles in sorted(groups.items()):
        run_input = {
            "searchTerms": [f"from:{handle} -filter:retweets" for handle in handles],
            "queryType": "Latest",
            "maxItems": max_items,
            "includeSearchTerms": True,
            "since": since_date,
        }
        logger.info(
            "Shared account collection: %d accounts since %s, max %d each",
            len(handles), since_date, max_items,
        )
        run = apify_actor_call(client.actor(actor_id), run_input=run_input, wait_seconds=600)
        meta["apify_runs"] += 1
        meta["apify_cost_usd"] += float(apify_run_get(run, "usageTotalUsd") or 0)
        if apify_run_get(run, "status", "") != "SUCCEEDED":
            logger.error("Shared account collection failed for since=%s", since_date)
            continue

        for tweet in client.dataset(apify_run_get(run, "defaultDatasetId")).iterate_items():
            items.append(_normalize_account_tweet(tweet))
        for handle in handles:
            account_state[handle.lower()] = {"last_success_date": success_date}

    meta["total_fetched"] = len(items)
    if meta["apify_runs"]:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)
    logger.info(
        "Shared account collection: %d posts, %d runs, cost=$%.4f",
        len(items), meta["apify_runs"], meta["apify_cost_usd"],
    )
    return items, meta


def items_for_accounts(items: list[dict], accounts: list[dict]) -> list[dict]:
    handles = {
        account.get("handle", "").strip().lstrip("@").lower()
        for account in accounts
        if account.get("handle")
    }
    return [item.copy() for item in items if item.get("author", "").lower() in handles]

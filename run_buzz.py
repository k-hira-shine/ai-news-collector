#!/usr/bin/env python3
"""バズりランキング収集スクリプト

指定アカウントの直近30日のポストをApifyで取得し、
いいね数でランキングして data/buzz.json に保存する。

使い方:
  python run_buzz.py                    # config.yaml の buzz_accounts を全取得
  python run_buzz.py --add fiction_log  # 指定アカウントを追加取得してマージ
  python run_buzz.py --accounts taziku_co rute1203d  # 指定アカウントのみ取得
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

BASE = Path(__file__).parent
BUZZ_JSON = BASE / "data" / "buzz.json"
CONFIG_YAML = BASE / "config.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_buzz")

JST = timezone(timedelta(hours=9))


def load_config() -> dict:
    with open(CONFIG_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_accounts_batch(client, actor_id: str, handles: list[str], days: int = 30, max_items: int = 100) -> dict[str, list[dict]]:
    """複数アカウントを1回のApify起動でまとめて取得"""
    since_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    search_terms = [f"from:{h} -filter:retweets" for h in handles]
    run_input = {
        "searchTerms": search_terms,
        "queryType": "Latest",
        "maxItems": max_items,  # アカウントごとの上限
        "includeSearchTerms": True,
        "since": since_date,
    }
    logger.info("Fetching %d accounts in 1 batch (last %d days, max %d each) ...", len(handles), days, max_items)
    run = client.actor(actor_id).call(run_input=run_input, timeout_secs=300)
    cost = float((run or {}).get("usageTotalUsd") or 0)
    status = (run or {}).get("status", "")
    if status != "SUCCEEDED":
        logger.error("Batch run status=%s", status)
        return {}

    # アカウントごとに仕分け
    result: dict[str, list[dict]] = {h: [] for h in handles}
    total = 0
    for tweet in client.dataset(run["defaultDatasetId"]).iterate_items():
        author = (tweet.get("author") or {}).get("userName") or tweet.get("userName") or tweet.get("username") or ""
        author_lower = author.lower()
        for h in handles:
            if h.lower() == author_lower:
                result[h].append(tweet)
                break
        total += 1
    logger.info("Batch done: %d tweets total, cost=$%.4f", total, cost)
    for h in handles:
        logger.info("  @%s: %d tweets", h, len(result[h]))
    return result


def fetch_account_tweets(client, actor_id: str, handle: str, days: int = 30, max_items: int = 100) -> list[dict]:
    """単一アカウント取得（追加時などに使用）"""
    result = fetch_accounts_batch(client, actor_id, [handle], days=days, max_items=max_items)
    return result.get(handle, [])


def normalize_tweet(tweet: dict) -> dict:
    author = tweet.get("author") or {}
    return {
        "url": tweet.get("url") or tweet.get("tweetUrl") or "",
        "text": (tweet.get("text") or tweet.get("fullText") or "")[:500],
        "likes": tweet.get("likeCount") or tweet.get("likes") or 0,
        "retweets": tweet.get("retweetCount") or tweet.get("retweets") or 0,
        "replies": tweet.get("replyCount") or tweet.get("replies") or 0,
        "views": tweet.get("viewCount") or tweet.get("views") or 0,
        "created_at": tweet.get("createdAt") or tweet.get("created_at") or "",
        "author_followers": author.get("followers") or author.get("followersCount") or 0,
        "eng_rate": None,  # フォロワー数があれば計算
    }


def build_account_data(handle: str, display_name: str, tweets: list[dict]) -> dict:
    normalized = [normalize_tweet(t) for t in tweets]
    # いいね数でソート
    normalized.sort(key=lambda x: x["likes"], reverse=True)
    # エンゲージメント率を計算
    for t in normalized:
        followers = t.get("author_followers") or 0
        if followers > 0:
            t["eng_rate"] = round((t["likes"] + t["retweets"]) / followers * 100, 4)
    # 中央値（いいね）
    likes_list = sorted([t["likes"] for t in normalized if t["likes"] > 0])
    median = likes_list[len(likes_list) // 2] if likes_list else None
    return {
        "account": handle,
        "display_name": display_name,
        "snap_date": datetime.now(JST).strftime("%Y/%m/%d %H:%M JST"),
        "median_likes": median,
        "tweets": normalized,
    }


def load_existing_buzz() -> dict:
    if BUZZ_JSON.exists():
        try:
            return json.loads(BUZZ_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"updated_at": "", "accounts": []}


def save_buzz(data: dict) -> None:
    data["updated_at"] = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    BUZZ_JSON.parent.mkdir(parents=True, exist_ok=True)
    BUZZ_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved → %s (%d accounts)", BUZZ_JSON, len(data["accounts"]))


def get_display_name(handle: str, config: dict) -> str:
    """config.yaml の buzz_accounts から表示名を取得。なければハンドルをそのまま使う"""
    for ac in config.get("buzz_accounts", []):
        if ac.get("handle", "").lower() == handle.lower():
            return ac.get("display_name", handle)
    return handle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--add", metavar="HANDLE", help="このアカウントを追加取得してbuzz.jsonにマージ")
    parser.add_argument("--accounts", nargs="+", metavar="HANDLE", help="このアカウントのみ取得（スペース区切り）")
    parser.add_argument("--days", type=int, default=30, help="何日前まで遡るか（デフォルト30）")
    parser.add_argument("--max-items", type=int, default=200, help="アカウントあたりの最大取得件数")
    args = parser.parse_args()

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        logger.error("APIFY_TOKEN not set")
        sys.exit(1)

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.error("apify-client not installed")
        sys.exit(1)

    client = ApifyClient(token)
    config = load_config()
    actor_id = config.get("x_twitter", {}).get("apify_actor", "xquik/x-tweet-scraper")

    existing = load_existing_buzz()
    existing_map = {ac["account"]: ac for ac in existing.get("accounts", [])}

    if args.add:
        # 1アカウントだけ追加・更新してマージ
        handle = args.add.lstrip("@")
        display_name = get_display_name(handle, config)
        tweets = fetch_account_tweets(client, actor_id, handle, days=args.days, max_items=args.max_items)
        if tweets:
            existing_map[handle] = build_account_data(handle, display_name, tweets)
            # config.yaml に未登録なら追加
            _ensure_in_config(handle, display_name)
        existing["accounts"] = list(existing_map.values())

    elif args.accounts:
        # 指定アカウントのみ取得
        for handle in args.accounts:
            handle = handle.lstrip("@")
            display_name = get_display_name(handle, config)
            tweets = fetch_account_tweets(client, actor_id, handle, days=args.days, max_items=args.max_items)
            if tweets:
                existing_map[handle] = build_account_data(handle, display_name, tweets)
        existing["accounts"] = list(existing_map.values())

    else:
        # config.yaml の buzz_accounts を全取得（1回のApify起動でまとめて）
        buzz_accounts = config.get("buzz_accounts", [])
        if not buzz_accounts:
            logger.warning("buzz_accounts not configured in config.yaml")
            sys.exit(0)
        handles = [ac["handle"].lstrip("@") for ac in buzz_accounts]
        display_map = {ac["handle"].lstrip("@"): ac.get("display_name", ac["handle"]) for ac in buzz_accounts}
        batch_result = fetch_accounts_batch(client, actor_id, handles, days=args.days, max_items=args.max_items)
        for handle, tweets in batch_result.items():
            if tweets:
                existing_map[handle] = build_account_data(handle, display_map.get(handle, handle), tweets)
        existing["accounts"] = list(existing_map.values())

    save_buzz(existing)

    # buzz.html を再生成
    try:
        import build_buzz
        build_buzz.build()
    except Exception as e:
        logger.warning("build_buzz failed: %s", e)


def _ensure_in_config(handle: str, display_name: str) -> None:
    """config.yaml の buzz_accounts に未登録なら追記する"""
    with open(CONFIG_YAML, encoding="utf-8") as f:
        content = f.read()
    config = yaml.safe_load(content)
    accounts = config.get("buzz_accounts", [])
    handles_lower = [a.get("handle", "").lower() for a in accounts]
    if handle.lower() not in handles_lower:
        # YAMLに追記
        new_entry = f"\n  - handle: \"{handle}\"\n    display_name: \"{display_name}\""
        if "buzz_accounts:" in content:
            content = content.replace("buzz_accounts:", f"buzz_accounts:{new_entry}", 1)
        else:
            content += f"\nbuzz_accounts:{new_entry}\n"
        with open(CONFIG_YAML, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Added @%s to config.yaml buzz_accounts", handle)


if __name__ == "__main__":
    main()

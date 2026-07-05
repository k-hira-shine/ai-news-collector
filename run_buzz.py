#!/usr/bin/env python3
"""バズりランキング収集スクリプト

指定アカウントの最近のポストをApifyで差分取得し、既存の30日分と
マージして、いいね数ランキングを data/buzz.json に保存する。

使い方:
  python run_buzz.py                    # config.yaml の buzz_accounts を全取得
  python run_buzz.py --add fiction_log  # 指定アカウントを追加取得してマージ
  python run_buzz.py --accounts taziku_co rute1203d  # 指定アカウントのみ取得
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from utils import clamp_max_items

BASE = Path(__file__).parent
BUZZ_JSON = BASE / "data" / "buzz.json"
BUZZ_METRICS_JSONL = BASE / "data" / "buzz_collection_metrics.jsonl"
CONFIG_YAML = BASE / "config.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_buzz")

JST = timezone(timedelta(hours=9))
FULL_PROFILE = {"days": 30, "max_items": 100}
DEFAULT_RETENTION_DAYS = 30


def load_config() -> dict:
    with open(CONFIG_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_collection_settings(
    config: dict,
    profile: str,
    days_override: int | None = None,
    max_items_override: int | None = None,
    now: datetime | None = None,
) -> tuple[str, int, int, int]:
    collection = config.get("buzz_collection", {})
    profiles = collection.get("profiles", {})
    active_profile = collection.get("active_profile", "reduced")
    resolved_profile = active_profile if profile == "auto" else profile
    full_refresh_weekday = collection.get("full_refresh_weekday")
    now = now or datetime.now(JST)
    if (
        profile == "auto"
        and full_refresh_weekday
        and now.astimezone(JST).isoweekday() == int(full_refresh_weekday)
    ):
        resolved_profile = "full"
    settings = profiles.get(resolved_profile, FULL_PROFILE)
    days = days_override if days_override is not None else int(settings.get("days", FULL_PROFILE["days"]))
    max_items = clamp_max_items(
        max_items_override
        if max_items_override is not None
        else settings.get("max_items", FULL_PROFILE["max_items"]),
        "buzz_collection.max_items",
    )
    retention_days = int(collection.get("retention_days", DEFAULT_RETENTION_DAYS))
    return resolved_profile, days, max_items, retention_days


def fetch_accounts_batch(client, actor_id: str, handles: list[str], days: int = 30, max_items: int = 100) -> tuple[dict[str, list[dict]], float]:
    """指定アカウント群を1回のApify起動で取得する低レベル関数。"""
    since_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    search_terms = [f"from:{h} -filter:retweets min_faves:5" for h in handles]
    run_input = {
        "searchTerms": search_terms,
        "queryType": "Latest",
        "maxItems": max_items,
        "includeSearchTerms": True,
        "since": since_date,
    }
    logger.info("Fetching %d accounts in 1 batch (last %d days, max %d each) ...", len(handles), days, max_items)
    from utils import apify_actor_call, apify_run_get

    run = apify_actor_call(client.actor(actor_id), run_input=run_input, wait_seconds=300)
    cost = float(apify_run_get(run, "usageTotalUsd") or 0)
    status = apify_run_get(run, "status", "")
    if status != "SUCCEEDED":
        logger.error("Batch run status=%s", status)
        return {}, cost

    # アカウントごとに仕分け
    result: dict[str, list[dict]] = {h: [] for h in handles}
    total = 0
    for tweet in client.dataset(apify_run_get(run, "defaultDatasetId")).iterate_items():
        # author フィールドは構造が揺れるため複数パターンで取得
        author_obj = tweet.get("author") or {}
        author = (
            author_obj.get("userName")
            or author_obj.get("username")
            or tweet.get("userName")
            or tweet.get("username")
            or tweet.get("user", {}).get("screen_name")
            or tweet.get("authorName")
            or ""
        )
        # searchTerm から from:handle を抽出してフォールバック
        if not author:
            st = tweet.get("searchTerm") or tweet.get("searchTerms") or ""
            m = re.search(r"from:(\w+)", st)
            if m:
                author = m.group(1)
        author_lower = author.lower()
        for h in handles:
            if h.lower() == author_lower:
                result[h].append(tweet)
                break
        total += 1
    logger.info("Batch done: %d tweets total, cost=$%.4f", total, cost)
    for h in handles:
        logger.info("  @%s: %d tweets", h, len(result[h]))
    return result, cost


def fetch_account_tweets_with_cost(client, actor_id: str, handle: str, days: int = 30, max_items: int = 100) -> tuple[list[dict], float]:
    """単一アカウント取得（追加時などに使用）"""
    result, cost = fetch_accounts_batch(client, actor_id, [handle], days=days, max_items=max_items)
    return result.get(handle, []), cost


def fetch_account_tweets(client, actor_id: str, handle: str, days: int = 30, max_items: int = 100) -> list[dict]:
    tweets, _ = fetch_account_tweets_with_cost(client, actor_id, handle, days=days, max_items=max_items)
    return tweets


def fetch_accounts_individually(client, actor_id: str, handles: list[str], days: int = 30, max_items: int = 100) -> tuple[dict[str, list[dict]], float]:
    """1 run=1アカウントで取得する。

    xquik/x-tweet-scraper の maxItems は searchTerms 全体の合算上限として扱われる
    ビルドがあるため、複数アカウントを1 runに束ねると先頭アカウントが枠を食い潰す。
    """
    result: dict[str, list[dict]] = {}
    total_cost = 0.0
    for index, handle in enumerate(handles, start=1):
        logger.info("Fetching @%s (%d/%d) ...", handle, index, len(handles))
        tweets, cost = fetch_account_tweets_with_cost(
            client, actor_id, handle, days=days, max_items=max_items
        )
        result[handle] = tweets
        total_cost += cost
    logger.info("Individual account fetch done: %d accounts, cost=$%.4f", len(handles), total_cost)
    return result, total_cost


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
        "author_followers": (
            author.get("followers")
            or author.get("followersCount")
            or tweet.get("author_followers")
            or 0
        ),
        "eng_rate": None,  # フォロワー数があれば計算
    }


def _tweet_datetime(tweet: dict) -> datetime | None:
    raw = tweet.get("created_at") or tweet.get("createdAt") or ""
    if not raw:
        return None
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _tweet_key(tweet: dict) -> str:
    url = tweet.get("url") or tweet.get("tweetUrl")
    if url:
        return str(url)
    return f"{tweet.get('created_at', '')}|{tweet.get('text', '')}"


def _finalize_account_data(handle: str, display_name: str, normalized: list[dict]) -> dict:
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


def build_account_data(handle: str, display_name: str, tweets: list[dict]) -> dict:
    return _finalize_account_data(handle, display_name, [normalize_tweet(t) for t in tweets])


def merge_account_data(
    existing_account: dict | None,
    handle: str,
    display_name: str,
    fetched_tweets: list[dict],
    retention_days: int = DEFAULT_RETENTION_DAYS,
    retention_max_items: int = 100,
    now: datetime | None = None,
) -> tuple[dict, dict]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)
    existing_tweets = list((existing_account or {}).get("tweets", []))
    existing_by_key = {_tweet_key(t): t for t in existing_tweets}
    merged_by_key = dict(existing_by_key)

    normalized_fetched = [normalize_tweet(t) for t in fetched_tweets]
    for tweet in normalized_fetched:
        merged_by_key[_tweet_key(tweet)] = tweet

    retained: list[dict] = []
    expired = 0
    for tweet in merged_by_key.values():
        created_at = _tweet_datetime(tweet)
        if created_at is not None and created_at < cutoff:
            expired += 1
            continue
        retained.append(tweet)

    retained.sort(
        key=lambda tweet: _tweet_datetime(tweet) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    overflow = max(0, len(retained) - retention_max_items)
    retained = retained[:retention_max_items]
    merged_account = _finalize_account_data(handle, display_name, retained)
    merged_keys = {_tweet_key(t) for t in retained}
    prior_top = {
        _tweet_key(t)
        for t in sorted(existing_tweets, key=lambda x: x.get("likes", 0), reverse=True)[:20]
        if (_tweet_datetime(t) is None or _tweet_datetime(t) >= cutoff)
    }
    top_retained = len(prior_top & merged_keys)
    metrics = {
        "fetched": len(normalized_fetched),
        "new": len({_tweet_key(t) for t in normalized_fetched} - set(existing_by_key)),
        "retained": len(retained),
        "expired": expired,
        "overflow": overflow,
        "prior_top20_retention_pct": round(top_retained / len(prior_top) * 100, 1) if prior_top else 100.0,
    }
    return merged_account, metrics


def collection_gap_risk(existing_account: dict | None, fetched_tweets: list[dict], max_items: int) -> bool:
    if not existing_account or len(fetched_tweets) < max_items:
        return False
    previous_dates = [_tweet_datetime(t) for t in existing_account.get("tweets", [])]
    fetched_dates = [_tweet_datetime(normalize_tweet(t)) for t in fetched_tweets]
    previous_dates = [dt for dt in previous_dates if dt is not None]
    fetched_dates = [dt for dt in fetched_dates if dt is not None]
    if not previous_dates or not fetched_dates:
        return False
    # 取得した最古の投稿すら前回最新より新しい場合、上限の間に未取得投稿がある可能性が高い。
    return min(fetched_dates) > max(previous_dates)


def evaluate_guardrail_status(
    ranking_overlap_pct: float,
    min_ranking_overlap_pct: float,
    fallback_triggered: bool,
    starved_accounts: list[str] | None = None,
) -> str:
    """公開ランキングの実害指標(ranking_overlap)を主軸にガードレールを判定する。

    top20_retention は「日付順100件保持 × いいね順ランキング」という構造上、
    高いいねの古い投稿が保持枠から自然に押し出されるだけで1アカウント分が落ち、
    full運用でも誤って warning になる。そのためメトリクスとしては記録し続けるが
    warning 条件からは外し、ランキングが実際に崩れたか(overlap)のみで鳴らす。
    """
    if fallback_triggered:
        return "fallback"
    if starved_accounts:
        return "warning"
    return "pass" if ranking_overlap_pct >= min_ranking_overlap_pct else "warning"


def load_existing_buzz() -> dict:
    if BUZZ_JSON.exists():
        try:
            return json.loads(BUZZ_JSON.read_text(encoding="utf-8"))
        except Exception as e:
            raise RuntimeError(f"Failed to parse {BUZZ_JSON}: {e}") from e
    return {"updated_at": "", "accounts": []}


def save_buzz(data: dict) -> None:
    data["updated_at"] = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    BUZZ_JSON.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = BUZZ_JSON.with_suffix(f"{BUZZ_JSON.suffix}.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, BUZZ_JSON)
    logger.info("Saved → %s (%d accounts)", BUZZ_JSON, len(data["accounts"]))


def save_collection_metrics(metrics: dict) -> None:
    BUZZ_METRICS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with BUZZ_METRICS_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(metrics, ensure_ascii=False) + "\n")
    logger.info(
        "Buzz quality: fetched=%d new=%d retained=%d top20=%.1f%% guardrail=%s",
        metrics["fetched_items"],
        metrics["new_items"],
        metrics["retained_items"],
        metrics["prior_top20_retention_pct"],
        metrics["guardrail_status"],
    )


def overall_ranked_urls(accounts: list[dict], limit: int = 20) -> list[str]:
    ranked: list[dict] = []
    for account in accounts:
        median = account.get("median_likes") or 0
        if median <= 0:
            continue
        ranked.extend(
            tweet
            for tweet in account.get("tweets", [])
            if tweet.get("likes", 0) >= median * 2
        )
    ranked.sort(key=lambda tweet: tweet.get("likes", 0), reverse=True)
    return [_tweet_key(tweet) for tweet in ranked[:limit]]


def load_recent_zero_fetch_streaks(current_metrics: list[dict], threshold: int) -> tuple[dict[str, int], list[str]]:
    streaks = {
        item["account"]: 1
        for item in current_metrics
        if item.get("fetched", 0) == 0
    }
    if not streaks:
        return {}, []

    if threshold <= 1 or not BUZZ_METRICS_JSONL.exists():
        return streaks, sorted(streaks)

    lines = [
        line
        for line in BUZZ_METRICS_JSONL.read_text(encoding="utf-8").split("\n")
        if line.strip()
    ]
    for line in reversed(lines):
        try:
            metrics = json.loads(line)
        except json.JSONDecodeError:
            continue
        previous = {
            item.get("account"): item
            for item in metrics.get("account_metrics", [])
            if item.get("account")
        }
        if not previous:
            break
        for account in list(streaks):
            if previous.get(account, {}).get("fetched", 0) == 0:
                streaks[account] += 1
            else:
                del streaks[account]
        if not streaks:
            break
        if min(streaks.values()) >= threshold:
            break

    starved = sorted(account for account, count in streaks.items() if count >= threshold)
    return streaks, starved


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
    parser.add_argument("--profile", choices=["auto", "reduced", "full"], default="auto")
    parser.add_argument("--days", type=int, help="何日前まで遡るか（profile設定を上書き）")
    parser.add_argument("--max-items", type=int, help="アカウントあたりの最大取得件数（profile設定を上書き）")
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
    profile, days, max_items, retention_days = resolve_collection_settings(
        config, args.profile, args.days, args.max_items
    )
    collection_config = config.get("buzz_collection", {})
    retention_max_items = int(collection_config.get("retention_max_items", 100))
    min_ranking_overlap_pct = float(
        collection_config.get("min_weekly_top20_overlap_pct", 75.0)
    )
    zero_fetch_warning_streak = int(collection_config.get("zero_fetch_warning_streak", 2))
    logger.info(
        "Buzz collection profile=%s days=%d max_items=%d retention_days=%d",
        profile,
        days,
        max_items,
        retention_days,
    )

    existing = load_existing_buzz()
    previous_ranked_urls = overall_ranked_urls(existing.get("accounts", []))
    existing_map = {ac["account"]: ac for ac in existing.get("accounts", [])}
    apify_cost = 0.0
    account_metrics: list[dict] = []
    gap_risk_accounts: list[str] = []
    fallback_triggered = False

    if args.add:
        # 1アカウントだけ追加・更新してマージ
        handle = args.add.lstrip("@")
        display_name = get_display_name(handle, config)
        tweets, apify_cost = fetch_account_tweets_with_cost(
            client, actor_id, handle, days=days, max_items=max_items
        )
        # ツイートが0件でもアカウント自体は登録する
        merged, metrics = merge_account_data(
            existing_map.get(handle),
            handle,
            display_name,
            tweets,
            retention_days,
            retention_max_items,
        )
        existing_map[handle] = merged
        account_metrics.append({"account": handle, **metrics})
        _ensure_in_config(handle, display_name)
        existing["accounts"] = list(existing_map.values())

    elif args.accounts:
        # 指定アカウントのみ取得
        for handle in args.accounts:
            handle = handle.lstrip("@")
            display_name = get_display_name(handle, config)
            tweets, cost = fetch_account_tweets_with_cost(
                client, actor_id, handle, days=days, max_items=max_items
            )
            apify_cost += cost
            merged, metrics = merge_account_data(
                existing_map.get(handle),
                handle,
                display_name,
                tweets,
                retention_days,
                retention_max_items,
            )
            existing_map[handle] = merged
            account_metrics.append({"account": handle, **metrics})
        existing["accounts"] = list(existing_map.values())

    else:
        # config.yaml の buzz_accounts を全取得（1 run=1アカウント）
        buzz_accounts = config.get("buzz_accounts", [])
        if not buzz_accounts:
            logger.warning("buzz_accounts not configured in config.yaml")
            sys.exit(0)
        handles = [ac["handle"].lstrip("@") for ac in buzz_accounts]
        display_map = {ac["handle"].lstrip("@"): ac.get("display_name", ac["handle"]) for ac in buzz_accounts}
        batch_result, apify_cost = fetch_accounts_individually(
            client, actor_id, handles, days=days, max_items=max_items
        )
        if profile != "full":
            gap_risk_accounts = [
                handle
                for handle, tweets in batch_result.items()
                if collection_gap_risk(existing_map.get(handle), tweets, max_items)
            ]
        if gap_risk_accounts:
            logger.warning(
                "Buzz reduced collection may have gaps for %s; retrying full profile",
                ", ".join(f"@{handle}" for handle in gap_risk_accounts),
            )
            batch_result, fallback_cost = fetch_accounts_individually(
                client,
                actor_id,
                handles,
                days=FULL_PROFILE["days"],
                max_items=FULL_PROFILE["max_items"],
            )
            apify_cost += fallback_cost
            profile = "full"
            days = FULL_PROFILE["days"]
            max_items = FULL_PROFILE["max_items"]
            fallback_triggered = True
        for handle, tweets in batch_result.items():
            merged, metrics = merge_account_data(
                existing_map.get(handle),
                handle,
                display_map.get(handle, handle),
                tweets,
                retention_days,
                retention_max_items,
            )
            if tweets:
                existing_map[handle] = merged
            account_metrics.append({"account": handle, **metrics})
        existing["accounts"] = list(existing_map.values())

    save_buzz(existing)
    fetched_items = sum(item["fetched"] for item in account_metrics)
    retained_items = sum(item["retained"] for item in account_metrics)
    new_items = sum(item["new"] for item in account_metrics)
    min_top_retention = min(
        (item["prior_top20_retention_pct"] for item in account_metrics),
        default=100.0,
    )
    current_ranked_urls = overall_ranked_urls(existing.get("accounts", []))
    ranking_overlap_pct = 100.0
    if previous_ranked_urls:
        ranking_overlap_pct = round(
            len(set(previous_ranked_urls) & set(current_ranked_urls))
            / len(previous_ranked_urls)
            * 100,
            1,
        )
    zero_fetch_streaks, starved_accounts = load_recent_zero_fetch_streaks(
        account_metrics, zero_fetch_warning_streak
    )
    guardrail_status = evaluate_guardrail_status(
        ranking_overlap_pct,
        min_ranking_overlap_pct,
        fallback_triggered,
        starved_accounts,
    )
    save_collection_metrics({
        "checked_at": datetime.now(JST).isoformat(),
        "profile": profile,
        "days": days,
        "max_items": max_items,
        "retention_days": retention_days,
        "retention_max_items": retention_max_items,
        "accounts": len(account_metrics),
        "fetched_items": fetched_items,
        "new_items": new_items,
        "retained_items": retained_items,
        "prior_top20_retention_pct": min_top_retention,
        "ranking_top20_overlap_pct": ranking_overlap_pct,
        "min_weekly_top20_overlap_pct": min_ranking_overlap_pct,
        "gap_risk_accounts": gap_risk_accounts,
        "zero_fetch_warning_streak": zero_fetch_warning_streak,
        "zero_fetch_streaks": zero_fetch_streaks,
        "starved_accounts": starved_accounts,
        "account_metrics": account_metrics,
        "fallback_triggered": fallback_triggered,
        "guardrail_status": guardrail_status,
        "apify_cost_usd": round(apify_cost, 4),
    })

    # buzz.html を再生成
    try:
        import build_buzz
        build_buzz.build()
    except Exception as e:
        logger.warning("build_buzz failed: %s", e)

    # 実行ログ記録
    try:
        from utils import log_run, write_run_status
        accounts_count = len(existing.get("accounts", []))
        run_status = "warning" if guardrail_status == "warning" else "success"
        log_run("buzz", run_status,
                items_collected=fetched_items,
                apify_cost_usd=apify_cost,
                extra={
                    "accounts": accounts_count,
                    "items_retained": retained_items,
                    "new_items": new_items,
                    "profile": profile,
                    "guardrail_status": guardrail_status,
                    "fallback_triggered": fallback_triggered,
                    "starved_accounts": starved_accounts,
                })
        write_run_status("buzz", run_status,
                         clear_incident_on_success=(run_status == "success"),
                         extra={
                             "items_collected": fetched_items,
                             "items_retained": retained_items,
                             "new_items": new_items,
                             "accounts": accounts_count,
                             "profile": profile,
                             "guardrail_status": guardrail_status,
                             "fallback_triggered": fallback_triggered,
                             "starved_accounts": starved_accounts,
                         })
    except Exception as e:
        logger.warning("log_run failed: %s", e)


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

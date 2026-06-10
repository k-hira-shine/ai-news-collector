#!/usr/bin/env python3
"""過去にバズったGemini活用投稿を単発調査する。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.gemini_omni_media import media_from_apify_tweet
from utils import apify_run_get

logger = logging.getLogger("gemini-buzz-research")

DATA_DIR = ROOT / "data" / "gemini_buzz"
RAW_DIR = DATA_DIR / "raw"
RANKING_PATH = DATA_DIR / "ranking.json"
MANIFEST_PATH = DATA_DIR / "search_manifest.json"
ACTOR_ID = "xquik/x-tweet-scraper"

TEST_QUERIES = [
    "Gemini 使い方 lang:ja min_faves:100",
    "Gemini プロンプト lang:ja min_faves:100",
    "Gemini workflow lang:en min_faves:100",
    "Gemini tutorial lang:en min_faves:100",
]

USAGE_HINTS = re.compile(
    r"使い方|活用|プロンプト|手順|方法|やり方|作り方|効率化|"
    r"\bhow to\b|\btutorial\b|\bworkflow\b|\bprompt\b|\bguide\b|"
    r"\buse case\b|\bI use\b|\bsteps?\b",
    re.I,
)
NEWS_HINTS = re.compile(
    r"発表|リリース|公開され|アップデート|提供開始|速報|"
    r"\bannounc(?:e|ed|ement)\b|\breleas(?:e|ed)\b|\blaunch(?:ed)?\b|"
    r"\broll(?:ing)? out\b|\bnow available\b",
    re.I,
)
PROMO_HINTS = re.compile(
    r"無料配布|プレゼント|フォロー.*リプ|DMします|"
    r"comment ['\"]?\w+['\"]?|reply ['\"]?\w+['\"]?|"
    r"follow me|link in bio|limited offer",
    re.I,
)
OTHER_AI_HINTS = re.compile(
    r"(?<![A-Za-z0-9_])(?:ChatGPT|Claude)(?![A-Za-z0-9_])",
    re.I,
)
EXTERNAL_DETAIL_HINTS = re.compile(
    r"リプ欄|返信欄|続きはリプ|詳細はリプ|スレッド|"
    r"\bthread\b|\brepl(?:y|ies)\b|\bdetails below\b|\blink in bio\b",
    re.I,
)


def _parse_args() -> argparse.Namespace:
    today = date.today()
    parser = argparse.ArgumentParser(description="Gemini活用法の過去バズ投稿を単発調査")
    parser.add_argument("--start", default=(today - timedelta(days=365)).isoformat())
    parser.add_argument("--end", default=today.isoformat())
    parser.add_argument("--max-items-per-query", type=int, default=100)
    parser.add_argument("--max-charge-usd", type=Decimal, default=Decimal("0.08"))
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--refresh-costs-only", action="store_true")
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> None:
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if start >= end:
        raise SystemExit("--start must be before --end")
    if not 1 <= args.max_items_per_query <= 100:
        raise SystemExit("Test mode limits --max-items-per-query to 1..100")
    expected = len(TEST_QUERIES) * args.max_items_per_query * 0.00015
    if Decimal(str(expected)) > args.max_charge_usd:
        raise SystemExit(
            f"Expected result charge ${expected:.4f} exceeds cap ${args.max_charge_usd}"
        )


def _query_with_dates(query: str, start: str, end: str) -> str:
    # Xのuntilは終了日を含まないため、利用者が指定した終了日の翌日を渡す。
    until = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    return f"{query} since:{start} until:{until}"


def _normalize(tweet: dict) -> dict | None:
    url = tweet.get("url") or tweet.get("tweetUrl") or tweet.get("twitterUrl") or ""
    text = tweet.get("text") or tweet.get("fullText") or ""
    if not url or not text:
        return None
    author_obj = tweet.get("author") or {}
    author = (
        author_obj.get("userName")
        or author_obj.get("username")
        or tweet.get("username")
        or tweet.get("userName")
        or ""
    )
    media, video_mp4 = media_from_apify_tweet(tweet)
    likes = int(tweet.get("likeCount") or tweet.get("likes") or 0)
    retweets = int(tweet.get("retweetCount") or tweet.get("retweets") or 0)
    bookmarks = int(tweet.get("bookmarkCount") or tweet.get("bookmarks") or 0)
    quotes = int(tweet.get("quoteCount") or tweet.get("quotes") or 0)
    replies = int(tweet.get("replyCount") or tweet.get("replies") or 0)
    views = int(tweet.get("viewCount") or tweet.get("views") or 0)
    relevance = classify_relevance(text)
    return {
        "url": url,
        "author": author,
        "author_display": author_obj.get("name") or author,
        "author_followers": int(
            author_obj.get("followers") or author_obj.get("followersCount") or 0
        ),
        "text": text,
        "published_at": tweet.get("createdAt") or tweet.get("created_at") or "",
        "likes": likes,
        "retweets": retweets,
        "bookmarks": bookmarks,
        "quotes": quotes,
        "replies": replies,
        "views": views,
        "buzz_score": likes + retweets * 3 + bookmarks * 2 + quotes * 2,
        "search_term": tweet.get("searchTerm") or tweet.get("searchTerms") or "",
        "media": media,
        "video_mp4": video_mp4,
        **relevance,
    }


def classify_relevance(text: str) -> dict:
    """初回テスト用の保守的なルール判定。"""
    usage = bool(USAGE_HINTS.search(text))
    promo = bool(PROMO_HINTS.search(text))
    news = bool(NEWS_HINTS.search(text))
    accepted = usage and not promo
    if promo:
        reason = "promotion"
    elif usage:
        reason = "usage"
    elif news:
        reason = "news_only"
    else:
        reason = "unclear"
    return {
        "accepted": accepted,
        "filter_reason": reason,
        "needs_review": accepted and news,
        "mentions_other_ai": bool(OTHER_AI_HINTS.search(text)),
        "needs_external_detail": bool(EXTERNAL_DETAIL_HINTS.search(text)),
    }


def _dedupe(posts: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {}
    for post in posts:
        current = by_url.get(post["url"])
        if not current or post["likes"] > current["likes"]:
            by_url[post["url"]] = post
    return list(by_url.values())


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def save_results(
    posts: list[dict],
    *,
    args: argparse.Namespace,
    runs: list[dict],
    cost: float,
    queries: list[str],
) -> None:
    now = datetime.now(timezone.utc)
    snapshot_id = now.strftime("%Y%m%dT%H%M%SZ")
    raw_path = RAW_DIR / f"{snapshot_id}.json"
    deduped = _dedupe(posts)
    accepted = sorted(
        (post for post in deduped if post["accepted"]),
        key=lambda post: (post["likes"], post["retweets"], post["published_at"]),
        reverse=True,
    )
    snapshot = {
        "snapshot_id": snapshot_id,
        "fetched_at": now.isoformat(),
        "actor": ACTOR_ID,
        "run_ids": [run["run_id"] for run in runs],
        "runs": runs,
        "period": {"start": args.start, "end": args.end},
        "queries": queries,
        "max_items_per_query": args.max_items_per_query,
        "max_possible_results": len(queries) * args.max_items_per_query,
        "apify_cost_usd": round(cost, 4),
        "raw_count": len(posts),
        "deduplicated_count": len(deduped),
        "accepted_count": len(accepted),
        "posts": deduped,
    }
    _write_json(raw_path, snapshot)
    _write_json(
        RANKING_PATH,
        {
            "snapshot_id": snapshot_id,
            "fetched_at": now.isoformat(),
            "ranking_basis": "likes_desc",
            "engagement_is_snapshot": True,
            "count": len(accepted),
            "posts": accepted,
        },
    )
    _write_json(
        MANIFEST_PATH,
        {
            key: value for key, value in snapshot.items()
            if key not in ("posts",)
        } | {
            "raw_snapshot": str(raw_path.relative_to(ROOT)),
            "limitations": [
                "X Top search is relevance-ranked and not exhaustive.",
                "Engagement values are a snapshot at collection time.",
                "Rule-based relevance filtering requires manual review.",
            ],
        },
    )


def refresh_manifest_costs() -> None:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN missing")
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"Manifest missing: {MANIFEST_PATH}")
    from apify_client import ApifyClient

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    client = ApifyClient(token)
    total_cost = 0.0
    for run in manifest.get("runs", []):
        details = client.run(run["run_id"]).get() or {}
        run_cost = float(apify_run_get(details, "usageTotalUsd") or 0)
        run["apify_cost_usd"] = round(run_cost, 4)
        total_cost += run_cost
    manifest["apify_cost_usd"] = round(total_cost, 4)
    _write_json(MANIFEST_PATH, manifest)

    raw_path = ROOT / manifest["raw_snapshot"]
    snapshot = json.loads(raw_path.read_text(encoding="utf-8"))
    snapshot["runs"] = manifest.get("runs", [])
    snapshot["apify_cost_usd"] = manifest["apify_cost_usd"]
    _write_json(raw_path, snapshot)
    logger.info("Refreshed costs for %d runs: $%.4f", len(manifest.get("runs", [])), total_cost)


def run_research(args: argparse.Namespace) -> None:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN missing")
    from apify_client import ApifyClient

    queries = [_query_with_dates(query, args.start, args.end) for query in TEST_QUERIES]
    logger.info(
        "Starting one-off test: %d separate queries, max %d results, total charge cap $%s",
        len(queries),
        len(queries) * args.max_items_per_query,
        args.max_charge_usd,
    )
    actor = ApifyClient(token).actor(ACTOR_ID)
    client = ApifyClient(token)
    posts = []
    runs = []
    per_query_cap = args.max_charge_usd / len(queries)
    for query in queries:
        run = actor.call(
            run_input={
                "searchTerms": [query],
                "queryType": "Top",
                "maxItems": args.max_items_per_query,
                "includeSearchTerms": True,
            },
            max_items=args.max_items_per_query,
            max_total_charge_usd=per_query_cap,
            timeout_secs=600,
        )
        status = apify_run_get(run, "status", "")
        if status != "SUCCEEDED":
            raise SystemExit(f"Apify run failed for {query!r}: {status}")
        query_posts = []
        for tweet in client.dataset(
            apify_run_get(run, "defaultDatasetId")
        ).iterate_items():
            post = _normalize(tweet)
            if post:
                post["search_term"] = query
                query_posts.append(post)
        run_id = apify_run_get(run, "id", "")
        run_details = client.run(run_id).get() or run
        query_cost = float(apify_run_get(run_details, "usageTotalUsd") or 0)
        runs.append(
            {
                "query": query,
                "run_id": run_id,
                "raw_count": len(query_posts),
                "apify_cost_usd": round(query_cost, 4),
            }
        )
        posts.extend(query_posts)
        logger.info(
            "Query completed: %s, raw=%d, cost=$%.4f",
            query,
            len(query_posts),
            query_cost,
        )
    cost = sum(run["apify_cost_usd"] for run in runs)
    if Decimal(str(cost)) > args.max_charge_usd:
        raise SystemExit(
            f"Actual total charge ${cost:.4f} exceeds cap ${args.max_charge_usd}"
        )
    save_results(
        posts,
        args=args,
        runs=runs,
        cost=cost,
        queries=queries,
    )
    logger.info("Saved %d raw posts, cost=$%.4f", len(posts), cost)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args()
    _validate_args(args)
    if args.refresh_costs_only:
        refresh_manifest_costs()
    elif not args.build_only:
        run_research(args)
    from build_gemini_buzz import build
    build()


if __name__ == "__main__":
    main()

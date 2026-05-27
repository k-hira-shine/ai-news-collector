#!/usr/bin/env python3
"""Gemini Omni 海外・動画付き X 投稿を Apify で収集し JSON を更新する。"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.gemini_omni_media import media_from_apify_tweet
from utils import apify_actor_call, apify_run_get

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("collect_gemini_omni")

OMNI = re.compile(r"gemini\s+omni|geminiomni", re.I)
JP = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]")
OFFICIAL = {
    "google", "googleai", "googledeepmind", "geminiapp", "sundarpichai", "demishassabis",
    "flowbygoogle", "newsfromgoogle", "officiallogank", "youtube", "updatesfromyt",
}
NEWS_BOT = {"testingcatalog", "theaigrid", "ainews", "producthunt"}
HANDS = re.compile(
    r"\b(tried|tested|spent|using|used|made|created|generated|edited|putting|paces|"
    r"referenced|asked|I made|workflow|remix|built|shot|prompt)\b",
    re.I,
)
FIRST_PERSON = re.compile(r"\b(I|my|we|our)\b", re.I)

VIDEO_POSTS_PATH = ROOT / "data" / "gemini_omni_overseas_video_posts.json"
HANDS_ON_PATH = ROOT / "data" / "gemini_omni_overseas_hands_on_video.json"

SEARCH_QUERIES = [
    '"Gemini Omni" lang:en -filter:replies min_faves:5',
    '"Gemini Omni Flash" lang:en -filter:replies min_faves:5',
    'Gemini Omni (video OR generated OR created OR tested OR tried OR Flow) lang:en -filter:replies min_faves:5',
]


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _parse_tweet(tweet: dict) -> dict | None:
    text = tweet.get("text") or tweet.get("fullText") or ""
    author_obj = tweet.get("author") or {}
    author = (
        author_obj.get("userName")
        or author_obj.get("username")
        or tweet.get("username")
        or ""
    ).lower()
    if not OMNI.search(text):
        return None
    if JP.search(text) or author in OFFICIAL or author in NEWS_BOT:
        return None

    media, video_mp4 = media_from_apify_tweet(tweet)
    has_video = any(m.get("type") == "video" for m in media) or bool(video_mp4) or bool(
        re.search(r"https?://t\.co/\w+", text)
    )
    if not has_video:
        return None

    url = tweet.get("url") or tweet.get("tweetUrl") or tweet.get("twitterUrl") or ""
    if not url:
        return None

    hands_on = bool(HANDS.search(text))
    return {
        "url": url,
        "author": author,
        "likes": int(tweet.get("likeCount") or tweet.get("likes") or 0),
        "retweets": int(tweet.get("retweetCount") or tweet.get("retweets") or 0),
        "views": int(tweet.get("viewCount") or tweet.get("views") or 0),
        "published_at": tweet.get("createdAt") or "",
        "hands_on": hands_on,
        "text": text,
        "media": media,
        "video_mp4": video_mp4,
        "has_native_video": any(m.get("type") == "video" for m in media) or bool(video_mp4),
        "first_person": bool(FIRST_PERSON.search(text)),
    }


def _tier(post: dict) -> int:
    author = post.get("author") or ""
    text = post.get("text") or ""
    has_native = post.get("has_native_video")
    hands = post.get("hands_on")
    first = post.get("first_person")
    if author in OFFICIAL or author in NEWS_BOT:
        return 0
    if hands and has_native and first and post.get("likes", 0) >= 50:
        return 3
    if hands and has_native:
        return 2
    if has_native or hands:
        return 1
    if re.search(r"https?://t\.co/", text):
        return 1
    return 0


def _post_dt(post: dict) -> datetime:
    raw = post.get("published_at") or ""
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def fetch_apify(*, since_days: int = 7, max_items: int = 100) -> tuple[list[dict], float]:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN missing")

    from apify_client import ApifyClient

    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")
    run_input = {
        "searchTerms": SEARCH_QUERIES,
        "queryType": "Top",
        "maxItems": max_items,
        "includeSearchTerms": True,
        "since": since,
    }
    logger.info("Apify since=%s maxItems=%d queries=%d", since, max_items, len(SEARCH_QUERIES))

    client = ApifyClient(token)
    run = apify_actor_call(client.actor("xquik/x-tweet-scraper"), run_input=run_input, wait_seconds=600)
    status = apify_run_get(run, "status", "")
    cost = float(apify_run_get(run, "usageTotalUsd") or 0)
    logger.info("Apify status=%s cost=$%.4f", status, cost)
    if status != "SUCCEEDED":
        raise SystemExit(f"Apify run failed: {status}")

    posts: list[dict] = []
    for tweet in client.dataset(apify_run_get(run, "defaultDatasetId")).iterate_items():
        parsed = _parse_tweet(tweet)
        if parsed:
            posts.append(parsed)
    return posts, cost


def merge_posts(existing: list[dict], new_posts: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {p["url"]: p for p in existing if p.get("url")}
    for p in new_posts:
        url = p.get("url")
        if url:
            by_url[url] = p
    merged = list(by_url.values())
    merged.sort(key=lambda p: (_post_dt(p), p.get("likes") or 0), reverse=True)
    return merged


def curate_hands_on(posts: list[dict], *, max_age_days: int = 14) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    curated: list[dict] = []
    for p in posts:
        if _post_dt(p) < cutoff:
            continue
        tier = _tier(p)
        if tier < 1:
            continue
        row = dict(p)
        row["tier"] = tier
        curated.append(row)
    curated.sort(key=lambda p: (_post_dt(p), p.get("tier") or 0, p.get("likes") or 0), reverse=True)
    return curated


def main() -> None:
    _load_env()

    existing_video: list[dict] = []
    if VIDEO_POSTS_PATH.is_file():
        existing_video = json.loads(VIDEO_POSTS_PATH.read_text(encoding="utf-8")).get("posts") or []

    new_posts, cost = fetch_apify(since_days=7, max_items=100)
    logger.info("Apify parsed %d video+overseas posts", len(new_posts))

    merged = merge_posts(existing_video, new_posts)
    VIDEO_POSTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    VIDEO_POSTS_PATH.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "apify_cost_usd": cost,
                "count": len(merged),
                "posts": merged,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Wrote %d posts -> %s", len(merged), VIDEO_POSTS_PATH.name)

    curated = curate_hands_on(merged, max_age_days=14)
    HANDS_ON_PATH.write_text(
        json.dumps(
            {
                "curated_count": len(curated),
                "apify_cost_usd": cost,
                "posts": curated,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("Curated %d posts (last 14d, tier>=1) -> %s", len(curated), HANDS_ON_PATH.name)

    if curated:
        newest = _post_dt(curated[0]).date()
        oldest = _post_dt(curated[-1]).date()
        logger.info("Date range: %s .. %s", oldest, newest)


if __name__ == "__main__":
    main()

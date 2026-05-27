#!/usr/bin/env python3
"""既存 Gemini Omni JSON に video_mp4 を Apify tweetIds で補完する"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.gemini_omni_media import media_from_apify_tweet, tweet_id_from_url
from utils import apify_actor_call, apify_run_get

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_gemini_omni_videos")

VIDEO_POSTS = ROOT / "data" / "gemini_omni_overseas_video_posts.json"
HANDS_ON = ROOT / "data" / "gemini_omni_overseas_hands_on_video.json"
BATCH = 80


def _load_env() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _fetch_by_ids(client, tweet_ids: list[str]) -> dict[str, dict]:
    if not tweet_ids:
        return {}
    run = apify_actor_call(
        client.actor("xquik/x-tweet-scraper"),
        run_input={"tweetIds": tweet_ids},
        wait_seconds=300,
    )
    if apify_run_get(run, "status", "") != "SUCCEEDED":
        raise RuntimeError(f"Apify failed: {apify_run_get(run, 'status', '')}")
    cost = float(apify_run_get(run, "usageTotalUsd") or 0)
    logger.info("Fetched %d ids, cost=$%.4f", len(tweet_ids), cost)
    by_id: dict[str, dict] = {}
    for tweet in client.dataset(apify_run_get(run, "defaultDatasetId")).iterate_items():
        tid = str(tweet.get("id") or "")
        if tid:
            by_id[tid] = tweet
    return by_id


def _apply_mp4(posts: list[dict], by_id: dict[str, dict]) -> int:
    updated = 0
    for post in posts:
        tid = tweet_id_from_url(post.get("url") or "")
        raw = by_id.get(tid)
        if not raw:
            continue
        media, mp4 = media_from_apify_tweet(raw)
        if mp4:
            post["video_mp4"] = mp4
            post["media"] = media
            post["has_native_video"] = True
            updated += 1
    return updated


def main() -> None:
    _load_env()
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN missing")

    from apify_client import ApifyClient

    video_data = json.loads(VIDEO_POSTS.read_text(encoding="utf-8"))
    hands_data = json.loads(HANDS_ON.read_text(encoding="utf-8"))
    all_posts = video_data.get("posts") or []
    hands_posts = hands_data.get("posts") or []

    need_ids: list[str] = []
    for p in all_posts:
        if p.get("video_mp4"):
            continue
        tid = tweet_id_from_url(p.get("url") or "")
        if tid:
            need_ids.append(tid)
    need_ids = list(dict.fromkeys(need_ids))
    logger.info("Need mp4 for %d tweets", len(need_ids))

    client = ApifyClient(token)
    by_id: dict[str, dict] = {}
    for i in range(0, len(need_ids), BATCH):
        chunk = need_ids[i : i + BATCH]
        by_id.update(_fetch_by_ids(client, chunk))

    n1 = _apply_mp4(all_posts, by_id)
    url_to_post = {p["url"]: p for p in all_posts if p.get("url")}
    for p in hands_posts:
        src = url_to_post.get(p.get("url") or "")
        if src and src.get("video_mp4"):
            p["video_mp4"] = src["video_mp4"]
            p["media"] = src["media"]
            p["has_native_video"] = src.get("has_native_video", True)

    video_data["posts"] = all_posts
    hands_data["posts"] = hands_posts
    VIDEO_POSTS.write_text(json.dumps(video_data, ensure_ascii=False, indent=2), encoding="utf-8")
    HANDS_ON.write_text(json.dumps(hands_data, ensure_ascii=False, indent=2), encoding="utf-8")
    have = sum(1 for p in hands_posts if p.get("video_mp4"))
    logger.info("Updated %d posts; hands_on with mp4: %d / %d", n1, have, len(hands_posts))


if __name__ == "__main__":
    main()

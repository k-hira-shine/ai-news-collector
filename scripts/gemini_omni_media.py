"""Gemini Omni 投稿の動画 URL 抽出（Apify raw tweet 用）"""

from __future__ import annotations

import re

TWEET_ID_RE = re.compile(r"/status/(\d+)")


def tweet_id_from_url(url: str) -> str:
    m = TWEET_ID_RE.search(url or "")
    return m.group(1) if m else ""


def best_mp4_from_video_info(video_info: dict) -> str:
    variants = video_info.get("variants") or []
    mp4s = [
        v for v in variants
        if v.get("content_type") == "video/mp4" and v.get("url")
    ]
    if not mp4s:
        return ""
    mp4s.sort(key=lambda v: int(v.get("bitrate") or 0), reverse=True)
    return str(mp4s[0]["url"])


def media_from_apify_tweet(tweet: dict) -> tuple[list[dict], str]:
    """media リストと代表 mp4 URL を返す"""
    media: list[dict] = []
    video_mp4 = ""
    for m in tweet.get("media") or []:
        mtype = m.get("type", "photo")
        murl = m.get("url") or m.get("media_url_https") or m.get("previewUrl") or ""
        entry: dict = {"type": mtype, "url": murl}
        if mtype == "video":
            mp4 = best_mp4_from_video_info(m.get("video_info") or {})
            if mp4:
                entry["mp4"] = mp4
                if not video_mp4:
                    video_mp4 = mp4
        if murl or entry.get("mp4"):
            media.append(entry)
    return media, video_mp4

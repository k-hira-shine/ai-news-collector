"""Deterministic quality filters shared by Money and SNS analyses."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_URL_RE = re.compile(r"https?://\S+")
_SPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^\w\u3040-\u30ff\u3400-\u9fff]+")

_RIGHTS_VIOLATION_MARKERS = (
    "無断転載",
    "丸パクリ",
    "違法アップロード",
    "著作権侵害",
    "stolen content",
    "copyright infringement",
    "reupload without permission",
)

_RIGHTS_CRITICISM_MARKERS = (
    "批判",
    "問題",
    "違反",
    "禁止",
    "危険",
    "避け",
    "やめ",
    "ダメ",
    "許可を取",
    "対策",
    "吐き気",
    "しょうもない",
    "should not",
    "do not",
    "illegal",
    "against copyright",
)

_PROMOTION_MARKERS = (
    "無料勉強会",
    "無料セミナー",
    "無料相談",
    "特典を配布",
    "特典受け取り",
    "プレゼントします",
    "応募ください",
    "予約が埋まる",
    "公式line",
    "line登録",
    "dmください",
    "free course",
    "free webinar",
    "sign up now",
    "limited spots",
    "link in bio",
    "dm me",
)


def content_text(item: dict) -> str:
    return str(item.get("content") or item.get("title") or "")


def is_rights_violation_content(text: str) -> bool:
    lowered = unicodedata.normalize("NFKC", text).lower()
    if not any(marker in lowered for marker in _RIGHTS_VIOLATION_MARKERS):
        return False
    return not any(marker in lowered for marker in _RIGHTS_CRITICISM_MARKERS)


def is_promotional_content(text: str) -> bool:
    lowered = unicodedata.normalize("NFKC", text).lower()
    return any(marker in lowered for marker in _PROMOTION_MARKERS)


def prefilter_analysis_items(items: list[dict], min_followers: int) -> list[dict]:
    """Remove candidates that are cheap and reliable to reject before Gemini."""
    filtered = []
    for item in items:
        text = content_text(item).strip()
        followers = int(item.get("author_followers") or 0)
        if followers < min_followers:
            continue
        if not text or text.startswith("RT "):
            continue
        if text.startswith("@") and len(text) < 120:
            continue
        if is_rights_violation_content(text) or is_promotional_content(text):
            continue
        filtered.append(item)
    return filtered


def _normalized_similarity_text(item: dict) -> str:
    text = unicodedata.normalize("NFKC", content_text(item)).lower()
    text = _URL_RE.sub("", text)
    text = _SPACE_RE.sub("", text)
    return _NON_WORD_RE.sub("", text)


def filter_analysis_results(
    items: list[dict],
    *,
    similarity_threshold: float = 0.9,
    minimum_similarity_length: int = 50,
) -> list[dict]:
    """Reject unsafe/promotional results and collapse near-identical posts."""
    kept: list[dict] = []
    normalized_kept: list[str] = []

    for item in items:
        text = content_text(item)
        if is_rights_violation_content(text) or is_promotional_content(text):
            continue

        normalized = _normalized_similarity_text(item)
        is_duplicate = False
        if len(normalized) >= minimum_similarity_length:
            for previous in normalized_kept:
                if len(previous) < minimum_similarity_length:
                    continue
                length_ratio = min(len(normalized), len(previous)) / max(len(normalized), len(previous))
                if length_ratio < similarity_threshold:
                    continue
                if SequenceMatcher(None, normalized, previous).ratio() >= similarity_threshold:
                    is_duplicate = True
                    break
        if is_duplicate:
            continue

        kept.append(item)
        normalized_kept.append(normalized)

    return kept

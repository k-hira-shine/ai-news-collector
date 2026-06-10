#!/usr/bin/env python3
"""過去にバズったGemini新機能・活用投稿を単発調査する。"""

from __future__ import annotations

import argparse
import hashlib
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
REVIEWS_PATH = DATA_DIR / "discovery_reviews.json"
ACTOR_ID = "xquik/x-tweet-scraper"
DISCOVERY_REVIEW_MODEL = "gemini-2.5-flash-lite"
DISCOVERY_REVIEW_VERSION = 1

USAGE_QUERIES = [
    "Gemini 使い方 lang:ja min_faves:100",
    "Gemini プロンプト lang:ja min_faves:100",
    "Gemini workflow lang:en min_faves:100",
    "Gemini tutorial lang:en min_faves:100",
]
DISCOVERY_QUERIES = [
    "Gemini 新機能 lang:ja min_faves:100",
    "Gemini アップデート lang:ja min_faves:100",
    "Gemini すごい lang:ja min_faves:100",
    "Gemini new feature lang:en min_faves:100",
    "Gemini released lang:en min_faves:100",
    "Gemini insane lang:en min_faves:100",
]
FEATURE_QUERIES = [
    "Gemini Nano Banana lang:en min_faves:100",
    "Gemini Deep Think lang:en min_faves:100",
    "Gemini CLI lang:en min_faves:100",
    "Gemini Canvas lang:en min_faves:100",
    "Gemini Guided Learning lang:en min_faves:100",
    "Gemini Live lang:en min_faves:100",
    "Gemini image editing lang:en min_faves:100",
    "Gemini video generation lang:en min_faves:100",
    "Gemini 2.0 lang:en min_faves:100",
    "Gemini 3 lang:en min_faves:100",
]
FEATURE_EXPANSION_QUERIES = [
    "Gemini Flash Image lang:en min_faves:100",
    "Gemini Robotics lang:en min_faves:100",
    "Gemini Code Wiki lang:en min_faves:100",
    "Gemini TTS lang:en min_faves:100",
    "Gemini Gems lang:en min_faves:100",
    "Gemini extensions lang:en min_faves:100",
    "Gemini audio model lang:en min_faves:100",
    "Gemini agent mode lang:en min_faves:100",
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
    r"無料配布|プレゼント|フォロー.*リプ|いいねとリプ|DMします|"
    r"comment ['\"]?\w+['\"]?|reply ['\"]?\w+['\"]?|"
    r"follow me|link in bio|link in comment|limited offer",
    re.I,
)
OTHER_AI_HINTS = re.compile(
    r"(?<![A-Za-z0-9_])(?:ChatGPT|Claude)(?![A-Za-z0-9_])",
    re.I,
)
OTHER_PRODUCT_HINTS = re.compile(
    r"\bGemma\b|\bNotebookLM\b|\bPrompt Expanders?\b|"
    r"\bWorkspace Studio\b|\bDisco\b|\bGenTabs\b|\bStepFun\b|"
    r"\bFLORA\b|\bProject Genie\b",
    re.I,
)
EXTERNAL_DETAIL_HINTS = re.compile(
    r"リプ欄|返信欄|続きはリプ|詳細はリプ|スレッド|"
    r"\bthread\b|\brepl(?:y|ies)\b|\bdetails below\b|\blink in bio\b",
    re.I,
)
GEMINI_HINTS = re.compile(r"\bGemini\b|ジェミニ", re.I)
GEMINI_VERSION_HINTS = re.compile(
    r"\bGemini\s+(?:\d(?:\.\d)?|CLI|Deep Think|Live Translate|Code Wiki|"
    r"Robotics|Omni|Flash|Pro|Nano Banana)\b",
    re.I,
)
RELEASE_HINTS = re.compile(
    r"新機能|新しい|登場|発表|公開|提供開始|アップデート|刷新|ついに|"
    r"\bnew (?:feature|capabilit(?:y|ies)|model|tool|file search|session management)\b|"
    r"\bupdate[ds]?\b|\blaunch(?:ed|ing)?\b|\breleas(?:e|ed|ing)\b|"
    r"\bintroduc(?:e|ed|ing)\b|\benhanced\b|\breworked\b|\brolling out\b",
    re.I,
)
NEGATED_RELEASE_HINTS = re.compile(
    r"\bnot (?:an? )?(?:app |model |feature )?release\b",
    re.I,
)
EXCITEMENT_HINTS = re.compile(
    r"すごい|凄い|ヤバ|やば|衝撃|驚|神アプデ|異次元|待ち焦がれ|"
    r"信じられ|とんでもな|バケモン|世界が変わ|"
    r"\bcrazy\b|\binsane\b|\bwild\b|\bmind[- ]?blow(?:ing|n)?\b|"
    r"\bomg\b|\boh my\b|\bcan't believe\b|\bcannot believe\b|"
    r"\bblown away\b|\bgame[ -]?changer\b|\bthis is over\b|"
    r"\bkills?\b|\bno way\b|\bslept on\b|\brewired\b",
    re.I,
)
CAPABILITY_HINTS = re.compile(
    r"デモ|動画|画像|音声|3D|リアルタイム|ワークフロー|アプリ|サイト|"
    r"できるようにな|生成でき|作れる|構築でき|変換でき|自動化|"
    r"自動保存|再開でき|接続でき|操作でき|コード不要|コードは1行も|プロンプトだけ|"
    r"\bdemo\b|\bvideo\b|\bimage\b|\baudio\b|\b3d\b|\breal[- ]?time\b|"
    r"\bworkflow\b|\bapp\b|\bwebsite\b|\bno cod(?:e|ing)\b|"
    r"\bsingle prompt\b|\btext prompt\b|\bcan\b|"
    r"\bbuilds?\b|\bcreates?\b|\bgenerates?\b|\btransforms?\b|\bautomates?\b|"
    r"\bwrites?\b|\bfilms?\b|\bresearches?\b|\bdesigns?\b",
    re.I,
)
GENERIC_HYPE_HINTS = re.compile(
    r"9割|性能の(?:10|30|半分)%|神プロンプト|コピペOK|全部パクって|"
    r"使い方が.*間違|初期設定のまま|リプに置|"
    r"\bmost people\b|\bbookmark this\b|\bsteal the prompt\b",
    re.I,
)
SUBJECT_ACTION_HINTS = re.compile(
    r"(?:Gemini|ジェミニ)[^.!?\n。！？]{0,180}(?:新機能|新登場|登場|リリース|公開|"
    r"アップデート|できる|生成|作れる|構築|変換|自動化|"
    r"\bnew feature\b|\breleas(?:e|ed|ing)\b|\blaunch(?:ed|ing)?\b|"
    r"\bcan\b|\bbuilds?\b|\bcreates?\b|\bgenerates?\b|\btransforms?\b)|"
    r"(?:新機能|新登場|リリース|公開|発表)[^.!?\n。！？]{0,50}"
    r"(?:Gemini|ジェミニ)|"
    r"\b(?:introduc(?:e|ed|ing)|releas(?:e|ed|ing)|launch(?:ed|ing)?)"
    r"\s+(?:Google\s+)?Gemini\b",
    re.I | re.S,
)
DISCOVERY_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "is_gemini_feature": {"type": "boolean"},
                    "kind": {
                        "type": "string",
                        "enum": ["surprise", "new_feature", "reject"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["id", "is_gemini_feature", "kind", "reason"],
            },
        }
    },
    "required": ["items"],
}


def _parse_args() -> argparse.Namespace:
    today = date.today()
    parser = argparse.ArgumentParser(description="Geminiの過去バズ投稿を単発調査")
    parser.add_argument(
        "--mode",
        choices=("discovery", "usage"),
        default="discovery",
        help="discovery=新機能・驚き投稿、usage=使い方・チュートリアル",
    )
    parser.add_argument(
        "--query-profile",
        choices=("broad", "features", "feature-expansion"),
        default="broad",
        help="broad=一般語、features=主要機能、feature-expansion=追加機能",
    )
    parser.add_argument("--start", default=(today - timedelta(days=365)).isoformat())
    parser.add_argument("--end", default=today.isoformat())
    parser.add_argument("--max-items-per-query", type=int, default=25)
    parser.add_argument("--max-charge-usd", type=Decimal, default=Decimal("0.05"))
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--refresh-costs-only", action="store_true")
    parser.add_argument("--reclassify-only", action="store_true")
    parser.add_argument("--review-only", action="store_true")
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> None:
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if start >= end:
        raise SystemExit("--start must be before --end")
    if (
        args.build_only
        or args.refresh_costs_only
        or args.reclassify_only
        or args.review_only
    ):
        return
    if not 1 <= args.max_items_per_query <= 100:
        raise SystemExit("Test mode limits --max-items-per-query to 1..100")
    queries = _queries_for_mode(args.mode, args.query_profile)
    expected = len(queries) * args.max_items_per_query * 0.00015
    if Decimal(str(expected)) > args.max_charge_usd:
        raise SystemExit(
            f"Expected result charge ${expected:.4f} exceeds cap ${args.max_charge_usd}"
        )


def _queries_for_mode(mode: str, query_profile: str = "broad") -> list[str]:
    if mode == "usage":
        if query_profile != "broad":
            raise SystemExit("non-broad query profiles require discovery mode")
        return USAGE_QUERIES
    if query_profile == "features":
        return FEATURE_QUERIES
    if query_profile == "feature-expansion":
        return FEATURE_EXPANSION_QUERIES
    return DISCOVERY_QUERIES


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
        **classify_discovery(text),
    }


def classify_discovery(text: str) -> dict:
    """新機能や具体的な能力に驚いて紹介する投稿を判定する。"""
    matches = list(GEMINI_HINTS.finditer(text))
    other_product = OTHER_PRODUCT_HINTS.search(text)
    other_product_is_subject = bool(
        other_product and matches and other_product.start() < matches[0].start()
    )
    context = " ".join(
        text[max(0, match.start() - 180) : match.end() + 220]
        for match in matches
    )
    gemini = bool(matches)
    release = bool(RELEASE_HINTS.search(context))
    negated_release = bool(NEGATED_RELEASE_HINTS.search(context))
    excitement = bool(EXCITEMENT_HINTS.search(context))
    capability = bool(CAPABILITY_HINTS.search(context))
    generic_hype = bool(GENERIC_HYPE_HINTS.search(text))
    gemini_subject = bool(SUBJECT_ACTION_HINTS.search(text))
    versioned_demo = bool(GEMINI_VERSION_HINTS.search(text)) and excitement and capability
    score = int(release) * 2 + int(excitement) * 2 + int(capability)
    is_discovery = (
        gemini
        and capability
        and (release or excitement)
        and (gemini_subject or versioned_demo)
        and not other_product_is_subject
        and not negated_release
        and not (generic_hype and not release)
    )
    if not is_discovery:
        kind = ""
    elif excitement:
        kind = "surprise"
    else:
        kind = "new_feature"
    return {
        "is_discovery": is_discovery,
        "discovery_kind": kind,
        "discovery_score": score if is_discovery else 0,
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


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _load_discovery_reviews() -> dict[str, dict]:
    if not REVIEWS_PATH.exists():
        return {}
    try:
        data = json.loads(REVIEWS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if data.get("version") != DISCOVERY_REVIEW_VERSION:
        return {}
    return {
        key: value
        for key, value in (data.get("by_url") or {}).items()
        if isinstance(value, dict)
    }


def _apply_discovery_reviews(
    posts: list[dict],
    reviews: dict[str, dict],
) -> list[dict]:
    enriched = []
    for post in posts:
        copy = dict(post)
        review = reviews.get(copy.get("url") or "")
        if review and review.get("text_hash") == _text_hash(copy.get("text") or ""):
            approved = (
                bool(copy.get("is_discovery"))
                and bool(review.get("is_gemini_feature"))
                and review.get("kind") != "reject"
            )
            copy["is_discovery"] = approved
            copy["discovery_kind"] = review.get("kind") if approved else ""
            copy["discovery_score"] = copy.get("discovery_score", 0) if approved else 0
            copy["discovery_reviewed"] = True
            copy["discovery_review_reason"] = review.get("reason") or ""
        enriched.append(copy)
    return enriched


def review_discovery_posts(posts: list[dict]) -> list[dict]:
    """Gemini自身の新機能・具体デモかを低コストモデルで二次判定する。"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY missing: using rule-based discovery labels")
        return posts
    from google import genai

    reviews = _load_discovery_reviews()
    missing = [
        post
        for post in posts
        if post.get("is_discovery")
        and (
            not reviews.get(post.get("url") or "")
            or reviews[post.get("url") or ""].get("text_hash")
            != _text_hash(post.get("text") or "")
        )
    ]
    client = genai.Client(api_key=api_key)
    for start in range(0, len(missing), 25):
        batch = missing[start : start + 25]
        blocks = "\n\n".join(
            f"[ID: {post.get('url') or ''}]\n{post.get('text') or ''}"
            for post in batch
        )
        prompt = f"""以下のX投稿が「Google Gemini自身の新機能・新モデル・具体的な能力デモ」
を主題にした投稿か判定してください。

採用:
- Gemini本体、Geminiアプリ、Gemini API、Gemini CLI、Gemini Enterprise、
  Gemini Flash/Pro/Deep Think/Live Translate/Robotics/Omni等の新機能・新モデル
- Geminiが生成・構築・自動化した具体的なデモ
- 新機能やデモへの驚き・興奮を示す投稿

除外:
- Gemma、NotebookLM、Google Workspace、他社製品が主題でGeminiは比較・基盤として出るだけ
- 他AIとの一覧、一般的な使い方、神プロンプト配布
- 噂・今後の予想だけで、公開済み機能や実デモがない
- Geminiの能力を誤解させていると批判する投稿
- 文脈不足で具体的な機能が分からない投稿

kind:
- surprise: 驚きや興奮を伴う具体デモ
- new_feature: リリース・更新・新機能の説明
- reject: 除外対象

投稿:
{blocks}"""
        response = client.models.generate_content(
            model=DISCOVERY_REVIEW_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": DISCOVERY_REVIEW_SCHEMA,
                "thinking_config": {"thinking_budget": 0},
                "max_output_tokens": 6000,
            },
        )
        from gemini_usage import log_usage

        log_usage("gemini_buzz_discovery_review", DISCOVERY_REVIEW_MODEL, response)
        parsed = json.loads(response.text or "{}")
        post_by_url = {post.get("url") or "": post for post in batch}
        for row in parsed.get("items") or []:
            url = row.get("id") or ""
            post = post_by_url.get(url)
            if not post:
                continue
            reviews[url] = {
                "text_hash": _text_hash(post.get("text") or ""),
                "is_gemini_feature": bool(row.get("is_gemini_feature")),
                "kind": row.get("kind") or "reject",
                "reason": (row.get("reason") or "")[:300],
            }
        _write_json(
            REVIEWS_PATH,
            {
                "version": DISCOVERY_REVIEW_VERSION,
                "model": DISCOVERY_REVIEW_MODEL,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "by_url": reviews,
            },
        )
    return _apply_discovery_reviews(posts, reviews)


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
    current_accepted = _accepted_posts(deduped, args.mode)
    ranking_posts = current_accepted
    if args.mode == "discovery":
        previous = json.loads(RANKING_PATH.read_text(encoding="utf-8")) if RANKING_PATH.exists() else {}
        previous_discovery = [
            post for post in previous.get("posts", []) if post.get("is_discovery")
        ]
        ranking_posts = _accepted_posts(
            _dedupe(previous_discovery + current_accepted),
            args.mode,
        )
    ranking_posts = sorted(
        ranking_posts,
        key=lambda post: (post["likes"], post["retweets"], post["published_at"]),
        reverse=True,
    )
    snapshot = {
        "snapshot_id": snapshot_id,
        "fetched_at": now.isoformat(),
        "actor": ACTOR_ID,
        "search_mode": args.mode,
        "query_profile": args.query_profile,
        "run_ids": [run["run_id"] for run in runs],
        "runs": runs,
        "period": {"start": args.start, "end": args.end},
        "queries": queries,
        "max_items_per_query": args.max_items_per_query,
        "max_possible_results": len(queries) * args.max_items_per_query,
        "apify_cost_usd": round(cost, 4),
        "raw_count": len(posts),
        "deduplicated_count": len(deduped),
        "accepted_count": len(current_accepted),
        "accumulated_ranking_count": len(ranking_posts),
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
            "count": len(ranking_posts),
            "discovery_count": sum(
                bool(post.get("is_discovery")) for post in ranking_posts
            ),
            "search_mode": args.mode,
            "posts": ranking_posts,
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


def _accepted_posts(posts: list[dict], mode: str) -> list[dict]:
    if mode == "discovery":
        return [
            post
            for post in posts
            if post.get("is_discovery") and post.get("filter_reason") != "promotion"
        ]
    return [post for post in posts if post.get("accepted")]


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


def reclassify_snapshot() -> None:
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"Manifest missing: {MANIFEST_PATH}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    raw_path = ROOT / manifest["raw_snapshot"]
    snapshot = json.loads(raw_path.read_text(encoding="utf-8"))
    posts = snapshot.get("posts", [])
    for post in posts:
        post.update(classify_relevance(post.get("text") or ""))
    ranking = json.loads(RANKING_PATH.read_text(encoding="utf-8")) if RANKING_PATH.exists() else {}
    ranking_posts = ranking.get("posts", [])
    for post in ranking_posts:
        post.update(classify_relevance(post.get("text") or ""))
    accepted = sorted(
        _accepted_posts(_dedupe(ranking_posts + posts), "discovery"),
        key=lambda post: (post["likes"], post["retweets"], post["published_at"]),
        reverse=True,
    )
    snapshot["accepted_count"] = len(_accepted_posts(posts, "discovery"))
    snapshot["accumulated_ranking_count"] = len(accepted)
    _write_json(raw_path, snapshot)
    _write_json(
        RANKING_PATH,
        {
            "snapshot_id": snapshot["snapshot_id"],
            "fetched_at": snapshot["fetched_at"],
            "ranking_basis": "likes_desc",
            "engagement_is_snapshot": True,
            "count": len(accepted),
            "discovery_count": sum(bool(post["is_discovery"]) for post in accepted),
            "posts": accepted,
        },
    )
    logger.info(
        "Reclassified %d accepted posts: %d discovery posts",
        len(accepted),
        sum(bool(post["is_discovery"]) for post in accepted),
    )


def review_discovery_snapshot() -> None:
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"Manifest missing: {MANIFEST_PATH}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    raw_path = ROOT / manifest["raw_snapshot"]
    snapshot = json.loads(raw_path.read_text(encoding="utf-8"))
    ranking = json.loads(RANKING_PATH.read_text(encoding="utf-8"))
    combined = _dedupe((ranking.get("posts") or []) + (snapshot.get("posts") or []))
    for post in combined:
        post.update(classify_relevance(post.get("text") or ""))
    reviewed = review_discovery_posts(combined)
    accepted = sorted(
        _accepted_posts(reviewed, "discovery"),
        key=lambda post: (post["likes"], post["retweets"], post["published_at"]),
        reverse=True,
    )
    reviewed_by_url = {post["url"]: post for post in reviewed}
    snapshot["posts"] = [
        reviewed_by_url.get(post["url"], post) for post in snapshot.get("posts", [])
    ]
    snapshot["accepted_count"] = len(
        _accepted_posts(snapshot["posts"], "discovery")
    )
    snapshot["accumulated_ranking_count"] = len(accepted)
    manifest["accepted_count"] = snapshot["accepted_count"]
    manifest["accumulated_ranking_count"] = len(accepted)
    _write_json(raw_path, snapshot)
    _write_json(MANIFEST_PATH, manifest)
    _write_json(
        RANKING_PATH,
        {
            **{key: value for key, value in ranking.items() if key != "posts"},
            "count": len(accepted),
            "discovery_count": len(accepted),
            "posts": accepted,
        },
    )
    logger.info("AI-reviewed discovery ranking: %d posts", len(accepted))


def run_research(args: argparse.Namespace) -> None:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN missing")
    from apify_client import ApifyClient

    queries = [
        _query_with_dates(query, args.start, args.end)
        for query in _queries_for_mode(args.mode, args.query_profile)
    ]
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
                "accepted_count": len(_accepted_posts(query_posts, args.mode)),
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
    if args.mode == "discovery":
        posts = review_discovery_posts(posts)
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
    elif args.review_only:
        review_discovery_snapshot()
    elif args.reclassify_only:
        reclassify_snapshot()
    elif not args.build_only:
        run_research(args)
    from build_gemini_buzz import build
    build()


if __name__ == "__main__":
    main()

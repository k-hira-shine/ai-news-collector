"""X/Twitter・HackerNews・arxiv から AI ニュースを収集し、重複排除して JSONL に保存"""

import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from utils import apify_actor_call, apify_run_get, data_dir, hash_url, now_iso, parse_datetime, retry, today_str

logger = logging.getLogger("ai-news.collector")


# ━━━━━━━━━━━━━━━━ X/Twitter (Apify) ━━━━━━━━━━━━━━━━


def _get_apify_usage(token: str) -> dict | None:
    """Apify 月間使用量 API から通算コストを取得"""
    try:
        req = urllib.request.Request(
            "https://api.apify.com/v2/users/me/usage/monthly",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read()).get("data", {})
        return {
            "total": data.get("totalUsageCreditsUsdAfterVolumeDiscount", 0),
            "cycle_end": data.get("usageCycle", {}).get("endAt", ""),
        }
    except Exception as e:
        logger.warning("Apify usage API failed: %s", e)
        return None


def _default_x_runtime_meta() -> dict:
    return {
        "has_apify": False,
        "has_cookies": False,
        "apify_actor": "",
        "search_queries_configured": 0,
        "search_total": 0,
        "search_error_count": 0,
        "auth_error_count": 0,
        "must_follow_configured": 0,
        "must_follow_items": 0,
        "must_follow_error": False,
        "apify_cost_usd": 0.0,
        "apify_runs": 0,
        "invalid_items_stripped": 0,
        "apify_failure_hints": [],
        "search_failure_detail": "",
        "must_follow_failure_detail": "",
    }


_AUTH_ERROR_PATTERN = re.compile(
    r"(?i)("
    # Apify系Actorの認証/プロキシ失敗メッセージ
    r"Cookie health check[:\s]+FAILED|"
    r"Refresh the cookies|"
    r"Authenticated modes will fail|"
    r"ProxyAuthRequired|"
    r"proxy\s*auth\s*required|"
    # 一般的な認証エラー
    r"\blogin\s*required|\blogin\s*failed|"
    r"\bnot\s*logged\s*in|\bsession\s*expired|"
    r"\bunauthori[sz]ed|\bauthentication\s*(failed|required)|"
    r"\binvalid\s*(auth|token|cookie|session)|"
    r"\bauth_token\b|\bct0\s*(missing|invalid)|"
    r"\b403\s*forbidden|\b401\s*unauthori[sz]ed|"
    r"\bcookies?\s*(expired|invalid|missing)"
    r")"
)


def _fetch_apify_run_log(client, run_id: str) -> str:
    try:
        return client.run(run_id).log().get() or ""
    except Exception as e:
        logger.debug("Failed to fetch Apify run log %s: %s", run_id, e)
        return ""


def _inspect_apify_run_log(log_text: str) -> dict:
    """Apify Actor ログから障害の種類と要約を抽出（原因の記録用）"""
    hints: list[str] = []
    if "x_api_unavailable" in log_text:
        hints.append("x_api_unavailable")
    if "zero-output-run" in log_text:
        hints.append("zero-output-run")
    if "HTTP 502" in log_text or "Error 502" in log_text:
        hints.append("http_502")
    if "HTTP 503" in log_text and "x_api_unavailable" not in hints:
        hints.append("http_503")
    if _AUTH_ERROR_PATTERN.search(log_text):
        hints.append("auth_error")

    sample = ""
    for line in log_text.splitlines():
        if "retry-exhausted" in line or "fetch-error" in line or "zero-output-run" in line:
            sample = line.strip()[:280]
            break

    return {
        "hints": hints,
        "fetch_errors": log_text.count("fetch-error"),
        "sample_error": sample,
        "auth_error": "auth_error" in hints,
    }


def _merge_failure_hints(meta: dict, hints: list[str]) -> None:
    merged = list(meta.get("apify_failure_hints") or [])
    for h in hints:
        if h not in merged:
            merged.append(h)
    meta["apify_failure_hints"] = merged


def _format_failure_detail(inspection: dict, *, label: str) -> str:
    hints = inspection.get("hints") or []
    parts = [label]
    if hints:
        parts.append("検出: " + ", ".join(hints))
    if inspection.get("fetch_errors"):
        parts.append(f"fetch-error ×{inspection['fetch_errors']}")
    if inspection.get("sample_error"):
        parts.append("ログ抜粋: " + inspection["sample_error"])
    return " / ".join(parts)


def _note_zero_batch_failure(
    meta: dict,
    *,
    batch: str,
    configured: int,
    raw_count: int,
    inspection: dict,
) -> None:
    """SUCCEEDED だが 0 件のとき、原因を meta に残し search_error_count を立てる"""
    detail = _format_failure_detail(inspection, label=f"{batch} 0件")
    if batch == "search":
        meta["search_failure_detail"] = detail
        if raw_count == 0 and configured > 0:
            meta["search_error_count"] = max(meta.get("search_error_count", 0), configured)
    else:
        meta["must_follow_failure_detail"] = detail
        if raw_count == 0 and configured > 0:
            meta["must_follow_error"] = True
    _merge_failure_hints(meta, inspection.get("hints") or [])
    logger.warning("Apify %s: SUCCEEDED but %d items — %s", batch, raw_count, detail)


def _run_log_has_auth_error(client, run_id: str) -> bool:
    inspection = _inspect_apify_run_log(_fetch_apify_run_log(client, run_id))
    return inspection["auth_error"]


def _is_valid_tweet_item(item: dict) -> bool:
    url = (item.get("url") or "").strip()
    text = (item.get("content") or item.get("title") or "").strip()
    return url.startswith("http") and len(text) >= 5


def _should_warn_x_cookies(meta: dict) -> bool:
    """Warn only when there is concrete evidence that cookies are bad.

    Criteria:
      - Apify + cookies are configured and searches were attempted
      - At least one Apify run log contained auth-related errors
      - The must-follow timeline (which uses the same cookies) also returned
        zero items — if it succeeded, cookies are clearly still valid.
    """
    if not meta.get("has_apify") or not meta.get("has_cookies"):
        return False
    if meta.get("search_queries_configured", 0) <= 0:
        return False
    if meta.get("auth_error_count", 0) <= 0:
        return False
    if meta.get("must_follow_items", 0) > 0:
        return False
    return True


def _collect_x_twitter_with_meta(config: dict) -> tuple[list[dict], dict]:
    meta = _default_x_runtime_meta()
    items = collect_x_twitter(config, runtime_meta=meta)
    return items, meta


def _x_collection_settings(x_cfg: dict) -> tuple[int, int, list[dict]]:
    """通常便/夕方軽量便の上限と追跡アカウントを返す。"""
    must_follow = x_cfg.get("must_follow_accounts", [])
    max_query = int(x_cfg.get("max_results_per_query", 40))
    max_account = int(x_cfg.get("max_results_per_account", 10))
    if x_cfg.get("runtime_mode") != "light":
        return max_query, max_account, must_follow

    light = x_cfg.get("light_mode", {})
    selected = {str(handle).lower() for handle in light.get("must_follow_handles", [])}
    accounts = [
        account for account in must_follow
        if account.get("handle", "").lower() in selected
    ]
    return (
        int(light.get("max_results_per_query", 75)),
        int(light.get("max_results_per_account", 10)),
        accounts,
    )


def collect_x_twitter(config: dict, runtime_meta: dict | None = None) -> list[dict]:
    """Apify 経由で X/Twitter を収集 (検索 + 必須アカウント)"""
    meta = runtime_meta if runtime_meta is not None else _default_x_runtime_meta()
    token = os.environ.get("APIFY_TOKEN")
    meta["has_apify"] = bool(token)
    meta["has_cookies"] = False
    if not token:
        logger.warning("APIFY_TOKEN not set — skipping X/Twitter")
        return []

    try:
        from apify_client import ApifyClient
    except ImportError:
        logger.warning("apify-client not installed — skipping X/Twitter")
        return []

    client = ApifyClient(token)
    x_cfg = config.get("x_twitter", {})
    actor_id = x_cfg.get("apify_actor", "xquik/x-tweet-scraper")
    meta["apify_actor"] = actor_id
    search_queries = x_cfg.get("search_queries", [])
    max_results_per_query, max_results_per_account, must_follow = _x_collection_settings(x_cfg)
    meta["search_queries_configured"] = len(search_queries)
    items: list[dict] = []

    max_age_days = config.get("collection", {}).get("max_age_days", 2)
    since_date = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime("%Y-%m-%d")

    if search_queries:
        # クエリごとに 1 actor run で呼ぶ（searchTerms は常に1語）。
        # 以前は searchTerms 配列で全クエリを1 runにまとめ、maxItems を
        # 「検索語ごとの上限」として扱っていた（2026-05-11 比較テストで確認）。
        # だが 2026-06-21 の xquik/x-tweet-scraper 新ビルドで maxItems が
        # 「全searchTerms合算の上限」に変わり、先頭クエリが枠を食い潰して
        # 収集が約9割減した（x_valid 206→39, 2026-06-21〜22）。1 run=1クエリなら
        # 合算＝クエリ毎に戻り、actor の maxItems 解釈変更に依存しなくなる。
        # 課金は結果従量制（$0.00015/件）のため、総取得数が同じならコストは不変。
        total_count = 0
        auth_error_seen = False
        all_hints: list[str] = []
        for query in search_queries:
            try:
                run_input = {
                    "searchTerms": [query],
                    "queryType": "Top",
                    "maxItems": max_results_per_query,
                    "includeSearchTerms": True,
                    "since": since_date,
                }

                run = apify_actor_call(client.actor(actor_id), run_input=run_input, wait_seconds=300)
                meta["apify_runs"] += 1
                meta["apify_cost_usd"] += float(apify_run_get(run, "usageTotalUsd") or 0)
                run_status = apify_run_get(run, "status", "")
                run_id = apify_run_get(run, "id", "")
                if run_status and run_status != "SUCCEEDED":
                    meta["search_error_count"] += 1
                    logger.error("X search query run status=%s: %.60s", run_status, query)
                    if run_id and _run_log_has_auth_error(client, run_id):
                        auth_error_seen = True
                    continue
                count = 0
                for tweet in client.dataset(apify_run_get(run, "defaultDatasetId")).iterate_items():
                    item = _normalize_tweet(tweet)
                    if _is_valid_tweet_item(item):
                        items.append(item)
                        count += 1
                total_count += count
                logger.info("X search query (%.60s): %d tweets", query, count)
                # 0件のときだけ run ログを点検（健全時の無駄な7回fetchを避ける）
                if count == 0 and run_id:
                    inspection = _inspect_apify_run_log(_fetch_apify_run_log(client, run_id))
                    all_hints.extend(inspection.get("hints") or [])
                    if inspection.get("auth_error"):
                        auth_error_seen = True
            except Exception as e:
                meta["search_error_count"] += 1
                logger.error("X search query failed (%.60s): %s", query, e)
        meta["search_total"] += total_count
        _merge_failure_hints(meta, all_hints)
        logger.info("X search (%d queries): %d tweets total", len(search_queries), total_count)
        # 全クエリ合算で 0 件 & 原因ヒントありなら従来どおり search_failure を記録
        if total_count == 0 and all_hints:
            _note_zero_batch_failure(
                meta,
                batch="search",
                configured=len(search_queries),
                raw_count=0,
                inspection={"hints": all_hints, "auth_error": auth_error_seen},
            )
        # auth エラーを1つでも検出したら cookie 失敗として扱う
        if auth_error_seen:
            meta["auth_error_count"] += 1
            meta["search_error_count"] = max(meta.get("search_error_count", 0), 1)
            logger.warning("X search: auth error detected — treating as cookie failure")
    else:
        logger.info("X search queries not configured — skipping search queries")

    meta["must_follow_configured"] = len(must_follow)
    if must_follow:
        # アカウントも 1アカウント=1 actor run で呼ぶ（searchTerms は常に1語）。
        # 検索クエリと同じく、2026-06-21 の xquik/x-tweet-scraper 新ビルドで maxItems が
        # 「全searchTerms合算の上限」に変わり、全アカウントを1 runにまとめていた旧実装では
        # maxItems を全アカウントで食い合い、後半アカウントが budget=0 で飢餓して
        # must_follow が約1件/アカウントに激減した（2026-06-23 発覚＝検索側のみ修正していた）。
        # 1 run=1アカウントなら maxItems がアカウント毎に効き、actor の解釈変更に依存しない。
        # 課金は結果従量制（$0.00015/件）のため、総取得数が同じならコストは不変。
        priority_map = {acct["handle"].lower(): acct for acct in must_follow}
        mf_count = 0
        auth_error_seen = False
        all_hints: list[str] = []
        for acct in must_follow:
            handle = acct["handle"]
            query = f"from:{handle} -filter:replies"
            try:
                run_input = {
                    "searchTerms": [query],
                    "queryType": "Latest",
                    "maxItems": max_results_per_account,
                    "includeSearchTerms": True,
                    "since": since_date,
                }

                run = apify_actor_call(client.actor(actor_id), run_input=run_input, wait_seconds=300)
                meta["apify_runs"] += 1
                meta["apify_cost_usd"] += float(apify_run_get(run, "usageTotalUsd") or 0)
                run_status = apify_run_get(run, "status", "")
                run_id = apify_run_get(run, "id", "")
                if run_status and run_status != "SUCCEEDED":
                    meta["must_follow_error"] = True
                    logger.error("X must-follow run status=%s: %s", run_status, handle)
                    if run_id and _run_log_has_auth_error(client, run_id):
                        auth_error_seen = True
                    continue
                acct_count = 0
                for tweet in client.dataset(apify_run_get(run, "defaultDatasetId")).iterate_items():
                    item = _normalize_tweet(tweet)
                    if not _is_valid_tweet_item(item):
                        continue
                    author_lower = item["author"].lower()
                    acct_cfg = priority_map.get(author_lower, {})
                    item["is_must_follow"] = True
                    item["is_official"] = acct_cfg.get("priority") == "critical"
                    item["priority"] = acct_cfg.get("priority", "normal")
                    items.append(item)
                    mf_count += 1
                    acct_count += 1
                logger.info("X must-follow (%s): %d tweets", handle, acct_count)
                # 0件のときだけ run ログを点検（健全時の無駄なfetchを避ける）
                if acct_count == 0 and run_id:
                    inspection = _inspect_apify_run_log(_fetch_apify_run_log(client, run_id))
                    all_hints.extend(inspection.get("hints") or [])
                    if inspection.get("auth_error"):
                        auth_error_seen = True
            except Exception as e:
                meta["must_follow_error"] = True
                logger.error("X must-follow failed (%s): %s", handle, e)
        meta["must_follow_items"] = mf_count
        _merge_failure_hints(meta, all_hints)
        logger.info("X must-follow (%d profiles): %d tweets total", len(must_follow), mf_count)
        # 全アカウント合算で 0 件 & 原因ヒントありなら従来どおり失敗を記録
        if mf_count == 0 and all_hints:
            _note_zero_batch_failure(
                meta,
                batch="must-follow",
                configured=len(must_follow),
                raw_count=0,
                inspection={"hints": all_hints, "auth_error": auth_error_seen},
            )
        # auth エラーを1つでも検出したら cookie 失敗として扱う
        if auth_error_seen:
            meta["auth_error_count"] += 1
            meta["must_follow_error"] = True
            logger.warning("X must-follow: auth error detected — treating as cookie failure")

    before_valid = len(items)
    items = [it for it in items if _is_valid_tweet_item(it)]
    stripped = before_valid - len(items)
    if stripped:
        meta["invalid_items_stripped"] = meta.get("invalid_items_stripped", 0) + stripped
        logger.warning("Stripped %d invalid/empty tweet records from Apify dataset", stripped)

    min_eng = x_cfg.get("min_engagement", 0)
    if min_eng > 0:
        before = len(items)
        items = [
            it for it in items
            if it.get("is_must_follow")
            or (it["engagement"].get("likes", 0) + it["engagement"].get("retweets", 0)) >= min_eng
        ]
        logger.info("X engagement filter (>=%d): %d → %d", min_eng, before, len(items))

    meta["x_valid_count"] = len(items)
    if meta.get("search_total", 0) == 0 and meta.get("search_queries_configured", 0) > 0:
        if not meta.get("search_failure_detail") and meta.get("apify_failure_hints"):
            meta["search_failure_detail"] = (
                "search 0件 / 検出: " + ", ".join(meta["apify_failure_hints"])
            )
            meta["search_error_count"] = max(
                meta.get("search_error_count", 0),
                meta["search_queries_configured"],
            )

    if meta["apify_runs"] > 0:
        usage_now = _get_apify_usage(token)
        if usage_now is not None:
            meta["apify_cycle_total_usd"] = usage_now["total"]
            meta["apify_cycle_end"] = usage_now.get("cycle_end", "")

    logger.info("X/Twitter total: %d items (Apify: %d runs, $%.4f)", len(items), meta["apify_runs"], meta["apify_cost_usd"])
    return items


def _normalize_tweet(tweet: dict) -> dict:
    url = tweet.get("url") or tweet.get("tweetUrl") or tweet.get("twitterUrl") or ""
    author_obj = tweet.get("author") or {}
    username = (
        author_obj.get("userName")
        or author_obj.get("username")
        or tweet.get("username")
        or tweet.get("userName")
        or tweet.get("authorUsername")
        or "unknown"
    )
    text = tweet.get("text") or tweet.get("fullText") or ""
    return {
        "id": hash_url(url),
        "source": "x",
        "url": url,
        "title": text[:200],
        "content": text,
        "author": username,
        "published_at": tweet.get("createdAt") or "",
        "collected_at": now_iso(),
        "engagement": {
            "likes": tweet.get("likeCount") or tweet.get("likes") or 0,
            "retweets": tweet.get("retweetCount") or tweet.get("retweets") or 0,
            "replies": tweet.get("replyCount") or tweet.get("replies") or 0,
            "views": tweet.get("viewCount") or tweet.get("views") or 0,
            "bookmarks": tweet.get("bookmarkCount") or tweet.get("bookmarks") or 0,
            "quotes": tweet.get("quoteCount") or tweet.get("quotes") or 0,
        },
        "source_name": f"@{username}",
        "priority": "normal",
        "is_official": False,
        "is_must_follow": False,
    }


# ━━━━━━━━━━━━━━━━ HackerNews (Algolia API) ━━━━━━━━━━━━━━━━


def collect_hackernews(config: dict) -> list[dict]:
    """Algolia HN Search API で直近 AI 関連記事を収集（認証不要・無料）"""
    hn_cfg = config.get("hackernews", {})
    if not hn_cfg.get("enabled", False):
        return []

    max_age_hours = hn_cfg.get("max_age_hours", 48)
    min_score = hn_cfg.get("min_score", 10)
    max_items = hn_cfg.get("max_items", 30)
    # AI関連キーワードでPython側フィルタ用
    keywords = [kw.lower() for kw in hn_cfg.get(
        "filter_keywords",
        ["ai", "llm", "chatgpt", "claude", "gemini", "openai", "anthropic",
         "gpt", "deepmind", "mistral", "llama", "machine learning", "neural"]
    )]

    since_ts = int((datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).timestamp())
    # search_by_date で日付順取得、クエリなしで全件取得してPython側でフィルタ
    url = (
        "https://hn.algolia.com/api/v1/search_by_date"
        "?tags=story"
        f"&numericFilters=created_at_i%3E{since_ts}"
        "&hitsPerPage=200"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ai-news-collector/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        logger.warning("HackerNews API failed: %s", e)
        return []

    items: list[dict] = []
    for hit in data.get("hits", []):
        title = hit.get("title", "")
        points = hit.get("points") or 0

        # スコア足切り
        if points < min_score:
            continue
        # AI関連キーワードフィルタ
        title_lower = title.lower()
        if not any(kw in title_lower for kw in keywords):
            continue

        hn_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
        hn_id = hash_url(hn_url)
        comments = hit.get("num_comments") or 0
        author = hit.get("author", "")
        created_at = hit.get("created_at", "")
        hn_item_url = f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"

        items.append({
            "id": hn_id,
            "source": "hn",
            "url": hn_url,
            "hn_item_url": hn_item_url,
            "title": title,
            "content": title,
            "author": author,
            "published_at": created_at,
            "collected_at": now_iso(),
            "engagement": {
                "likes": points,
                "retweets": 0,
                "replies": comments,
                "views": 0,
                "bookmarks": 0,
                "quotes": 0,
            },
            "source_name": "HackerNews",
            "priority": "normal",
            "is_official": False,
            "is_must_follow": False,
        })
        if len(items) >= max_items:
            break

    logger.info("HackerNews: %d items (min_score=%d, last %dh)", len(items), min_score, max_age_hours)

    if items:
        _translate_hn_items(items)

    return items


# ━━━━━━━━━━━━━━━━ arxiv API ━━━━━━━━━━━━━━━━


def collect_arxiv(config: dict) -> list[dict]:
    """arxiv Atom API で cs.AI/cs.LG/cs.CL の新着論文を収集（認証不要・無料）"""
    arxiv_cfg = config.get("arxiv", {})
    if not arxiv_cfg.get("enabled", False):
        return []

    categories = arxiv_cfg.get("categories", ["cs.AI", "cs.LG", "cs.CL"])
    max_results = arxiv_cfg.get("max_results_per_category", 10)
    max_age_days = arxiv_cfg.get("max_age_days", 2)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    items: list[dict] = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for i, cat in enumerate(categories):
        if i > 0:
            time.sleep(3)  # arxiv のリクエスト制限を尊重
        url = (
            "http://export.arxiv.org/api/query"
            f"?search_query=cat:{cat}"
            f"&sortBy=submittedDate&sortOrder=descending"
            f"&max_results={max_results}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ai-news-collector/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                root = ET.fromstring(resp.read())
        except Exception as e:
            logger.warning("arxiv API failed for %s: %s", cat, e)
            continue

        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            published_el = entry.find("atom:published", ns)
            link_el = entry.find("atom:link[@rel='alternate']", ns)
            if link_el is None:
                link_el = entry.find("atom:link", ns)
            authors = [
                a.find("atom:name", ns).text
                for a in entry.findall("atom:author", ns)
                if a.find("atom:name", ns) is not None
            ]

            title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
            summary = (summary_el.text or "").strip().replace("\n", " ")[:300] if summary_el is not None else ""
            published_at = published_el.text or "" if published_el is not None else ""
            paper_url = (link_el.get("href") or "") if link_el is not None else ""

            # 期間フィルタ
            pub_dt = parse_datetime(published_at)
            if pub_dt and pub_dt < cutoff:
                continue

            arxiv_id = hash_url(paper_url)
            items.append({
                "id": arxiv_id,
                "source": "arxiv",
                "url": paper_url,
                "title": title,
                "content": f"{title}\n{summary}",
                "author": ", ".join(authors[:3]),
                "published_at": published_at,
                "collected_at": now_iso(),
                "arxiv_category": cat,
                "arxiv_summary": summary,
                "engagement": {
                    "likes": 0,
                    "retweets": 0,
                    "replies": 0,
                    "views": 0,
                    "bookmarks": 0,
                    "quotes": 0,
                },
                "source_name": f"arxiv:{cat}",
                "priority": "normal",
                "is_official": False,
                "is_must_follow": False,
            })

        logger.info("arxiv %s: %d papers (last %dd)", cat, len([x for x in items if x.get("arxiv_category") == cat]), max_age_days)

    logger.info("arxiv total: %d papers", len(items))

    # Gemini で タイトル・要旨を日本語訳（APIキーがある場合のみ）
    if items:
        _translate_arxiv_items(items)

    return items


def _translate_hn_items(items: list[dict]) -> None:
    """低コスト翻訳モデルでHNタイトルをまとめて日本語訳（in-place）"""
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        return
    try:
        from google import genai
        client = genai.Client(api_key=gemini_key)
    except Exception as e:
        logger.warning("Gemini import failed — skipping HN translation: %s", e)
        return

    lines = [f"[{i}] {item.get('title', '')}" for i, item in enumerate(items)]
    prompt = (
        "以下のHackerNewsの英語記事タイトルを日本語に翻訳してください。\n"
        "各タイトルを [番号] 翻訳タイトル の形式で返してください。\n"
        "番号・形式は必ず元と一致させてください。余計な説明は不要です。\n\n"
        + "\n".join(lines)
    )

    try:
        from translation_config import get_translation_model

        model_name = get_translation_model()
        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={"thinking_config": {"thinking_budget": 0}, "max_output_tokens": 4096},
        )
        from gemini_usage import log_usage
        log_usage("hn_translate", model_name, resp)
        text = resp.text or ""
        import re as _re
        pattern = _re.compile(r'\[(\d+)\]\s*(.+)')
        for m in pattern.finditer(text):
            idx = int(m.group(1))
            if 0 <= idx < len(items):
                items[idx]["title_ja"] = m.group(2).strip()
        translated = sum(1 for it in items if it.get("title_ja"))
        logger.info("HN translation: %d/%d items translated", translated, len(items))
    except Exception as e:
        logger.warning("HN translation failed: %s", e)


def _translate_arxiv_items(items: list[dict]) -> None:
    """低コスト翻訳モデルでタイトル・要旨をまとめて日本語訳（in-place）"""
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        return
    try:
        from google import genai
        client = genai.Client(api_key=gemini_key)
    except Exception as e:
        logger.warning("Gemini import failed — skipping arxiv translation: %s", e)
        return

    # タイトル+要旨をまとめて1リクエストで翻訳
    lines = []
    for i, item in enumerate(items):
        title = item.get("title", "")
        summary = item.get("arxiv_summary", "")
        lines.append(f"[{i}] TITLE: {title}\nSUMMARY: {summary}")

    prompt = (
        "以下の英語論文リストのタイトルと要旨を日本語に翻訳してください。\n"
        "各論文を [番号] TITLE: 翻訳タイトル\\nSUMMARY: 翻訳要旨 の形式で返してください。\n"
        "番号・形式は必ず元と一致させてください。余計な説明は不要です。\n\n"
        + "\n\n".join(lines)
    )

    try:
        from translation_config import get_translation_model

        model_name = get_translation_model()
        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={"thinking_config": {"thinking_budget": 0}, "max_output_tokens": 16384},
        )
        from gemini_usage import log_usage
        log_usage("arxiv_translate", model_name, resp)
        text = resp.text or ""
        # パース: [番号] TITLE: ... SUMMARY: ... を抽出
        import re as _re
        pattern = _re.compile(
            r'\[(\d+)\]\s*TITLE:\s*(.+?)\s*\n\s*SUMMARY:\s*(.+?)(?=\n\[|\Z)',
            _re.DOTALL,
        )
        for m in pattern.finditer(text):
            idx = int(m.group(1))
            if 0 <= idx < len(items):
                items[idx]["title_ja"] = m.group(2).strip()
                items[idx]["arxiv_summary_ja"] = m.group(3).strip()
        translated = sum(1 for it in items if it.get("title_ja"))
        logger.info("arxiv translation: %d/%d items translated", translated, len(items))
    except Exception as e:
        logger.warning("arxiv translation failed: %s", e)


# ━━━━━━━━━━━━━━━━ 著作権・法規制・訴訟 RSS ━━━━━━━━━━━━━━━━


def collect_legal_rss(config: dict, health: dict | None = None) -> list[dict]:
    """legal_news.rss_feeds から AI 著作権・法規制・訴訟ニュースを収集し、
    X 分析パイプライン互換（source="rss"）のアイテムとして返す。
    dedup・保存は collect_all 側で行う。フィード障害は警告のみで他に影響させない。

    health（任意・out引数）に feed 単位の健全性を入れる:
      legal_feeds_total  … url を持つ設定フィード数
      legal_feeds_ok     … 生entries>0（到達かつ中身あり）のフィード数
      legal_feeds_failed … HTTP>=400 / bozo例外 / parse例外のフィード数
    feedparser は 404/タイムアウト/空でも例外を投げないため、これで
    「窓に新着なしの0件」と「取得失敗の0件」を区別できるようにする。
    """
    legal_cfg = config.get("legal_news", {})
    if not legal_cfg.get("enabled", False):
        return []

    try:
        import feedparser
    except ImportError:
        logger.error("feedparser not installed — skipping legal RSS")
        return []

    feeds_total = feeds_ok = feeds_failed = 0

    feeds = legal_cfg.get("rss_feeds", [])
    max_per_feed = legal_cfg.get("max_items_per_feed", 20)
    max_age_days = legal_cfg.get("max_age_days", 5)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    collected_at = now_iso()

    items: list[dict] = []
    for feed_cfg in feeds:
        url = feed_cfg.get("url", "")
        label = feed_cfg.get("label", url)
        limit = int(feed_cfg.get("max_items", max_per_feed))
        if not url:
            continue
        feeds_total += 1
        try:
            feed = feedparser.parse(url)
            raw = len(feed.entries)
            status = getattr(feed, "status", None)
            bozo = getattr(feed, "bozo", 0)
            if (status is not None and status >= 400) or (bozo and raw == 0):
                feeds_failed += 1
                logger.warning(
                    "Legal RSS unhealthy [%s]: status=%s bozo=%s raw=0", label, status, bozo
                )
            elif raw > 0:
                feeds_ok += 1
            # raw==0 で error でもない＝到達したが中身なし（曖昧なので ok にも failed にも数えない）
            count = 0
            for entry in feed.entries[:limit]:
                link = entry.get("link", "")
                if not link:
                    continue

                pub = entry.get("published_parsed") or entry.get("updated_parsed")
                pub_dt: datetime | None = None
                if pub:
                    try:
                        pub_dt = datetime.fromtimestamp(time.mktime(pub), tz=timezone.utc)
                    except Exception:
                        pass
                if pub_dt and pub_dt < cutoff:
                    continue

                content = ""
                if entry.get("content"):
                    content = entry.content[0].get("value", "")
                elif entry.get("summary"):
                    content = entry.summary
                content = re.sub(r"<[^>]+>", " ", content).strip()
                content = re.sub(r"\s+", " ", content)[:2000]

                title = entry.get("title", "").strip()
                items.append({
                    "id": hash_url(link),
                    "source": "rss",
                    "url": link,
                    "title": title[:200],
                    "content": content,
                    "author": entry.get("author", ""),
                    "published_at": pub_dt.isoformat() if pub_dt else "",
                    "collected_at": collected_at,
                    "source_name": label,
                    "source_label": label,
                    "priority": "normal",
                    "is_official": False,
                    "is_must_follow": False,
                    "legal_news": True,
                })
                count += 1
            logger.info("Legal RSS [%s]: %d items", label, count)
        except Exception as e:
            feeds_failed += 1
            logger.warning("Legal RSS fetch failed [%s]: %s", label, e)

    if health is not None:
        health["legal_feeds_total"] = feeds_total
        health["legal_feeds_ok"] = feeds_ok
        health["legal_feeds_failed"] = feeds_failed
    logger.info(
        "Legal RSS total: %d items (last %dd) — feeds ok=%d failed=%d / %d",
        len(items), max_age_days, feeds_ok, feeds_failed, feeds_total,
    )
    return items


# ━━━━━━━━━━━━━━━━ HN/arxiv 専用保存 ━━━━━━━━━━━━━━━━


def save_hn_jsonl(items: list[dict]) -> str:
    """data/hn/YYYY-MM-DD.jsonl に保存（既存エントリは翻訳済みデータで上書き）"""
    hn_dir = data_dir("hn")
    os.makedirs(hn_dir, exist_ok=True)
    path = os.path.join(hn_dir, f"{today_str()}.jsonl")
    # 既存エントリをIDをキーに読み込み、新データで上書きマージ
    existing: dict[str, dict] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        existing[entry["id"]] = entry
                    except Exception:
                        pass
    for item in items:
        existing[item["id"]] = item
    with open(path, "w", encoding="utf-8") as f:
        for item in existing.values():
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info("Saved %d hn/arxiv items → %s", len(existing), path)
    return path


# ━━━━━━━━━━━━━━━━ 重複排除 & 永続化 ━━━━━━━━━━━━━━━━


class SeenURLsCache:
    def __init__(self, retention_days: int = 7):
        self.path = data_dir("cache", "seen_urls.json")
        self.retention_days = retention_days
        self.cache = self._load()

    def _load(self) -> dict[str, str]:
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).strftime(
            "%Y-%m-%d"
        )
        return {k: v for k, v in data.items() if v >= cutoff}

    def is_seen(self, url_hash: str) -> bool:
        return url_hash in self.cache

    def mark_seen(self, url_hash: str) -> None:
        self.cache[url_hash] = today_str()

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.cache, f)
        os.replace(tmp, self.path)


def deduplicate(items: list[dict], cache: SeenURLsCache) -> list[dict]:
    unique: list[dict] = []
    seen_in_batch: set[str] = set()

    for item in items:
        uid = item["id"]
        if uid in seen_in_batch or cache.is_seen(uid):
            continue
        seen_in_batch.add(uid)
        cache.mark_seen(uid)
        unique.append(item)

    logger.info("Dedup: %d → %d items (%d removed)", len(items), len(unique), len(items) - len(unique))
    return unique


def _filter_old_items(items: list[dict], max_age_days: int = 7) -> list[dict]:
    """published_at が max_age_days 以上前のアイテムを除外する"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    before = len(items)
    filtered = []
    for item in items:
        pub = parse_datetime(item.get("published_at", ""))
        if pub is None or pub >= cutoff:
            filtered.append(item)
    removed = before - len(filtered)
    if removed:
        logger.info("Age filter (>%dd): %d → %d (%d removed)", max_age_days, before, len(filtered), removed)
    return filtered


def save_daily_jsonl(items: list[dict]) -> str:
    path = data_dir("daily", f"{today_str()}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info("Saved %d items → %s", len(items), path)
    return path


# ━━━━━━━━━━━━━━━━ JSONL 読み込み ━━━━━━━━━━━━━━━━


def _load_latest_daily() -> list[dict]:
    """直近の daily JSONL を読み込んで返す (--analyze-only 用)"""
    daily_dir = data_dir("daily")
    if not os.path.isdir(daily_dir):
        return []
    files = sorted(
        [f for f in os.listdir(daily_dir) if f.endswith(".jsonl")], reverse=True
    )
    if not files:
        return []
    path = os.path.join(daily_dir, files[0])
    items: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    logger.info("Loaded %d items from %s", len(items), path)
    return items


# ━━━━━━━━━━━━━━━━ オーケストレータ ━━━━━━━━━━━━━━━━


def collect_all(config: dict) -> tuple[list[dict], dict]:
    """X/Twitter から収集し、重複排除して保存。HN/arxiv は data/hn/ に別途保存"""
    cache = SeenURLsCache(
        retention_days=config.get("cache", {}).get("seen_urls_retention_days", 7)
    )

    items: list[dict] = []
    x_meta = _default_x_runtime_meta()
    try:
        items, x_meta = _collect_x_twitter_with_meta(config)
    except Exception as e:
        logger.error("X/Twitter collection completely failed: %s", e)
        x_meta["fatal_error"] = str(e)[:200]

    items = deduplicate(items, cache)
    items = _filter_old_items(items, max_age_days=config.get("collection", {}).get("max_age_days", 7))

    # 著作権・法規制・訴訟 RSS を X 分析パイプラインに合流（stage1 が AI 無関係を除外）。
    # legal は collect_legal_rss 内で独自の age 窓で絞るため、X 用の 2日フィルタは通さない。
    try:
        legal_health: dict = {}
        legal_items = collect_legal_rss(config, health=legal_health)
        legal_items = deduplicate(legal_items, cache)
        if legal_items:
            items = items + legal_items
        x_meta["legal_rss_count"] = len(legal_items)
        x_meta.update(legal_health)
    except Exception as e:
        logger.error("Legal RSS collection failed: %s", e)
        x_meta["legal_rss_count"] = 0

    save_daily_jsonl(items)
    cache.save()

    # HN・arxiv は独立して data/hn/ に保存（X分析パイプラインには混ぜない）
    hn_items: list[dict] = []
    try:
        hn_items += collect_hackernews(config)
        hn_items += collect_arxiv(config)
        if hn_items:
            save_hn_jsonl(hn_items)
    except Exception as e:
        logger.error("HN/arxiv collection failed: %s", e)

    return items, x_meta

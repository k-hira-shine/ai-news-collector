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

from utils import data_dir, hash_url, now_iso, parse_datetime, retry, today_str

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


def _run_log_has_auth_error(client, run_id: str) -> bool:
    """Fetch Apify run log and check for auth-related failure keywords.

    Returns False on any fetch error (conservative: don't falsely warn).
    """
    try:
        log_text = client.run(run_id).log().get()
    except Exception as e:
        logger.debug("Failed to fetch Apify run log %s: %s", run_id, e)
        return False
    if not log_text:
        return False
    return bool(_AUTH_ERROR_PATTERN.search(log_text))


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
    meta["search_queries_configured"] = len(search_queries)
    items: list[dict] = []

    max_age_days = config.get("collection", {}).get("max_age_days", 2)
    since_date = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime("%Y-%m-%d")

    if search_queries:
        # xquik は searchTerms 配列で複数検索を1 runにまとめられる。
        # maxItems は検索語ごとの上限として適用される（2026-05-11 比較テストで確認）。
        try:
            run_input = {
                "searchTerms": list(search_queries),
                "queryType": "Top",
                "maxItems": x_cfg.get("max_results_per_query", 40),
                "includeSearchTerms": True,
                "since": since_date,
            }

            run = client.actor(actor_id).call(run_input=run_input, timeout_secs=300)
            meta["apify_runs"] += 1
            meta["apify_cost_usd"] += float((run or {}).get("usageTotalUsd") or 0)
            run_status = (run or {}).get("status", "")
            run_id = (run or {}).get("id", "")
            if run_status and run_status != "SUCCEEDED":
                # バッチ内のクエリは全部失敗扱い
                meta["search_error_count"] += len(search_queries)
                logger.error("X search batch (%d queries) run status=%s", len(search_queries), run_status)
                if run_id and _run_log_has_auth_error(client, run_id):
                    meta["auth_error_count"] += 1
                    logger.warning("X search batch: auth error detected in run log")
            else:
                count = 0
                for tweet in client.dataset(run["defaultDatasetId"]).iterate_items():
                    items.append(_normalize_tweet(tweet))
                    count += 1
                meta["search_total"] += count
                logger.info("X search batch (%d queries): %d tweets", len(search_queries), count)
                # SUCCEEDED でも結果が極端に少なく auth エラーがある場合は実質失敗扱い
                few_results = count < len(search_queries)
                if (count == 0 or few_results) and run_id and _run_log_has_auth_error(client, run_id):
                    meta["auth_error_count"] += 1
                    meta["search_error_count"] += len(search_queries)
                    logger.warning(
                        "X search batch: SUCCEEDED but %d results with auth error in log"
                        " — treating as cookie failure",
                        count,
                    )
        except Exception as e:
            meta["search_error_count"] += len(search_queries)
            logger.error("X search batch failed: %s", e)
    else:
        logger.info("X search queries not configured — skipping search queries")

    must_follow = x_cfg.get("must_follow_accounts", [])
    meta["must_follow_configured"] = len(must_follow)
    if must_follow:
        try:
            handles = [acct["handle"] for acct in must_follow]
            priority_map = {acct["handle"].lower(): acct for acct in must_follow}
            account_queries = [f"from:{handle} -filter:replies" for handle in handles]
            run_input: dict = {
                "searchTerms": account_queries,
                "queryType": "Latest",
                "maxItems": x_cfg.get("max_results_per_account", 10),
                "includeSearchTerms": True,
                "since": since_date,
            }

            run = client.actor(actor_id).call(run_input=run_input, timeout_secs=300)
            meta["apify_runs"] += 1
            meta["apify_cost_usd"] += float((run or {}).get("usageTotalUsd") or 0)
            run_status = (run or {}).get("status", "")
            run_id = (run or {}).get("id", "")
            if run_status and run_status != "SUCCEEDED":
                meta["must_follow_error"] = True
                logger.error("X must-follow batch run status=%s", run_status)
                if run_id and _run_log_has_auth_error(client, run_id):
                    meta["auth_error_count"] += 1
                    logger.warning("X must-follow: auth error detected in run log")
            else:
                mf_count = 0
                for tweet in client.dataset(run["defaultDatasetId"]).iterate_items():
                    item = _normalize_tweet(tweet)
                    author_lower = item["author"].lower()
                    acct_cfg = priority_map.get(author_lower, {})
                    item["is_must_follow"] = True
                    item["is_official"] = acct_cfg.get("priority") == "critical"
                    item["priority"] = acct_cfg.get("priority", "normal")
                    items.append(item)
                    mf_count += 1
                meta["must_follow_items"] = mf_count
                logger.info("X must-follow batch (%d profiles): %d tweets", len(handles), mf_count)
                # SUCCEEDED でも結果が少なく auth エラーがある場合は must_follow_error を立てる
                few_results = mf_count < len(handles)
                if (mf_count == 0 or few_results) and run_id and _run_log_has_auth_error(client, run_id):
                    meta["auth_error_count"] += 1
                    meta["must_follow_error"] = True
                    logger.warning(
                        "X must-follow: SUCCEEDED but %d results with auth error in log"
                        " — treating as cookie failure",
                        mf_count,
                    )
        except Exception as e:
            meta["must_follow_error"] = True
            logger.error("X must-follow batch failed: %s", e)

    min_eng = x_cfg.get("min_engagement", 0)
    if min_eng > 0:
        before = len(items)
        items = [
            it for it in items
            if it.get("is_must_follow")
            or (it["engagement"].get("likes", 0) + it["engagement"].get("retweets", 0)) >= min_eng
        ]
        logger.info("X engagement filter (>=%d): %d → %d", min_eng, before, len(items))

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


def _translate_arxiv_items(items: list[dict]) -> None:
    """Gemini Flash でタイトル・要旨をまとめて日本語訳（in-place）"""
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
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
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


# ━━━━━━━━━━━━━━━━ HN/arxiv 専用保存 ━━━━━━━━━━━━━━━━


def save_hn_jsonl(items: list[dict]) -> str:
    """data/hn/YYYY-MM-DD.jsonl に追記保存"""
    hn_dir = data_dir("hn")
    os.makedirs(hn_dir, exist_ok=True)
    path = os.path.join(hn_dir, f"{today_str()}.jsonl")
    # source ごとに既存エントリの重複を避けるため既存IDを読み込む
    existing_ids: set[str] = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        existing_ids.add(json.loads(line)["id"])
                    except Exception:
                        pass
    new_items = [it for it in items if it["id"] not in existing_ids]
    with open(path, "a", encoding="utf-8") as f:
        for item in new_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    logger.info("Saved %d hn/arxiv items → %s", len(new_items), path)
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

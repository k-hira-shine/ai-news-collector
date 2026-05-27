"""Gemini Omni 概要 + 海外実使用ポスト — docs/gemini-omni.html 生成"""

import json
import logging
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from glob import glob
from html import escape, unescape
from zoneinfo import ZoneInfo

from site_nav import NAV_CSS, render_nav

logger = logging.getLogger("ai-news.build_gemini_omni")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "gemini_omni_overseas_hands_on_video.json")
TRANSLATIONS_PATH = os.path.join(BASE_DIR, "data", "gemini_omni_post_translations.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "docs", "gemini-omni.html")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
JST = ZoneInfo("Asia/Tokyo")
TRANSLATE_MODEL = "gemini-2.5-flash"
TRANSLATE_BATCH = 8

TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text_ja": {"type": "string"},
                },
                "required": ["id", "text_ja"],
            },
        }
    },
    "required": ["items"],
}

PROMO_HINTS = (
    'Comment "OMNI"',
    "Like this post",
    "must be following so I can DM",
    "Want access for free",
)

TIER_LABELS = {
    3: ("注目", "#10b981"),
    2: ("実使用", "#38bdf8"),
    1: ("参考", "#94a3b8"),
}


def _parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(JST)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(JST)
    except Exception:
        return None


def _fmt_date(raw: str) -> str:
    dt = _parse_date(raw)
    if dt:
        return dt.strftime("%Y/%m/%d")
    return raw[:10] if raw else ""


def _is_promo(post: dict) -> bool:
    text = post.get("text") or ""
    if any(h in text for h in PROMO_HINTS):
        return True
    author = (post.get("author") or "").lower()
    return author in ("muvi_ai", "muviai")


def _load_env_file() -> None:
    path = os.path.join(BASE_DIR, ".env")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def _load_translation_cache() -> dict[str, str]:
    if not os.path.isfile(TRANSLATIONS_PATH):
        return {}
    try:
        with open(TRANSLATIONS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in (data.get("by_url") or {}).items() if isinstance(v, str)}
    except Exception as e:
        logger.warning("Failed to load translations cache: %s", e)
        return {}


def _save_translation_cache(cache: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(TRANSLATIONS_PATH), exist_ok=True)
    with open(TRANSLATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump({"by_url": cache, "updated_at": datetime.now(JST).isoformat()}, f, ensure_ascii=False, indent=2)


def _translate_batch(client, posts: list[dict]) -> dict[str, str]:
    from google.genai import types

    blocks = []
    for p in posts:
        url = p.get("url") or ""
        raw = unescape(re.sub(r"\s+", " ", (p.get("text") or "").strip()))
        blocks.append(f'[ID: {url}]\n{raw[:3500]}\n---')
    prompt = f"""以下は X（Twitter）投稿の英語本文です。各 ID ごとに自然な日本語へ翻訳してください。

## ルール
- text_ja: 投稿全文を日本語化（要約せず、意味を落とさない）
- @ユーザー名・URL・製品名（Gemini Omni, Seedance 等）はそのままかカタカナ表記でよい
- 絵文字・改行のニュアンスはできるだけ維持
- リード獲得（Comment "OMNI" 等）も含めて正直に訳す

## 投稿
{chr(10).join(blocks)}"""

    response = client.models.generate_content(
        model=TRANSLATE_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": TRANSLATE_SCHEMA,
            "thinking_config": {"thinking_budget": 0},
            "http_options": types.HttpOptions(timeout=120_000),
        },
    )
    text = response.text
    if not text:
        raise ValueError("Empty translation response")
    parsed = json.loads(text)
    out: dict[str, str] = {}
    for item in parsed.get("items") or []:
        pid = item.get("id") or ""
        ja = (item.get("text_ja") or "").strip()
        if pid and ja:
            out[pid] = ja
    return out


def ensure_post_translations(posts: list[dict]) -> list[dict]:
    """投稿に text_ja を付与（キャッシュ + 未訳のみ API）"""
    _load_env_file()
    cache = _load_translation_cache()
    missing = [p for p in posts if (p.get("url") or "") not in cache]
    api_key = os.environ.get("GEMINI_API_KEY")

    if missing and api_key:
        try:
            from google import genai
        except ImportError:
            logger.warning("google-genai not installed — skipping translation")
        else:
            client = genai.Client(api_key=api_key)
            for i in range(0, len(missing), TRANSLATE_BATCH):
                batch = missing[i : i + TRANSLATE_BATCH]
                logger.info("Translating posts %d–%d / %d…", i + 1, i + len(batch), len(missing))
                try:
                    cache.update(_translate_batch(client, batch))
                    _save_translation_cache(cache)
                except Exception as e:
                    logger.error("Translation batch failed: %s", e)
                    break
    elif missing:
        logger.warning("GEMINI_API_KEY not set — %d posts without Japanese", len(missing))

    enriched: list[dict] = []
    for p in posts:
        copy = dict(p)
        url = copy.get("url") or ""
        copy["text_ja"] = cache.get(url) or ""
        enriched.append(copy)
    return enriched


def _display_text(post: dict) -> str:
    ja = (post.get("text_ja") or "").strip()
    if ja:
        return ja
    return _clean_text(post.get("text") or "", limit=800)


def _clean_text(text: str, limit: int = 800) -> str:
    t = unescape(re.sub(r"\s+", " ", text or "").strip())
    if len(t) > limit:
        t = t[: limit - 1] + "…"
    return t


def _thumb_url(post: dict) -> str:
    for m in post.get("media") or []:
        url = m.get("url") or ""
        if url.startswith("http"):
            return url
    return ""


def _sort_posts(posts: list[dict]) -> list[dict]:
    return sorted(
        posts,
        key=lambda p: (p.get("tier") or 0, p.get("likes") or 0),
        reverse=True,
    )


def _load_posts() -> tuple[list[dict], dict]:
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    posts = _sort_posts(data.get("posts") or [])
    return posts, data


def _overview_html() -> str:
    return """
<section class="overview" id="overview">
  <h2>Gemini Omni とは</h2>
  <p class="lead">
    Google I/O 2026（2026年5月）で発表された、マルチモーダル動画生成・編集の新ファミリー。
    コミュニティでは「動画版 Nano Banana」とも呼ばれ、まずは<strong>動画</strong>が入口になっている。
  </p>
  <div class="overview-grid">
    <article class="ov-card">
      <h3>位置づけ</h3>
      <ul>
        <li>「Anything from anything」の第一歩（現時点は動画中心）</li>
        <li>他社の動画 AI と違い、<strong>映像のネイティブ編集</strong>もマルチモーダルで扱える点が差別化</li>
        <li>モデル名: <strong>Gemini Omni</strong>（ファミリー）／実運用は <strong>Gemini Omni Flash</strong> が入口</li>
      </ul>
    </article>
    <article class="ov-card">
      <h3>どこで使えるか</h3>
      <ul>
        <li>Gemini アプリ（有料プラン）</li>
        <li>Google Flow（Agent モードでの一括生成）</li>
        <li>YouTube Shorts 等への展開言及</li>
        <li>API は「近日」告知が多く、開発者向けはまだ待ちの声が多い</li>
      </ul>
    </article>
    <article class="ov-card">
      <h3>よく言われる制約</h3>
      <ul>
        <li>レート制限・<strong>約10秒</strong>の尺上限</li>
        <li>画質・物理表現のばらつき（バックフリップ等の失敗報告あり）</li>
        <li>Seedance 2.0 等との比較では「見た目は良いが演出・カメラワークは劣る」という実使用レビューも</li>
      </ul>
    </article>
    <article class="ov-card">
      <h3>このページのデータ</h3>
      <ul>
        <li>対象: 海外（本文に日本語なし）・動画付き・一人称の生成・検証っぽい X 投稿</li>
        <li>除外: Google 公式・まとめ系・明らかなリード獲得投稿</li>
        <li>収集: 既存ログ + Apify（英語検索 3 クエリ）→ 実使用っぽい投稿に絞り込み</li>
        <li>動画は X 上でプレビュー必須（サムネイルは参考画像）</li>
      </ul>
    </article>
  </div>
</section>"""


def _post_card(post: dict, *, featured: bool = False) -> str:
    url = escape(post.get("url") or "#")
    author = escape(post.get("author") or "?")
    likes = post.get("likes") or 0
    rts = post.get("retweets") or 0
    views = post.get("views") or 0
    tier = post.get("tier") or 1
    tier_label, tier_color = TIER_LABELS.get(tier, TIER_LABELS[1])
    promo = _is_promo(post)
    promo_badge = '<span class="badge promo">プロモ注意</span>' if promo else ""
    text = escape(_display_text(post))
    date = escape(_fmt_date(post.get("published_at") or ""))
    thumb = _thumb_url(post)
    thumb_html = ""
    if thumb:
        thumb_html = (
            f'<a class="thumb-wrap" href="{url}" target="_blank" rel="noopener">'
            f'<img src="{escape(thumb)}" alt="" loading="lazy" /></a>'
        )
    embed_html = ""
    if featured and not promo:
        raw_url = post.get("url") or ""
        embed_html = f"""
  <div class="tweet-embed">
    <blockquote class="twitter-tweet" data-dnt="true">
      <a href="{escape(raw_url)}"></a>
    </blockquote>
  </div>"""
    cls = "post-card featured" if featured else "post-card"
    stats = f"❤{likes:,} · RT{rts:,}"
    if views:
        stats += f" · 👁{views:,}"
    return f"""<article class="{cls}" data-tier="{tier}" data-promo="{1 if promo else 0}">
  <div class="post-head">
    <span class="badge tier" style="border-color:{tier_color};color:{tier_color}">{tier_label}</span>
    {promo_badge}
    <a class="author" href="https://x.com/{author}" target="_blank" rel="noopener">@{author}</a>
    <span class="stats">{stats}</span>
    <span class="date">{date}</span>
  </div>
  <div class="post-body">
    {thumb_html}
    <p class="post-text">{text}</p>
  </div>
  <div class="post-foot">
    <a class="x-link" href="{url}" target="_blank" rel="noopener">X で見る（動画プレビュー） →</a>
  </div>
  {embed_html}
</article>"""


def _featured_posts(posts: list[dict]) -> list[dict]:
    picked: list[dict] = []
    seen_urls: set[str] = set()
    for p in posts:
        if (p.get("tier") or 0) < 3:
            continue
        if _is_promo(p):
            continue
        url = p.get("url") or ""
        if url in seen_urls:
            continue
        seen_urls.add(url)
        picked.append(p)
        if len(picked) >= 12:
            break
    if len(picked) < 8:
        for p in posts:
            if (p.get("tier") or 0) < 2:
                continue
            url = p.get("url") or ""
            if url in seen_urls or _is_promo(p):
                continue
            seen_urls.add(url)
            picked.append(p)
            if len(picked) >= 12:
                break
    return picked


def sync_nav_in_docs() -> None:
    """site_nav 変更を既存 docs/*.html に反映"""
    pattern = re.compile(r"<nav class=\"topnav\">.*?</nav>", re.DOTALL)
    for path in sorted(glob(os.path.join(DOCS_DIR, "*.html"))):
        page = os.path.basename(path)
        new_nav = render_nav(page)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if not pattern.search(content):
            continue
        updated = pattern.sub(new_nav, content, count=1)
        if updated != content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(updated)
            logger.info("Updated nav in %s", page)


def build_gemini_omni_page(output_path: str = OUTPUT_PATH) -> None:
    posts, meta = _load_posts()
    posts = ensure_post_translations(posts)
    featured = _featured_posts(posts)
    featured_urls = {p.get("url") for p in featured}
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    cost = meta.get("apify_cost_usd")
    cost_str = f"${cost:.2f}" if isinstance(cost, (int, float)) else "—"
    nav_html = render_nav("gemini-omni.html")

    featured_html = "\n".join(_post_card(p, featured=True) for p in featured)
    all_html = "\n".join(
        _post_card(p) for p in posts if p.get("url") not in featured_urls
    )

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gemini Omni — 概要と海外実使用ポスト</title>
<style>
:root {{
  --bg: #0f1419; --card: #1a2236; --border: #2d3748;
  --text: #e2e8f0; --muted: #94a3b8; --accent: #4285f4; --accent2: #a78bfa;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding-top: 48px; }}
{NAV_CSS}
header {{ padding: 24px 20px 12px; border-bottom: 1px solid var(--border); }}
header h1 {{ font-size: 1.45rem; }}
header .meta {{ color: var(--muted); font-size: 0.85rem; margin-top: 6px; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 20px 16px 48px; }}
.toc {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }}
.toc a {{ padding: 6px 14px; background: var(--card); border: 1px solid var(--border); border-radius: 8px; color: var(--accent); text-decoration: none; font-size: 0.88rem; }}
.toc a:hover {{ background: rgba(66,133,244,0.15); }}
.overview {{ margin-bottom: 32px; }}
.overview h2 {{ font-size: 1.2rem; margin-bottom: 10px; color: var(--accent2); }}
.overview .lead {{ color: #cbd5e1; margin-bottom: 16px; max-width: 900px; }}
.overview-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }}
.ov-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }}
.ov-card h3 {{ font-size: 0.95rem; margin-bottom: 8px; color: var(--text); }}
.ov-card ul {{ padding-left: 1.1rem; font-size: 0.86rem; color: #cbd5e1; }}
.ov-card li {{ margin: 4px 0; }}
.section {{ margin-top: 28px; }}
.section h2 {{ font-size: 1.15rem; margin-bottom: 6px; }}
.section .hint {{ color: var(--muted); font-size: 0.84rem; margin-bottom: 14px; }}
.post-list {{ display: flex; flex-direction: column; gap: 14px; }}
.post-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }}
.post-card.featured {{ border-color: rgba(66,133,244,0.45); }}
.post-head {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 0.8rem; margin-bottom: 8px; }}
.badge {{ font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 8px; border: 1px solid; }}
.badge.promo {{ border-color: #f59e0b; color: #f59e0b; }}
.author {{ color: var(--accent); font-weight: 600; text-decoration: none; }}
.stats, .date {{ color: var(--muted); }}
.post-body {{ display: flex; gap: 12px; align-items: flex-start; }}
.thumb-wrap {{ flex-shrink: 0; display: block; width: 120px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }}
.thumb-wrap img {{ width: 100%; height: auto; display: block; }}
.post-text {{ font-size: 0.9rem; color: #cbd5e1; flex: 1; min-width: 0; }}
.post-foot {{ margin-top: 10px; }}
.x-link {{ color: var(--accent); font-size: 0.85rem; text-decoration: none; font-weight: 600; }}
.x-link:hover {{ text-decoration: underline; }}
.tweet-embed {{ margin-top: 12px; min-height: 48px; }}
footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 24px; border-top: 1px solid var(--border); margin-top: 32px; }}
@media (max-width: 640px) {{
  .post-body {{ flex-direction: column; }}
  .thumb-wrap {{ width: 100%; max-width: 200px; }}
}}
</style>
</head>
<body>
{nav_html}
<header>
  <h1>🎬 Gemini Omni</h1>
  <p class="meta">Last updated: {now_str} ｜ 実使用ポスト {len(posts)}件 ｜ Apify 収集コスト目安 {cost_str}</p>
</header>
<div class="container">
  <nav class="toc">
    <a href="#overview">概要</a>
    <a href="#featured">注目ポスト</a>
    <a href="#all-posts">一覧</a>
  </nav>
  {_overview_html()}
  <section class="section" id="featured">
    <h2>注目の実使用ポスト（動画付き・海外）</h2>
    <p class="hint">tier 3 中心。本文は日本語訳（原文は英語）。埋め込みは X のウィジェット。動画は各投稿のプレビューで確認してください。</p>
    <div class="post-list">{featured_html}</div>
  </section>
  <section class="section" id="all-posts">
    <h2>その他の収集ポスト</h2>
    <p class="hint">プロモ・紹介系（tier 1）を含む。本文は日本語訳。❤ 数・tier の降順。</p>
    <div class="post-list">{all_html}</div>
  </section>
</div>
<footer>データ: gemini_omni_overseas_hands_on_video.json ｜ 再生成: python build_gemini_omni.py</footer>
<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("Built Gemini Omni page → %s (%d posts, %d featured)", output_path, len(posts), len(featured))


def build() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_gemini_omni_page()
    sync_nav_in_docs()


if __name__ == "__main__":
    build()

"""Gemini活用法の過去バズ調査ページを生成する。"""

import json
import logging
import os
import re
from datetime import datetime
from html import escape, unescape
from pathlib import Path

from site_nav import NAV_CSS, render_nav
from translation_config import get_social_translation_model

logger = logging.getLogger("ai-news.build_gemini_buzz")
BASE = Path(__file__).parent
DATA_PATH = BASE / "data" / "gemini_buzz" / "ranking.json"
MANIFEST_PATH = BASE / "data" / "gemini_buzz" / "search_manifest.json"
TRANSLATIONS_PATH = BASE / "data" / "gemini_buzz" / "translations.json"
OUTPUT_PATH = BASE / "docs" / "gemini-buzz.html"
TRANSLATE_BATCH = 20
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


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_env_file() -> None:
    path = BASE / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _contains_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text or ""))


def _load_translation_cache() -> dict[str, str]:
    data = _load(TRANSLATIONS_PATH)
    return {
        key: value
        for key, value in (data.get("by_url") or {}).items()
        if isinstance(value, str) and value.strip()
    }


def _save_translation_cache(cache: dict[str, str]) -> None:
    TRANSLATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATIONS_PATH.write_text(
        json.dumps(
            {"by_url": cache, "updated_at": datetime.now().astimezone().isoformat()},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _translate_batch(client, posts: list[dict]) -> dict[str, str]:
    from google.genai import types

    model_name = get_social_translation_model()
    blocks = []
    for post in posts:
        url = post.get("url") or ""
        text = unescape(re.sub(r"\s+", " ", post.get("text") or "").strip())
        blocks.append(f"[ID: {url}]\n{text[:3500]}\n---")
    prompt = f"""以下のX投稿を自然な日本語へ翻訳してください。

## ルール
- 要約せず、意味と熱量を保って全文を翻訳する
- URL、@ユーザー名、製品名、モデル名は原文のままでよい
- 大文字による強調、絵文字、箇条書きのニュアンスを維持する
- 煽り表現も弱めず、そのまま日本語化する

## 投稿
{chr(10).join(blocks)}"""
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_json_schema": TRANSLATE_SCHEMA,
            "thinking_config": {"thinking_budget": 0},
            "max_output_tokens": 12000,
            "http_options": types.HttpOptions(timeout=120_000),
        },
    )
    from gemini_usage import log_usage

    log_usage("gemini_buzz_translate", model_name, response)
    parsed = json.loads(response.text or "{}")
    return {
        item.get("id"): (item.get("text_ja") or "").strip()
        for item in parsed.get("items") or []
        if item.get("id") and (item.get("text_ja") or "").strip()
    }


def ensure_post_translations(posts: list[dict]) -> list[dict]:
    """英語投稿だけをURL単位で翻訳し、既存翻訳は再利用する。"""
    _load_env_file()
    cache = _load_translation_cache()
    missing = [
        post
        for post in posts
        if not _contains_japanese(post.get("text") or "")
        and (post.get("url") or "") not in cache
    ]
    api_key = os.environ.get("GEMINI_API_KEY")
    if missing and api_key:
        from google import genai

        client = genai.Client(api_key=api_key)
        for start in range(0, len(missing), TRANSLATE_BATCH):
            batch = missing[start : start + TRANSLATE_BATCH]
            try:
                cache.update(_translate_batch(client, batch))
                _save_translation_cache(cache)
            except Exception as exc:
                logger.error("Translation batch failed: %s", exc)
                break
    elif missing:
        logger.warning("GEMINI_API_KEY not set: %d English posts remain untranslated", len(missing))

    enriched = []
    for post in posts:
        copy = dict(post)
        copy["text_ja"] = cache.get(copy.get("url") or "") or ""
        enriched.append(copy)
    return enriched


def _format_date(raw: str) -> str:
    """投稿日時を「2026年4月30日」形式へ変換する。"""
    raw = (raw or "").strip()
    if not raw:
        return ""
    # XのAPIは "Thu Apr 30 21:15:38 +0000 2026" 形式で返す
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return f"{dt.year}年{dt.month}月{dt.day}日"
        except ValueError:
            continue
    try:
        dt = datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")
        return f"{dt.year}年{dt.month}月{dt.day}日"
    except ValueError:
        return raw[:10]


def _engagement_rate_value(post: dict) -> float:
    """フォロワー数に対する総エンゲージメント率(%)を数値で返す。0なら-1。"""
    followers = int(post.get("author_followers") or 0)
    if followers <= 0:
        return -1.0
    engagements = sum(
        int(post.get(k) or 0)
        for k in ("likes", "retweets", "bookmarks", "quotes", "replies")
    )
    return engagements / followers * 100


def _engagement_rate(post: dict) -> str:
    """フォロワー数に対する総エンゲージメント率を「677%」形式で返す。"""
    rate = _engagement_rate_value(post)
    if rate < 0:
        return ""
    return f"{rate:,.0f}%" if rate >= 100 else f"{rate:.1f}%"


def _card(rank: int, post: dict) -> str:
    media = ""
    for item in post.get("media") or []:
        url = item.get("url") or ""
        if url.startswith("http"):
            media = f'<img class="thumb" src="{escape(url)}" loading="lazy" alt="">'
            break
    review = '<span class="review">要確認</span>' if post.get("needs_review") else ""
    discovery = ""
    if post.get("is_discovery"):
        label = "驚き" if post.get("discovery_kind") == "surprise" else "新機能"
        discovery = f'<span class="discovery">{label}</span>'
    er = _engagement_rate(post)
    er_value = _engagement_rate_value(post)
    er_html = (
        f'<span class="er" title="フォロワー数に対する総エンゲージメント率">'
        f"ER {escape(er)}</span>"
        if er
        else ""
    )
    likes = int(post.get("likes") or 0)
    retweets = int(post.get("retweets") or 0)
    bookmarks = int(post.get("bookmarks") or 0)
    buzz = int(post.get("buzz_score") or 0)
    original = post.get("text") or ""
    translated = (post.get("text_ja") or "").strip()
    display_text = translated or original
    original_html = ""
    if translated:
        original_html = (
            '\n    <details class="original"><summary>英語原文</summary>'
            f"<p>{escape(original)}</p></details>"
        )
    return f"""<article class="card" data-likes="{likes}" data-retweets="{retweets}" data-bookmarks="{bookmarks}" data-er="{er_value:.4f}" data-buzz="{buzz}" data-discovery="{int(bool(post.get("is_discovery")))}">
  <div class="rank">#{rank}</div>
  <div class="content">
    <div class="meta"><strong>{escape(post.get("author_display") or "")}</strong>
      <span class="handle">@{escape(post.get("author") or "")}</span>
      <span>{escape(_format_date(post.get("published_at") or ""))}</span>{discovery}{review}</div>
    <p>{escape(display_text)}</p>{original_html}
    <div class="stats">
      {er_html}
      <span>♥ {int(post.get("likes") or 0):,}</span>
      <span>↻ {int(post.get("retweets") or 0):,}</span>
      <span>🔖 {int(post.get("bookmarks") or 0):,}</span>
      <span>表示 {int(post.get("views") or 0):,}</span>
      <span>👤 {int(post.get("author_followers") or 0):,}</span>
      <a href="{escape(post.get("url") or "#")}" target="_blank" rel="noopener">Xで開く</a>
    </div>
  </div>{media}
</article>"""


def build() -> None:
    data = _load(DATA_PATH)
    manifest = _load(MANIFEST_PATH)
    posts = ensure_post_translations(data.get("posts") or [])
    discovery_count = sum(bool(post.get("is_discovery")) for post in posts)
    cards = "\n".join(_card(i, post) for i, post in enumerate(posts, 1))
    if not cards:
        cards = '<div class="empty">まだ調査を実行していません。</div>'
    period = manifest.get("period") or {}
    updated = (data.get("fetched_at") or "")[:19].replace("T", " ") or "未実行"
    summary = (
        f"対象: {period.get('start', '—')}〜{period.get('end', '—')} / "
        f"取得 {manifest.get('raw_count', 0)}件 / 採用 {len(posts)}件 / "
        f"驚き・新機能 {discovery_count}件 / "
        f"Apify ${float(manifest.get('apify_cost_usd') or 0):.4f}"
    )
    html = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gemini 驚き・新機能バズ調査</title>
<style>
:root{{--bg:#0f172a;--surface:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;--accent:#8b5cf6}}
*{{box-sizing:border-box}} body{{margin:0;padding-top:48px;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
{NAV_CSS}
main{{max-width:1050px;margin:auto;padding:28px 18px}} h1{{margin:0;color:#c4b5fd}} .lead{{color:var(--muted);line-height:1.7}}
.notice{{padding:12px 14px;border:1px solid #7c3aed;background:#2e1065;border-radius:10px;margin:18px 0;font-size:.86rem}}
.sortbar{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:18px 0;color:var(--muted);font-size:.85rem}}
.filterbar{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:18px 0;color:var(--muted);font-size:.85rem}}
.sortbtn{{cursor:pointer;padding:6px 12px;border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:999px;font-size:.82rem}}
.sortbtn:hover{{border-color:var(--accent)}} .sortbtn.active{{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:700}}
.filterbtn{{cursor:pointer;padding:6px 12px;border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:999px;font-size:.82rem}}
.filterbtn:hover{{border-color:#f59e0b}} .filterbtn.active{{background:#f59e0b;border-color:#f59e0b;color:#111827;font-weight:700}}
.card{{display:flex;gap:14px;align-items:flex-start;padding:16px;margin:12px 0;background:var(--surface);border:1px solid var(--border);border-radius:12px}}
.rank{{font-size:1.2rem;font-weight:800;color:#fbbf24;min-width:42px}} .content{{flex:1;min-width:0}}
.meta{{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;color:var(--muted);font-size:.8rem}} .meta strong{{color:var(--text)}} .meta .handle{{color:var(--muted)}} .content p{{white-space:pre-wrap;line-height:1.65}}
.stats{{display:flex;gap:14px;flex-wrap:wrap;align-items:center;color:var(--muted);font-size:.82rem}} .stats a{{color:#60a5fa}}
.er{{font-weight:700;color:#0f172a;background:#34d399;padding:1px 8px;border-radius:999px;font-size:.78rem}}
.thumb{{width:160px;max-height:120px;object-fit:cover;border-radius:8px}} .review{{color:#fbbf24}}
.discovery{{color:#111827;background:#fbbf24;padding:1px 7px;border-radius:999px;font-weight:700}}
.original{{margin:8px 0;color:var(--muted);font-size:.84rem}} .original summary{{cursor:pointer;color:#60a5fa}} .original p{{padding-left:12px;border-left:2px solid var(--border)}}
.empty{{padding:60px;text-align:center;color:var(--muted);border:1px dashed var(--border);border-radius:12px}}
@media(max-width:650px){{.thumb{{display:none}}.card{{gap:6px}}}}
</style></head><body>
{render_nav("gemini-buzz.html")}
<main><h1>Gemini 驚き・新機能バズ調査</h1>
<p class="lead">Geminiの新機能や具体的な能力を見て「これはすごい」と紹介している人気投稿を優先表示します。</p>
<div class="notice">{escape(summary)}<br>最終調査: {escape(updated)} UTC。XのTop検索は完全な全件取得ではありません。</div>
<div class="filterbar">表示:
  <button class="filterbtn active" data-filter="discovery">驚き・新機能</button>
  <button class="filterbtn" data-filter="all">すべて</button>
</div>
<div class="sortbar">並べ替え:
  <button class="sortbtn active" data-key="buzz">バズスコア</button>
  <button class="sortbtn" data-key="likes">いいね</button>
  <button class="sortbtn" data-key="retweets">リポスト</button>
  <button class="sortbtn" data-key="bookmarks">ブックマーク</button>
  <button class="sortbtn" data-key="er">エンゲージメント率</button>
</div>
<div id="cards">
{cards}
</div></main>
<script>
(function(){{
  var container=document.getElementById("cards");
  var cards=Array.prototype.slice.call(container.querySelectorAll(".card"));
  var buttons=document.querySelectorAll(".sortbtn");
  var filterButtons=document.querySelectorAll(".filterbtn");
  var currentFilter="discovery";
  function applyFilter(){{
    cards.forEach(function(card){{
      card.hidden=currentFilter==="discovery" && card.dataset.discovery!=="1";
    }});
    var visible=cards.filter(function(card){{return !card.hidden;}});
    visible.forEach(function(card,i){{card.querySelector(".rank").textContent="#"+(i+1);}});
  }}
  function sortBy(key){{
    cards.sort(function(a,b){{
      return parseFloat(b.dataset[key])-parseFloat(a.dataset[key]);
    }});
    cards.forEach(function(card,i){{
      card.querySelector(".rank").textContent="#"+(i+1);
      container.appendChild(card);
    }});
    applyFilter();
  }}
  buttons.forEach(function(btn){{
    btn.addEventListener("click",function(){{
      buttons.forEach(function(b){{b.classList.remove("active");}});
      btn.classList.add("active");
      sortBy(btn.dataset.key);
    }});
  }});
  filterButtons.forEach(function(btn){{
    btn.addEventListener("click",function(){{
      filterButtons.forEach(function(b){{b.classList.remove("active");}});
      btn.classList.add("active");
      currentFilter=btn.dataset.filter;
      applyFilter();
    }});
  }});
  applyFilter();
}})();
</script>
</body></html>"""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH} ({len(posts)} posts)")


if __name__ == "__main__":
    build()

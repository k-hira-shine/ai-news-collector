"""Gemini活用法の過去バズ調査ページを生成する。"""

import json
from datetime import datetime
from html import escape
from pathlib import Path

from site_nav import NAV_CSS, render_nav

BASE = Path(__file__).parent
DATA_PATH = BASE / "data" / "gemini_buzz" / "ranking.json"
MANIFEST_PATH = BASE / "data" / "gemini_buzz" / "search_manifest.json"
OUTPUT_PATH = BASE / "docs" / "gemini-buzz.html"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


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


def _engagement_rate(post: dict) -> str:
    """フォロワー数に対する総エンゲージメント率を「677%」形式で返す。"""
    followers = int(post.get("author_followers") or 0)
    if followers <= 0:
        return ""
    engagements = sum(
        int(post.get(k) or 0)
        for k in ("likes", "retweets", "bookmarks", "quotes", "replies")
    )
    rate = engagements / followers * 100
    return f"{rate:,.0f}%" if rate >= 100 else f"{rate:.1f}%"


def _card(rank: int, post: dict) -> str:
    media = ""
    for item in post.get("media") or []:
        url = item.get("url") or ""
        if url.startswith("http"):
            media = f'<img class="thumb" src="{escape(url)}" loading="lazy" alt="">'
            break
    review = '<span class="review">要確認</span>' if post.get("needs_review") else ""
    er = _engagement_rate(post)
    er_html = (
        f'<span class="er" title="フォロワー数に対する総エンゲージメント率">'
        f"ER {escape(er)}</span>"
        if er
        else ""
    )
    return f"""<article class="card">
  <div class="rank">#{rank}</div>
  <div class="content">
    <div class="meta"><strong>{escape(post.get("author_display") or "")}</strong>
      <span class="handle">@{escape(post.get("author") or "")}</span>
      <span>{escape(_format_date(post.get("published_at") or ""))}</span>{review}</div>
    <p>{escape(post.get("text") or "")}</p>
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
    posts = data.get("posts") or []
    cards = "\n".join(_card(i, post) for i, post in enumerate(posts, 1))
    if not cards:
        cards = '<div class="empty">まだ調査を実行していません。</div>'
    period = manifest.get("period") or {}
    updated = (data.get("fetched_at") or "")[:19].replace("T", " ") or "未実行"
    summary = (
        f"対象: {period.get('start', '—')}〜{period.get('end', '—')} / "
        f"取得 {manifest.get('raw_count', 0)}件 / 採用 {len(posts)}件 / "
        f"Apify ${float(manifest.get('apify_cost_usd') or 0):.4f}"
    )
    html = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gemini 活用法バズ調査</title>
<style>
:root{{--bg:#0f172a;--surface:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;--accent:#8b5cf6}}
*{{box-sizing:border-box}} body{{margin:0;padding-top:48px;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
{NAV_CSS}
main{{max-width:1050px;margin:auto;padding:28px 18px}} h1{{margin:0;color:#c4b5fd}} .lead{{color:var(--muted);line-height:1.7}}
.notice{{padding:12px 14px;border:1px solid #7c3aed;background:#2e1065;border-radius:10px;margin:18px 0;font-size:.86rem}}
.card{{display:flex;gap:14px;align-items:flex-start;padding:16px;margin:12px 0;background:var(--surface);border:1px solid var(--border);border-radius:12px}}
.rank{{font-size:1.2rem;font-weight:800;color:#fbbf24;min-width:42px}} .content{{flex:1;min-width:0}}
.meta{{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;color:var(--muted);font-size:.8rem}} .meta strong{{color:var(--text)}} .meta .handle{{color:var(--muted)}} .content p{{white-space:pre-wrap;line-height:1.65}}
.stats{{display:flex;gap:14px;flex-wrap:wrap;align-items:center;color:var(--muted);font-size:.82rem}} .stats a{{color:#60a5fa}}
.er{{font-weight:700;color:#0f172a;background:#34d399;padding:1px 8px;border-radius:999px;font-size:.78rem}}
.thumb{{width:160px;max-height:120px;object-fit:cover;border-radius:8px}} .review{{color:#fbbf24}}
.empty{{padding:60px;text-align:center;color:var(--muted);border:1px dashed var(--border);border-radius:12px}}
@media(max-width:650px){{.thumb{{display:none}}.card{{gap:6px}}}}
</style></head><body>
{render_nav("gemini-buzz.html")}
<main><h1>Gemini 活用法バズ調査</h1>
<p class="lead">過去に反響が大きかったGeminiの使い方・プロンプト・活用事例を、取得時点のいいね数順に保存した調査資料です。</p>
<div class="notice">{escape(summary)}<br>最終調査: {escape(updated)} UTC。XのTop検索は完全な全件取得ではありません。</div>
{cards}</main></body></html>"""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Generated {OUTPUT_PATH} ({len(posts)} posts)")


if __name__ == "__main__":
    build()

"""HackerNews + arxiv データから docs/hn.html を生成"""

import json
import logging
import os
from datetime import datetime, timezone
from glob import glob
from html import escape

from utils import data_dir

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("ai-news.build_hn")

HN_DATA_DIR = data_dir("hn")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "hn.html")


def load_hn_items(days: int = 7) -> list[dict]:
    """data/hn/ から直近 days 日分を読み込んで返す"""
    if not os.path.isdir(HN_DATA_DIR):
        return []
    files = sorted(glob(os.path.join(HN_DATA_DIR, "*.jsonl")), reverse=True)
    items: list[dict] = []
    seen_ids: set[str] = set()
    for f in files[:days]:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    if item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        items.append(item)
                except Exception:
                    continue
    return items


def _fmt_date(iso: str) -> str:
    """ISO文字列を表示用の短い形式に変換"""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - dt
        hours = int(diff.total_seconds() / 3600)
        if hours < 1:
            return "1時間以内"
        if hours < 24:
            return f"{hours}時間前"
        days = diff.days
        return f"{days}日前"
    except Exception:
        return iso[:10] if iso else ""


def build_hn_page(output_path: str = OUTPUT_PATH) -> None:
    items = load_hn_items(days=7)
    hn_items = sorted(
        [i for i in items if i.get("source") == "hn"],
        key=lambda x: x["engagement"].get("likes", 0),
        reverse=True,
    )
    arxiv_items = sorted(
        [i for i in items if i.get("source") == "arxiv"],
        key=lambda x: x.get("published_at", ""),
        reverse=True,
    )

    now_jst = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M JST")
    hn_count = len(hn_items)
    arxiv_count = len(arxiv_items)

    # ── HN カード HTML ────────────────────────────────
    hn_cards_html = ""
    if hn_items:
        for item in hn_items:
            title_ja = item.get("title_ja", "")
            title_en = escape(item.get("title", ""))
            title_display = escape(title_ja) if title_ja else title_en
            sub_title_html = f'<div class="item-title-en">{title_en}</div>' if title_ja else ""

            url = escape(item.get("url", "#"))
            hn_url = escape(item.get("hn_item_url", "#"))
            author = escape(item.get("author", ""))
            points = item["engagement"].get("likes", 0)
            comments = item["engagement"].get("replies", 0)
            age = _fmt_date(item.get("published_at", ""))
            hn_cards_html += f"""
<div class="item-card">
  <div class="item-title"><a href="{url}" target="_blank" rel="noopener">{title_display}</a></div>
  {sub_title_html}
  <div class="item-meta">
    <span class="badge badge-score">▲ {points}</span>
    <span class="badge badge-comments">💬 {comments}</span>
    <span class="meta-author">by {author}</span>
    <span class="meta-age">{age}</span>
    <a href="{hn_url}" target="_blank" rel="noopener" class="hn-link">HNで議論を見る →</a>
  </div>
</div>"""
    else:
        hn_cards_html = '<div class="empty">データなし（次回の収集をお待ちください）</div>'

    # ── arxiv カード HTML ─────────────────────────────
    arxiv_cards_html = ""
    cat_labels = {"cs.AI": "AI全般", "cs.LG": "機械学習", "cs.CL": "自然言語処理"}
    if arxiv_items:
        for item in arxiv_items:
            # 日本語訳があれば優先、なければ英語をそのまま表示
            title_ja = item.get("title_ja", "")
            title_en = escape(item.get("title", ""))
            title_display = escape(title_ja) if title_ja else title_en
            summary_ja = item.get("arxiv_summary_ja", "")
            summary_en = item.get("arxiv_summary", "")
            summary_display = escape(summary_ja) if summary_ja else escape(summary_en)

            url = escape(item.get("url", "#"))
            author = escape(item.get("author", ""))
            cat = item.get("arxiv_category", "")
            cat_label = escape(cat_labels.get(cat, cat))
            age = _fmt_date(item.get("published_at", ""))

            # 英語タイトルは小さくサブ表示
            sub_title_html = f'<div class="item-title-en">{title_en}</div>' if title_ja else ""

            arxiv_cards_html += f"""
<div class="item-card">
  <div class="item-title"><a href="{url}" target="_blank" rel="noopener">{title_display}</a></div>
  {sub_title_html}
  <div class="item-meta">
    <span class="badge badge-cat">{cat_label}</span>
    <span class="meta-author">{author}</span>
    <span class="meta-age">{age}</span>
  </div>
  {f'<div class="item-summary">{summary_display}</div>' if summary_display else ''}
</div>"""
    else:
        arxiv_cards_html = '<div class="empty">データなし（次回の収集をお待ちください）</div>'

    # ── HTML 生成 ─────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 英語一次情報 (HN + arxiv)</title>
<style>
:root {{
  --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
  --text: #e2e8f0; --muted: #94a3b8; --accent: #818cf8;
  --green: #34d399; --red: #f87171; --yellow: #fbbf24; --blue: #60a5fa;
  --orange: #fb923c;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 2rem 1rem; }}
header {{ text-align: center; margin-bottom: 2rem; }}
header h1 {{ font-size: 1.8rem; color: var(--accent); }}
header .updated {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.3rem; }}
.nav-links {{ display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap; margin-top: 0.8rem; }}
.nav-link {{ display: inline-block; padding: 0.4rem 1rem; background: var(--surface2); border-radius: 8px; color: var(--blue); text-decoration: none; font-size: 0.9rem; }}
.nav-link:hover {{ background: #475569; }}
.stats-bar {{ display: flex; gap: 1rem; justify-content: center; margin-bottom: 1.5rem; flex-wrap: wrap; }}
.stat-badge {{ background: var(--surface); border-radius: 8px; padding: 0.5rem 1.2rem; font-size: 0.9rem; color: var(--muted); }}
.stat-badge span {{ color: var(--text); font-weight: 700; margin-right: 0.3rem; }}
.columns {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
@media (max-width: 760px) {{ .columns {{ grid-template-columns: 1fr; }} }}
.col-header {{ display: flex; align-items: center; gap: 0.6rem; margin-bottom: 1rem; padding-bottom: 0.6rem; border-bottom: 2px solid var(--surface2); }}
.col-header h2 {{ font-size: 1.15rem; color: var(--accent); }}
.col-header .col-count {{ font-size: 0.85rem; color: var(--muted); }}
.item-card {{ background: var(--surface); border-radius: 10px; padding: 1rem 1.1rem; margin-bottom: 0.8rem; }}
.item-card:last-child {{ margin-bottom: 0; }}
.item-title {{ font-size: 0.97rem; font-weight: 600; margin-bottom: 0.5rem; line-height: 1.5; }}
.item-title a {{ color: var(--text); text-decoration: none; }}
.item-title a:hover {{ color: var(--accent); }}
.item-meta {{ display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; font-size: 0.82rem; }}
.badge {{ display: inline-block; padding: 1px 8px; border-radius: 4px; font-size: 0.78rem; font-weight: 600; }}
.badge-score {{ background: #f59e0b22; color: var(--yellow); }}
.badge-comments {{ background: #3b82f622; color: var(--blue); }}
.badge-cat {{ background: #818cf822; color: var(--accent); }}
.meta-author {{ color: var(--muted); }}
.meta-age {{ color: var(--muted); margin-left: auto; }}
.hn-link {{ color: var(--orange); text-decoration: none; font-size: 0.8rem; white-space: nowrap; }}
.hn-link:hover {{ color: var(--accent); }}
.item-summary {{ margin-top: 0.5rem; font-size: 0.85rem; color: var(--muted); line-height: 1.5; }}
.item-title-en {{ margin-top: 0.2rem; font-size: 0.78rem; color: var(--muted); line-height: 1.4; }}
.empty {{ text-align: center; color: var(--muted); padding: 3rem 0; font-size: 1rem; }}
@media (max-width: 640px) {{
  header h1 {{ font-size: 1.3rem; }}
  .nav-link {{ padding: 0.35rem 0.7rem; font-size: 0.82rem; }}
  .item-card {{ padding: 0.8rem; }}
  .item-title {{ font-size: 0.9rem; }}
}}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>AI 英語一次情報</h1>
  <div class="updated">Last updated: {now_jst}</div>
  <div class="nav-links">
    <a class="nav-link" href="index.html">📰 ニュース</a>
    <a class="nav-link" href="strategy.html">🎯 施策提案</a>
    <a class="nav-link" href="buzz.html">🔥 バズりランキング</a>
    <a class="nav-link" href="money.html">🎬 動画マネタイズ事例</a>
  </div>
</header>
<div class="stats-bar">
  <div class="stat-badge"><span>{hn_count}</span>HN 記事</div>
  <div class="stat-badge"><span>{arxiv_count}</span>arxiv 論文</div>
</div>
<div class="columns">
  <div>
    <div class="col-header">
      <h2>HackerNews</h2>
      <span class="col-count">スコア順 · 直近48時間</span>
    </div>
    {hn_cards_html}
  </div>
  <div>
    <div class="col-header">
      <h2>arxiv 新着論文</h2>
      <span class="col-count">cs.AI / cs.LG / cs.CL · 直近2日</span>
    </div>
    {arxiv_cards_html}
  </div>
</div>
</div>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, output_path)
    logger.info("hn.html written → %s (%d HN + %d arxiv)", output_path, hn_count, arxiv_count)


if __name__ == "__main__":
    build_hn_page()
    print(f"Generated: {OUTPUT_PATH}")

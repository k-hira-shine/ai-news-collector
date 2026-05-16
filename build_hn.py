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

CAT_LABELS = {"cs.AI": "AI全般", "cs.LG": "機械学習", "cs.CL": "自然言語処理"}


def load_all_dates(days: int = 14) -> dict[str, list[dict]]:
    """data/hn/ から直近 days 日分を日付ごとに返す {date_str: [items]}"""
    if not os.path.isdir(HN_DATA_DIR):
        return {}
    files = sorted(glob(os.path.join(HN_DATA_DIR, "*.jsonl")), reverse=True)
    result: dict[str, list[dict]] = {}
    for f in files[:days]:
        date_str = os.path.basename(f).replace(".jsonl", "")
        items: list[dict] = []
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
        result[date_str] = items
    return result


def _fmt_date(iso: str) -> str:
    if not iso:
        return ""
    from zoneinfo import ZoneInfo
    JST = ZoneInfo("Asia/Tokyo")
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(JST).strftime("%Y/%m/%d %H:%M")
    except ValueError:
        pass
    try:
        dt = datetime.strptime(iso, "%a %b %d %H:%M:%S %z %Y")
        return dt.astimezone(JST).strftime("%Y/%m/%d %H:%M")
    except ValueError:
        pass
    return iso[:10]


def _hn_card(item: dict) -> str:
    title_ja = item.get("title_ja", "")
    title_en = escape(item.get("title", ""))
    title_display = escape(title_ja) if title_ja else title_en
    sub_title_html = f'<div class="item-title-en">{title_en}</div>' if title_ja else ""
    url = escape(item.get("url", "#"))
    hn_url = escape(item.get("hn_item_url", "#"))
    author = escape(item.get("author", ""))
    points = item.get("engagement", {}).get("likes", 0)
    comments = item.get("engagement", {}).get("replies", 0)
    age = _fmt_date(item.get("published_at", ""))
    return f"""<div class="item-card">
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


def _arxiv_card(item: dict) -> str:
    title_ja = item.get("title_ja", "")
    title_en = escape(item.get("title", ""))
    title_display = escape(title_ja) if title_ja else title_en
    sub_title_html = f'<div class="item-title-en">{title_en}</div>' if title_ja else ""
    summary_ja = item.get("arxiv_summary_ja", "")
    summary_en = item.get("arxiv_summary", "")
    summary_display = escape(summary_ja) if summary_ja else escape(summary_en)
    url = escape(item.get("url", "#"))
    author = escape(item.get("author", ""))
    cat = item.get("arxiv_category", "")
    cat_label = escape(CAT_LABELS.get(cat, cat))
    age = _fmt_date(item.get("published_at", ""))
    summary_html = f'<div class="item-summary">{summary_display}</div>' if summary_display else ""
    return f"""<div class="item-card">
  <div class="item-title"><a href="{url}" target="_blank" rel="noopener">{title_display}</a></div>
  {sub_title_html}
  <div class="item-meta">
    <span class="badge badge-cat">{cat_label}</span>
    <span class="meta-author">{author}</span>
    <span class="meta-age">{age}</span>
  </div>
  {summary_html}
</div>"""


def _date_label(date_str: str) -> str:
    """2026-05-13 → 5/13"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.month}/{dt.day}"
    except Exception:
        return date_str


def build_hn_page(output_path: str = OUTPUT_PATH) -> None:
    all_dates = load_all_dates(days=14)
    if not all_dates:
        logger.warning("No HN data found")
        all_dates = {}

    sorted_dates = sorted(all_dates.keys(), reverse=True)
    from zoneinfo import ZoneInfo
    now_jst = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M JST")

    # 各日付のパネル HTML を生成
    panels_html = ""
    tabs_html = ""
    total_hn = 0
    total_arxiv = 0

    for i, date_str in enumerate(sorted_dates):
        items = all_dates[date_str]
        hn_items = sorted(
            [it for it in items if it.get("source") == "hn"],
            key=lambda x: x.get("engagement", {}).get("likes", 0),
            reverse=True,
        )
        arxiv_items = sorted(
            [it for it in items if it.get("source") == "arxiv"],
            key=lambda x: x.get("published_at", ""),
            reverse=True,
        )

        if i == 0:
            total_hn = len(hn_items)
            total_arxiv = len(arxiv_items)

        hn_cards = "".join(_hn_card(it) for it in hn_items) or '<div class="empty">データなし</div>'
        arxiv_cards = "".join(_arxiv_card(it) for it in arxiv_items) or '<div class="empty">データなし</div>'

        active_class = " active" if i == 0 else ""
        label = _date_label(date_str)
        is_today = i == 0
        today_mark = " <small>今日</small>" if is_today else ""

        tabs_html += f'<button class="date-tab{active_class}" data-panel="panel-{date_str}">{label}{today_mark}</button>\n'

        panels_html += f"""<div class="date-panel{active_class}" id="panel-{date_str}">
  <div class="stats-bar">
    <div class="stat-badge"><span>{len(hn_items)}</span>HN 記事</div>
    <div class="stat-badge"><span>{len(arxiv_items)}</span>arxiv 論文</div>
  </div>
  <div class="columns">
    <div>
      <div class="col-header">
        <h2>HackerNews</h2>
        <span class="col-count">スコア順 · 直近48時間</span>
      </div>
      {hn_cards}
    </div>
    <div>
      <div class="col-header">
        <h2>arxiv 新着論文</h2>
        <span class="col-count">cs.AI / cs.LG / cs.CL · 直近2日</span>
      </div>
      {arxiv_cards}
    </div>
  </div>
</div>
"""

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
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding-top: 48px; }}
.topnav {{ position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: #0f172aee; backdrop-filter: blur(8px); border-bottom: 1px solid var(--surface2); display: flex; gap: 0.4rem; justify-content: center; flex-wrap: wrap; padding: 6px 12px; }}
.nav-link {{ display: inline-block; padding: 4px 12px; background: var(--surface2); border-radius: 6px; color: var(--blue); text-decoration: none; font-size: 0.82rem; white-space: nowrap; }}
.nav-link:hover {{ background: #475569; color: #fff; }}
.nav-link.active {{ background: var(--accent); color: #fff; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 1.5rem 1rem 2rem; }}
header {{ text-align: center; margin-bottom: 1.5rem; }}
header h1 {{ font-size: 1.8rem; color: var(--accent); }}
header .updated {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.3rem; }}
.date-tabs {{ display: flex; gap: 0.4rem; flex-wrap: wrap; justify-content: center; margin-bottom: 1.5rem; }}
.date-tab {{
  padding: 0.4rem 1rem; border-radius: 8px; border: 1px solid var(--surface2);
  background: var(--surface); color: var(--muted); cursor: pointer;
  font-size: 0.88rem; transition: all 0.15s;
}}
.date-tab small {{ font-size: 0.75rem; color: var(--accent); margin-left: 0.3rem; }}
.date-tab:hover {{ background: var(--surface2); color: var(--text); }}
.date-tab.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
.date-tab.active small {{ color: #fff; }}
.date-panel {{ display: none; }}
.date-panel.active {{ display: block; }}
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
  .topnav {{ gap: 4px; padding: 4px 8px; }}
  .nav-link {{ padding: 3px 8px; font-size: 0.75rem; }}
  .item-card {{ padding: 0.8rem; }}
  .item-title {{ font-size: 0.9rem; }}
}}
</style>
</head>
<body>
<nav class="topnav">
  <a class="nav-link" href="home.html">🏠 ホーム</a>
  <a class="nav-link" href="index.html">📰 ニュース</a>
  <a class="nav-link" href="strategy.html">🎯 施策提案</a>
  <a class="nav-link" href="buzz.html">🔥 バズりランキング</a>
  <a class="nav-link" href="money.html">🎬 マネタイズ</a>
  <a class="nav-link" href="sns_success.html">🧠 SNS成功者</a>
  <a class="nav-link" href="post_generator.html">✍️ 投稿ストック</a>
  <a class="nav-link" href="tools.html">🔧 ツール追跡</a>
  <a class="nav-link" href="reviews.html">📋 使ってみた</a>
</nav>
<div class="container">
<header>
  <h1>AI 英語一次情報</h1>
  <div class="updated">Last updated: {now_jst}</div>
</header>
<div class="date-tabs">
{tabs_html}</div>
{panels_html}
</div>
<script>
document.querySelectorAll('.date-tab').forEach(tab => {{
  tab.addEventListener('click', () => {{
    document.querySelectorAll('.date-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.date-panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const panel = document.getElementById(tab.dataset.panel);
    if (panel) panel.classList.add('active');
  }});
}});
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, output_path)
    logger.info(
        "hn.html written → %s (%d dates, today: %d HN + %d arxiv)",
        output_path, len(sorted_dates), total_hn, total_arxiv,
    )


if __name__ == "__main__":
    build_hn_page()
    print(f"Generated: {OUTPUT_PATH}")

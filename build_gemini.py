"""Gemini機能追跡ページ — docs/gemini.html 生成"""

import json
import logging
import os
from datetime import datetime
from glob import glob
from html import escape
from zoneinfo import ZoneInfo

logger = logging.getLogger("ai-news.build_gemini")

GEMINI_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "gemini")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "gemini.html")

NAV_LINKS = [
    ("home.html",           "🏠 ホーム"),
    ("index.html",          "📰 ニュース"),
    ("strategy.html",       "🎯 施策提案"),
    ("buzz.html",           "🔥 バズりランキング"),
    ("money.html",          "🎬 マネタイズ"),
    ("sns_success.html",    "🧠 SNS成功者"),
    ("post_generator.html", "✍️ 投稿ストック"),
    ("tools.html",          "🔧 ツール追跡"),
    ("reviews.html",        "📋 使ってみた"),
    ("gemini.html",         "✨ Gemini追跡"),
]

STATUS_LABELS = {
    "available_now": ("今すぐ使える", "#10b981"),
    "coming_soon":   ("近日公開予定", "#f59e0b"),
    "unknown":       ("未分類", "#64748b"),
}

SOURCE_ICONS = {
    "rss": "📰",
    "scrape": "🌐",
    "x": "🐦",
}


def _to_jst_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
    except Exception:
        return iso[:10] if len(iso) >= 10 else iso


def load_gemini_items(days: int = 14) -> list[dict]:
    if not os.path.isdir(GEMINI_DATA_DIR):
        return []
    files = sorted(glob(os.path.join(GEMINI_DATA_DIR, "*.jsonl")), reverse=True)
    items: list[dict] = []
    for fpath in files[:days]:
        with open(fpath, encoding="utf-8") as f:
            for line in f.read().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
    return items


def _dedupe_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for item in sorted(
        items,
        key=lambda x: x.get("published_at") or x.get("collected_at") or "",
        reverse=True,
    ):
        key = item.get("url") or item.get("id") or ""
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _card(item: dict) -> str:
    status = item.get("status") or "unknown"
    label, color = STATUS_LABELS.get(status, STATUS_LABELS["unknown"])
    src = item.get("source", "")
    icon = SOURCE_ICONS.get(src, "📌")
    display_title = escape(
        item.get("title_ja") or item.get("summary_ja") or item.get("title") or ""
    )
    summary = escape(item.get("summary_ja") or "")
    source_label = escape(item.get("source_label") or "")
    url = escape(item.get("url") or "#")
    date = _to_jst_date(item.get("published_at") or item.get("collected_at") or "")

    summary_block = f'<p class="card-summary">{summary}</p>' if summary and summary != display_title else ""

    return f"""<article class="gemini-card" data-status="{escape(status)}">
  <div class="card-head">
    <span class="status-badge" style="border-color:{color};color:{color}">{label}</span>
    <span class="source-badge">{icon} {source_label}</span>
    <span class="date-badge">{date}</span>
  </div>
  <h3 class="card-title"><a href="{url}" target="_blank" rel="noopener">{display_title}</a></h3>
  {summary_block}
</article>"""


def _section(title: str, items: list[dict], empty_msg: str) -> str:
    if not items:
        return f"""<section class="gemini-section">
  <h2>{escape(title)} <span class="count">0件</span></h2>
  <div class="empty-state"><p>{escape(empty_msg)}</p></div>
</section>"""
    cards = "\n".join(_card(i) for i in items)
    return f"""<section class="gemini-section">
  <h2>{escape(title)} <span class="count">{len(items)}件</span></h2>
  <div class="gemini-grid">{cards}</div>
</section>"""


def _sources_section(items: list[dict]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        label = item.get("source_label") or item.get("source") or "unknown"
        counts[label] = counts.get(label, 0) + 1
    rows = "".join(
        f"<li><strong>{escape(label)}</strong>: {count}件</li>"
        for label, count in sorted(counts.items(), key=lambda x: -x[1])
    )
    return f"""<section class="gemini-section sources-section">
  <h2>チェックした情報源</h2>
  <ul class="sources-list">{rows or '<li>データなし</li>'}</ul>
</section>"""


def build_gemini_page(output_path: str = OUTPUT_PATH) -> None:
    items = _dedupe_items(load_gemini_items(days=14))
    now_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M JST")

    available = [i for i in items if i.get("status") == "available_now"]
    coming = [i for i in items if i.get("status") == "coming_soon"]

    nav_html = "\n".join(
        f'  <a href="{href}" class="nav-link{" active" if href == "gemini.html" else ""}">{label}</a>'
        for href, label in NAV_LINKS
    )

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gemini 機能トラッカー</title>
<style>
:root {{
  --bg: #0f1419; --card: #1a2236; --border: #2d3748;
  --text: #e2e8f0; --muted: #94a3b8; --accent: #4285f4;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
.topnav {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 10px 16px; background: #0a0e17; border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 100; }}
.topnav a {{ color: var(--muted); text-decoration: none; font-size: 0.82rem; padding: 4px 10px; border-radius: 6px; white-space: nowrap; }}
.topnav a:hover {{ color: var(--text); background: rgba(255,255,255,0.05); }}
.topnav a.active {{ color: var(--accent); background: rgba(66,133,244,0.15); }}
header {{ padding: 24px 20px 12px; border-bottom: 1px solid var(--border); }}
header h1 {{ font-size: 1.4rem; color: var(--text); }}
header .meta {{ color: var(--muted); font-size: 0.85rem; margin-top: 6px; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 20px 16px 40px; }}
.gemini-section {{ margin-bottom: 36px; }}
.gemini-section h2 {{ font-size: 1.1rem; margin-bottom: 14px; color: var(--text); }}
.gemini-section h2 .count {{ font-size: 0.85rem; color: var(--muted); font-weight: normal; }}
.gemini-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }}
.gemini-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }}
.card-head {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; align-items: center; }}
.status-badge {{ font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 10px; border: 1px solid; }}
.source-badge, .date-badge {{ font-size: 0.72rem; color: var(--muted); }}
.card-title {{ font-size: 0.95rem; margin-bottom: 6px; line-height: 1.4; }}
.card-title a {{ color: var(--text); text-decoration: none; }}
.card-title a:hover {{ color: var(--accent); }}
.card-summary {{ font-size: 0.85rem; color: #cbd5e1; }}
.card-reason {{ font-size: 0.78rem; color: var(--muted); margin-top: 6px; }}
.empty-state {{ text-align: center; padding: 40px 20px; color: var(--muted); background: var(--card); border-radius: 10px; border: 1px dashed var(--border); }}
.sources-list {{ list-style: none; background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 20px; }}
.sources-list li {{ padding: 4px 0; font-size: 0.85rem; color: var(--muted); }}
footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 24px; border-top: 1px solid var(--border); }}
@media (max-width: 640px) {{ .gemini-grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<nav class="topnav">
{nav_html}
</nav>
<header>
  <h1>✨ Gemini 機能トラッカー</h1>
  <p class="meta">Last updated: {now_str} ｜ 収集 {len(items)}件（今すぐ {len(available)} / 近日 {len(coming)}）</p>
</header>
<div class="container">
{_section("今すぐ使える機能", available, "直近14日で「利用可能」と判定された情報はまだありません。")}
{_section("近日公開予定", coming, "直近14日で「近日公開」と判定された情報はまだありません。")}
{_sources_section(items)}
</div>
<footer>Gemini公式RSS・Release Notes・API Changelog・公式Xアカウントを毎日自動チェック</footer>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("Built Gemini page → %s (%d items)", output_path, len(items))


def build() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_gemini_page()


if __name__ == "__main__":
    build()

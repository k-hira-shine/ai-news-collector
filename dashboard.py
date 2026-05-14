"""GitHub Pages 用 HTML ダッシュボード生成 (docs/index.html)"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from glob import glob
from html import escape

from utils import data_dir, STATUS_BANNER_HTML

logger = logging.getLogger("ai-news.dashboard")


def generate_dashboard(output_path: str) -> None:
    """data/analysis/ の直近データから HTML ダッシュボードを生成"""
    analyses = _load_recent_analyses(days=7)
    latest = analyses[0] if analyses else None
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    diagrams_dir = os.path.join(os.path.dirname(output_path), "diagrams")
    diagram_files = _list_recent_diagrams(diagrams_dir, limit=14)

    html = _render(latest, analyses, diagram_files)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, output_path)
    logger.info("Dashboard written → %s", output_path)


def _list_recent_diagrams(diagrams_dir: str, limit: int = 14) -> list[dict]:
    """docs/diagrams/*.html を新しい順に返す（PNGがあれば png_path も付与）"""
    if not os.path.isdir(diagrams_dir):
        return []
    _SLOT_ORDER = {"evening": 0, "morning": 1}  # 夕便が新しい（同日内では夕>朝）

    def _diag_sort_key(p: str) -> tuple:
        base = os.path.basename(p).rsplit(".html", 1)[0]
        date_part = base[:10] if len(base) >= 10 else base
        slot_part = base[11:] if len(base) > 11 else ""
        return (date_part, _SLOT_ORDER.get(slot_part, 99))

    files = sorted(glob(os.path.join(diagrams_dir, "*.html")), key=_diag_sort_key, reverse=True)
    results: list[dict] = []
    for f in files[:limit]:
        name = os.path.basename(f)
        base = name.rsplit(".html", 1)[0]
        date_part = base[:10] if len(base) >= 10 else base
        slot_part = base[11:] if len(base) > 11 else ""
        slot_label = {"morning": "朝便", "evening": "夕便"}.get(slot_part, slot_part)
        png_path = os.path.join(diagrams_dir, f"{base}.png")
        entry = {
            "name": name,
            "date": date_part,
            "slot": slot_label,
            "rel_path": f"diagrams/{name}",
        }
        if os.path.exists(png_path):
            entry["png_path"] = f"diagrams/{base}.png"
        results.append(entry)
    return results


def _load_recent_analyses(days: int = 7) -> list[dict]:
    analysis_dir = data_dir("analysis")
    if not os.path.isdir(analysis_dir):
        return []
    _SLOT_ORDER = {"morning": 0, "evening": 1}

    def _sort_key(p: str) -> tuple:
        base = os.path.basename(p).rsplit(".json", 1)[0]
        date_part = base[:10]
        slot_part = base[11:] if len(base) > 11 else ""
        return (date_part, _SLOT_ORDER.get(slot_part, 99))

    files = sorted(glob(os.path.join(analysis_dir, "*.json")), key=_sort_key, reverse=True)
    results: list[dict] = []
    for f in files[: days * 2]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                analysis = json.load(fh)
                base = os.path.basename(f).rsplit(".json", 1)[0]
                if len(base) >= 10:
                    analysis["_display_date"] = base[:10]
                if "_" in base:
                    analysis["_display_slot"] = base.rsplit("_", 1)[1]
                results.append(analysis)
        except (json.JSONDecodeError, OSError):
            continue
    return results


def _render(latest: dict | None, history: list[dict], diagrams: list[dict] | None = None) -> str:
    JST = timezone(timedelta(hours=9))
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    STATUS_BANNER = STATUS_BANNER_HTML

    diagrams = diagrams or []
    hn_items = _load_hn_today()
    if not latest:
        body = '<p class="empty">まだ分析データがありません。初回実行をお待ちください。</p>'
    else:
        body = _render_diagrams(diagrams) + _render_news_tabs(history) + _render_history(history) + _render_hn_section(hn_items)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI News Dashboard</title>
<style>
:root {{
  --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
  --text: #e2e8f0; --muted: #94a3b8; --accent: #818cf8;
  --green: #34d399; --red: #f87171; --yellow: #fbbf24; --blue: #60a5fa;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding-top: 48px; }}
.topnav {{ position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: #0f172aee; backdrop-filter: blur(8px); border-bottom: 1px solid var(--surface2); display: flex; gap: 0.4rem; justify-content: center; flex-wrap: wrap; padding: 6px 12px; }}
.nav-link {{ display: inline-block; padding: 4px 12px; background: var(--surface2); border-radius: 6px; color: var(--blue); text-decoration: none; font-size: 0.82rem; white-space: nowrap; }}
.nav-link:hover {{ background: #475569; color: #fff; }}
.nav-link.active {{ background: var(--accent); color: #fff; }}
.container {{ max-width: 960px; margin: 0 auto; padding: 1.5rem 1rem 2rem; }}
header {{ text-align: center; margin-bottom: 2rem; }}
header h1 {{ font-size: 1.8rem; color: var(--accent); }}
header .updated {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.3rem; }}
.card {{ background: var(--surface); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }}
.card h2 {{ font-size: 1.2rem; color: var(--accent); margin-bottom: 1rem; border-bottom: 1px solid var(--surface2); padding-bottom: 0.5rem; }}
.trend {{ font-size: 1rem; }}
.since-last {{ margin-top: 1rem; padding: 0.8rem; background: var(--surface2); border-radius: 8px; font-size: 0.95rem; }}
.trend-evo {{ margin-top: 1rem; }}
.trend-evo .evo-item {{ padding: 0.6rem 0.8rem; border-radius: 8px; background: var(--surface2); margin-bottom: 0.5rem; display: flex; flex-direction: column; gap: 0.3rem; }}
.trend-evo .evo-item:last-child {{ margin-bottom: 0; }}
.trend-evo .status-badge {{ display: inline-block; padding: 1px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600; white-space: nowrap; }}
.trend-evo .st-NEW {{ background: #16a34a33; color: var(--green); }}
.trend-evo .st-RISING {{ background: #dc262633; color: var(--red); }}
.trend-evo .st-SUSTAINED {{ background: #1e40af33; color: var(--blue); }}
.trend-evo .st-FADING {{ background: #6b728033; color: var(--muted); }}
.trend-evo .st-RESURFACED {{ background: #f59e0b33; color: var(--yellow); }}
.trend-evo .evo-topic {{ font-weight: 600; font-size: 0.95rem; }}
.trend-evo .evo-header {{ display: flex; align-items: center; gap: 0.5rem; }}
.trend-evo .evo-streak {{ color: var(--muted); font-size: 0.82rem; }}
.trend-evo .evo-desc {{ color: var(--muted); font-size: 0.85rem; border-top: 1px solid var(--surface); padding-top: 0.3rem; margin-top: 0.1rem; }}
.article {{ padding: 0.8rem 0; border-bottom: 1px solid var(--surface2); }}
.article:last-child {{ border-bottom: none; }}
.article .rank {{ display: inline-block; width: 28px; height: 28px; line-height: 28px; text-align: center; border-radius: 6px; background: var(--accent); color: #fff; font-weight: 700; font-size: 0.85rem; margin-right: 0.5rem; vertical-align: top; }}
.article .rank.gold {{ background: #f59e0b; }}
.article .rank.silver {{ background: #9ca3af; }}
.article .rank.bronze {{ background: #b45309; }}
.article a {{ color: var(--text); text-decoration: none; font-weight: 600; }}
.article a:hover {{ color: var(--accent); text-decoration: underline; }}
.article .meta {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.2rem; }}
.article .summary {{ font-size: 0.95rem; margin-top: 0.3rem; }}
.article-importance {{ font-size: 0.85rem; color: var(--muted); margin-top: 0.3rem; padding: 0.4rem 0.6rem; background: var(--surface2); border-radius: 6px; border-left: 3px solid var(--accent); }}
.cat-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }}
.cat-card {{ background: var(--surface2); border-radius: 8px; padding: 1rem; }}
.cat-card h3 {{ font-size: 1rem; margin-bottom: 0.5rem; }}
.cat-card .cat-summary {{ font-size: 0.9rem; color: var(--muted); }}
.action {{ padding: 0.4rem 0; }}
.action::before {{ content: "💡"; margin-right: 0.5rem; }}
.x-trend {{ padding: 0.8rem 0; border-bottom: 1px solid var(--surface2); }}
.x-trend:last-child {{ border-bottom: none; }}
.x-trend .topic {{ font-weight: 700; font-size: 1.05rem; }}
.x-trend .desc {{ margin-top: 0.3rem; font-size: 0.95rem; }}
.x-trend .tweet {{ background: var(--surface2); border-radius: 8px; padding: 0.6rem 0.8rem; margin-top: 0.5rem; font-size: 0.9rem; }}
.x-trend .tweet .author {{ color: var(--blue); font-weight: 600; }}
.x-trend .tweet .eng {{ color: var(--muted); font-size: 0.8rem; margin-top: 0.2rem; }}
.buzz {{ display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 0.8rem; margin-left: 0.5rem; }}
.buzz-high {{ background: #dc262633; color: var(--red); }}
.buzz-medium {{ background: #f59e0b33; color: var(--yellow); }}
.buzz-low {{ background: #1e40af33; color: var(--blue); }}
.history-chart {{ display: flex; align-items: flex-end; gap: 4px; height: 100px; margin-top: 1rem; }}
.history-bar {{ flex: 1; background: var(--accent); border-radius: 4px 4px 0 0; min-width: 24px; position: relative; }}
.history-bar .label {{ position: absolute; bottom: -20px; left: 50%; transform: translateX(-50%); font-size: 0.7rem; color: var(--muted); white-space: nowrap; }}
.empty {{ text-align: center; color: var(--muted); padding: 4rem 0; font-size: 1.1rem; }}
.diagram-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; margin-top: 0.5rem; }}
.diagram-item {{ display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; padding: 0.6rem 0.9rem; background: var(--surface2); border-radius: 8px; text-decoration: none; color: var(--text); font-size: 0.9rem; }}
.diagram-item:hover {{ background: #475569; }}
.diagram-item .slot-tag {{ display: inline-block; padding: 1px 8px; border-radius: 4px; background: var(--accent); color: #fff; font-size: 0.75rem; font-weight: 600; }}
.diagram-card {{ display: block; background: var(--surface2); border-radius: 10px; overflow: hidden; text-decoration: none; color: var(--text); transition: transform 0.15s; }}
.diagram-card:hover {{ transform: translateY(-2px); }}
.diagram-card img {{ width: 100%; height: auto; display: block; }}
.diagram-card .diagram-card-footer {{ display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; font-size: 0.85rem; }}
.diagram-card .slot-tag {{ display: inline-block; padding: 1px 8px; border-radius: 4px; background: var(--accent); color: #fff; font-size: 0.75rem; font-weight: 600; }}
@media (max-width: 640px) {{
  .container {{ padding: 1rem 0.75rem; }}
  header h1 {{ font-size: 1.3rem; }}
  .nav-links {{ gap: 0.4rem; }}
  .nav-link {{ padding: 0.35rem 0.7rem; font-size: 0.82rem; }}
  .card {{ padding: 1rem 0.9rem; margin-bottom: 1rem; border-radius: 10px; }}
  .card h2 {{ font-size: 1rem; }}
  .cat-grid {{ grid-template-columns: 1fr; }}
  .diagram-grid {{ grid-template-columns: 1fr; }}
  .article {{ padding: 0.6rem 0; }}
  .article .rank {{ width: 24px; height: 24px; line-height: 24px; font-size: 0.78rem; }}
  .article a {{ font-size: 0.92rem; }}
  .article .summary {{ font-size: 0.88rem; }}
  .x-trend .topic {{ font-size: 0.95rem; }}
  .x-trend .desc {{ font-size: 0.88rem; }}
  .x-trend .tweet {{ font-size: 0.83rem; padding: 0.5rem 0.6rem; }}
  .trend-evo .evo-item {{ gap: 0.2rem; }}
  .history-chart {{ height: 70px; }}
  .history-bar .label {{ font-size: 0.6rem; }}
}}
</style>
</head>
<body>
<nav class="topnav">
  <a class="nav-link active" href="index.html">📰 ニュース</a>
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
  <h1>🤖 AI News Dashboard</h1>
  <div class="updated">Last updated: {now_str}</div>
</header>
{body}
</div>
{STATUS_BANNER}
</body>
</html>"""


def _render_news_tabs(history: list[dict]) -> str:
    """日付・スロットのタブ切り替えで各便のニュースを表示"""
    if not history:
        return ""

    tabs_html = ""
    panels_html = ""
    slot_labels = {"morning": "朝便", "evening": "夕便"}

    # 実際に存在する日数（streak_days の上限に使う）
    actual_dates = len(set(
        (a.get("_display_date") or (a.get("run_time", ""))[:10])
        for a in history
    ))

    for i, a in enumerate(history):
        date = a.get("_display_date") or (a.get("run_time", ""))[:10]
        slot = a.get("_display_slot") or a.get("slot", "")
        slot_label = slot_labels.get(slot, slot)
        key = f"{date}-{slot}"
        active_class = " active" if i == 0 else ""
        is_today = i == 0
        today_mark = " <small>最新</small>" if is_today else ""

        tabs_html += f'<button class="news-tab{active_class}" data-panel="news-panel-{escape(key)}">{date[5:]} {slot_label}{today_mark}</button>\n'

        panel_content = _render_latest(a, max_streak=actual_dates)
        panels_html += f'<div class="news-panel{active_class}" id="news-panel-{escape(key)}">{panel_content}</div>\n'

    tab_css = """
<style>
.news-tabs { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 1rem; }
.news-tab {
  padding: 0.4rem 1rem; border-radius: 8px; border: 1px solid var(--surface2);
  background: var(--surface); color: var(--muted); cursor: pointer;
  font-size: 0.88rem; transition: all 0.15s;
}
.news-tab small { font-size: 0.75rem; color: var(--accent); margin-left: 0.3rem; }
.news-tab:hover { background: var(--surface2); color: var(--text); }
.news-tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.news-tab.active small { color: #fff; }
.news-panel { display: none; }
.news-panel.active { display: block; }
</style>
<script>
(function() {
  document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.news-tab').forEach(function(tab) {
      tab.addEventListener('click', function() {
        document.querySelectorAll('.news-tab').forEach(function(t) { t.classList.remove('active'); });
        document.querySelectorAll('.news-panel').forEach(function(p) { p.classList.remove('active'); });
        tab.classList.add('active');
        var panel = document.getElementById(tab.dataset.panel);
        if (panel) panel.classList.add('active');
      });
    });
  });
})();
</script>"""

    return (
        tab_css
        + f'<div class="news-tabs">\n{tabs_html}</div>\n'
        + panels_html
    )


def _render_latest(a: dict, max_streak: int = 0) -> str:
    display_slot = a.get("_display_slot") or a.get("slot")
    slot_label = "朝便" if display_slot == "morning" else "夕便"
    run_date = a.get("_display_date") or (a.get("run_time", ""))[:10]

    parts: list[str] = []

    # Trend summary + evolution
    trend = escape(a.get("trend_summary", ""))
    evo = a.get("trend_evolution", {})

    since_html = ""
    since_last = evo.get("since_last", "")
    if since_last:
        since_html = f'<div class="since-last">🔄 {escape(since_last)}</div>'

    evo_html = ""
    tracked = evo.get("tracked_topics", [])
    if tracked:
        status_icons = {
            "NEW": "⚡", "RISING": "📈", "SUSTAINED": "➡️",
            "FADING": "📉", "RESURFACED": "🔄",
        }
        evo_items: list[str] = []
        for t in tracked:
            status = t.get("status", "")
            icon = status_icons.get(status, "•")
            topic = escape(t.get("topic", ""))
            streak = t.get("streak_days", 0)
            # Gemini が過大に出力する場合があるので実データ日数でキャップ
            if max_streak and streak > max_streak:
                streak = max_streak
            streak_str = f'<span class="evo-streak">({streak}日目)</span>' if streak and streak > 1 else ""
            evolution = escape(t.get("evolution", ""))
            evo_desc = f'<div class="evo-desc">{evolution}</div>' if evolution else ""
            evo_items.append(
                f'<div class="evo-item">'
                f'<div class="evo-header">'
                f'<span class="status-badge st-{status}">{icon} {status}</span>'
                f'{streak_str}'
                f'</div>'
                f'<div class="evo-topic">{topic}</div>'
                f'{evo_desc}</div>'
            )
        evo_html = f'<div class="trend-evo">{"".join(evo_items)}</div>'

    parts.append(
        f'<div class="card">'
        f"<h2>📊 {run_date} {slot_label}</h2>"
        f'<div class="trend">{trend}</div>'
        f"{since_html}{evo_html}</div>"
    )

    # Xで話題
    x_trends = a.get("x_trends", [])
    if x_trends:
        trends_html: list[str] = []
        buzz_labels = {"high": "🔥 HIGH", "medium": "🔥 MEDIUM", "low": "LOW"}
        buzz_css = {"high": "buzz-high", "medium": "buzz-medium", "low": "buzz-low"}
        sentiment_icons = {"positive": "😊", "negative": "😟", "neutral": "😐", "mixed": "🤔"}

        for tr in x_trends:
            topic = escape(tr.get("topic", ""))
            desc = escape(tr.get("description", ""))
            bl = tr.get("buzz_level", "")
            sent = sentiment_icons.get(tr.get("sentiment", ""), "")
            buzz_tag = f'<span class="buzz {buzz_css.get(bl, "")}">{buzz_labels.get(bl, bl)}</span>'

            tweets_html = ""
            for tw in tr.get("representative_tweets", [])[:2]:
                tw_author = escape(tw.get("author", ""))
                tw_text = escape(tw.get("text", "")[:200])
                tw_url = escape(tw.get("url", ""))
                tw_likes = tw.get("likes", 0)
                tw_rts = tw.get("retweets", 0)
                author_link = f'<a href="{tw_url}" target="_blank" rel="noopener">{tw_author}</a>' if tw_url else tw_author
                eng_parts = []
                if tw_likes:
                    eng_parts.append(f"❤️ {tw_likes:,}")
                if tw_rts:
                    eng_parts.append(f"🔁 {tw_rts:,}")
                eng_html = f'<div class="eng">{" · ".join(eng_parts)}</div>' if eng_parts else ""
                tweets_html += f'<div class="tweet"><span class="author">{author_link}</span> {tw_text}{eng_html}</div>'

            trends_html.append(
                f'<div class="x-trend">'
                f'<span class="topic">{sent} {topic}</span>{buzz_tag}'
                f'<div class="desc">{desc}</div>'
                f'{tweets_html}</div>'
            )

        parts.append(f'<div class="card"><h2>🐦 Xで話題</h2>{"".join(trends_html)}</div>')

    # Top articles（全件・詳細表示）
    all_articles = a.get("top_articles", [])
    articles_html: list[str] = []
    for art in all_articles:
        rank = art.get("rank", 0)
        cls = {1: " gold", 2: " silver", 3: " bronze"}.get(rank, "")
        title = escape(art.get("title", ""))
        url = escape(art.get("url", ""))
        summary = escape(art.get("summary", ""))
        importance = escape(art.get("importance_reason", ""))
        cat = escape(art.get("category", ""))
        src = escape(art.get("source_label", ""))

        link = f'<a href="{url}" target="_blank" rel="noopener">{title}</a>' if url else title
        importance_html = f'<div class="article-importance">📌 {importance}</div>' if importance else ""
        articles_html.append(
            f'<div class="article">'
            f'<span class="rank{cls}">{rank}</span>{link}'
            f'<div class="meta">{cat} · {src}</div>'
            f'<div class="summary">{summary}</div>'
            f'{importance_html}</div>'
        )

    parts.append(f'<div class="card"><h2>⭐ 注目ポスト TOP {len(articles_html)}</h2>{"".join(articles_html)}</div>')

    # Category summaries
    cats_html: list[str] = []
    for cs in a.get("category_summaries", []):
        cat = escape(cs.get("category", ""))
        summary = escape(cs.get("summary", ""))
        count = cs.get("count", "")
        count_str = f" ({count}件)" if count else ""
        cats_html.append(
            f'<div class="cat-card"><h3>{cat}{count_str}</h3>'
            f'<div class="cat-summary">{summary}</div></div>'
        )
    if cats_html:
        parts.append(f'<div class="card"><h2>📁 カテゴリ別</h2><div class="cat-grid">{"".join(cats_html)}</div></div>')

    # Action items
    actions = a.get("action_items", [])
    if actions:
        acts = "".join(f'<div class="action">{escape(ai)}</div>' for ai in actions)
        parts.append(f'<div class="card"><h2>💡 ビジネスへの示唆</h2>{acts}</div>')

    return "\n".join(parts)


def _render_diagrams(diagrams: list[dict]) -> str:
    if not diagrams:
        return ""
    items: list[str] = []
    for d in diagrams:
        href = escape(d["rel_path"])
        date = escape(d["date"])
        slot = escape(d["slot"])
        if d.get("png_path"):
            png = escape(d["png_path"])
            items.append(
                f'<div class="diagram-item" onclick="openDiagram(\'{png}\',\'{href}\',\'{date} {slot}\')" style="cursor:pointer">'
                f'<span>{date}</span><span class="slot-tag">{slot}</span>'
                f'</div>'
            )
        else:
            items.append(
                f'<a class="diagram-item" href="{href}" target="_blank" rel="noopener">'
                f'<span>{date}</span><span class="slot-tag">{slot}</span></a>'
            )
    modal = '''
<div id="diagramModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.95);z-index:9999;">
  <div style="position:absolute;top:10px;left:0;right:0;display:flex;justify-content:space-between;align-items:center;padding:0 14px;z-index:10000;pointer-events:none;">
    <span id="diagramModalTitle" style="color:#fff;font-size:0.85rem;font-weight:600;text-shadow:0 1px 3px rgba(0,0,0,0.9);pointer-events:none;"></span>
    <button id="diagramCloseBtn" onclick="closeDiagramModal()" style="pointer-events:all;background:rgba(0,0,0,0.7);border:1px solid #888;color:#fff;padding:5px 12px;border-radius:6px;font-size:0.85rem;cursor:pointer;">✕ 閉じる</button>
  </div>
  <!-- 初期表示: 全体fit表示 -->
  <div id="diagramFitView" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding-top:44px;padding-bottom:8px;">
    <img id="diagramModalImg" src="" alt="" style="max-width:100%;max-height:100%;width:auto;height:auto;border-radius:6px;display:block;cursor:zoom-in;" onclick="enterZoomMode()" title="タップで拡大">
  </div>
  <!-- ズームモード: スクロール表示 -->
  <div id="diagramZoomView" style="display:none;position:absolute;inset:0;overflow:auto;-webkit-overflow-scrolling:touch;padding-top:44px;">
    <img id="diagramZoomImg" src="" alt="" style="width:900px;height:auto;display:block;border-radius:6px;cursor:zoom-out;" onclick="exitZoomMode()" title="タップで縮小">
  </div>
  <div style="position:absolute;bottom:10px;left:0;right:0;text-align:center;pointer-events:none;">
    <span id="diagramHint" style="color:#aaa;font-size:0.75rem;text-shadow:0 1px 2px rgba(0,0,0,0.9);">タップで拡大 / ピンチズーム可</span>
  </div>
</div>
<script>
function isMobile() {
  return /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) || window.innerWidth < 768;
}
function openDiagram(pngSrc, htmlHref, title) {
  if (isMobile()) {
    var img = document.getElementById('diagramModalImg');
    var zimg = document.getElementById('diagramZoomImg');
    img.src = pngSrc;
    zimg.src = pngSrc;
    document.getElementById('diagramModalTitle').textContent = title;
    document.getElementById('diagramFitView').style.display = 'flex';
    document.getElementById('diagramZoomView').style.display = 'none';
    document.getElementById('diagramHint').textContent = 'タップで拡大 / ピンチズーム可';
    document.getElementById('diagramModal').style.display = 'block';
    document.body.style.overflow = 'hidden';
  } else {
    window.open(htmlHref, '_blank', 'noopener');
  }
}
function enterZoomMode() {
  document.getElementById('diagramFitView').style.display = 'none';
  document.getElementById('diagramZoomView').style.display = 'block';
  document.getElementById('diagramHint').textContent = 'タップで全体表示に戻る';
}
function exitZoomMode() {
  document.getElementById('diagramZoomView').style.display = 'none';
  document.getElementById('diagramFitView').style.display = 'flex';
  document.getElementById('diagramHint').textContent = 'タップで拡大 / ピンチズーム可';
}
function closeDiagramModal() {
  document.getElementById('diagramModal').style.display = 'none';
  document.getElementById('diagramFitView').style.display = 'flex';
  document.getElementById('diagramZoomView').style.display = 'none';
  document.body.style.overflow = '';
}
</script>'''
    return (
        '<div class="card"><h2>🖼️ 図解版アーカイブ</h2>'
        f'<div class="diagram-grid">{"".join(items)}</div></div>'
        + modal
    )


def _render_history(history: list[dict]) -> str:
    if len(history) < 2:
        return ""

    # 同じ日付の朝・夕を合算する
    from collections import defaultdict as _dd
    daily: dict[str, int] = _dd(int)
    for h in history[:14]:
        date = h.get("_display_date") or (h.get("run_time", ""))[:10]
        daily[date] += h.get("item_count", 0)

    # 古い順に並べる
    counts = sorted(daily.items())

    if not counts:
        return ""

    max_n = max(n for _, n in counts) or 1
    bars: list[str] = []
    for date, n in counts:
        height = max(4, int(80 * n / max_n))
        short_date = date[5:]
        bars.append(
            f'<div class="history-bar" style="height:{height}px" title="{date}: {n}件">'
            f'<span class="label">{short_date}</span></div>'
        )

    return (
        '<div class="card"><h2>📈 収集推移</h2>'
        f'<div class="history-chart">{"".join(bars)}</div>'
        '<div style="height:24px"></div></div>'
    )


def _load_hn_today() -> list[dict]:
    """data/hn/ から直近2日分のデータを返す（最大50件）"""
    import glob as _glob
    hn_dir = data_dir("hn")
    if not os.path.isdir(hn_dir):
        return []
    files = sorted(_glob.glob(os.path.join(hn_dir, "*.jsonl")), reverse=True)[:2]
    items: list[dict] = []
    seen: set[str] = set()
    for f in files:
        try:
            for line in open(f, encoding="utf-8"):
                d = json.loads(line)
                url = d.get("url") or d.get("hn_item_url") or ""
                if url and url in seen:
                    continue
                seen.add(url)
                items.append(d)
        except (json.JSONDecodeError, OSError):
            continue
    items = items[:50]
    _translate_hn_missing(items)
    return items


def _translate_hn_missing(items: list[dict]) -> None:
    """title_ja がない item を Gemini でまとめて翻訳（in-place）"""
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        return
    untranslated = [(i, d) for i, d in enumerate(items) if not d.get("title_ja")]
    if not untranslated:
        return
    try:
        from google import genai as _genai
        client = _genai.Client(api_key=gemini_key)
    except Exception as e:
        logger.warning("Gemini import failed — skipping translation: %s", e)
        return
    lines = [f"[{i}] {d.get('title', '')}" for i, d in untranslated]
    prompt = (
        "以下の英語タイトルを自然な日本語に翻訳してください。\n"
        "[番号] 日本語タイトル の形式で返してください。余計な説明は不要です。\n\n"
        + "\n".join(lines)
    )
    try:
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        import re as _re
        for m in _re.finditer(r'\[(\d+)\]\s*(.+)', resp.text or ""):
            idx = int(m.group(1))
            if 0 <= idx < len(items):
                items[idx]["title_ja"] = m.group(2).strip()
    except Exception as e:
        logger.warning("HN translation failed: %s", e)


def _render_hn_section(items: list[dict]) -> str:
    if not items:
        return ""
    hn_items = [i for i in items if i.get("source_name") == "HackerNews"]
    arxiv_items = [i for i in items if i.get("source_name", "").startswith("arxiv")]

    def _item_html(d: dict) -> str:
        title = d.get("title_ja") or d.get("title") or ""
        url = d.get("url") or d.get("hn_item_url") or "#"
        hn_url = d.get("hn_item_url") or ""
        score = (d.get("engagement") or {}).get("score", 0)
        comments = (d.get("engagement") or {}).get("comments", 0)
        src = d.get("source_name") or ""
        badge = f'<span class="badge badge-score">{score}pt</span>' if score else ""
        badge += f'<span class="badge badge-comments">{comments}💬</span>' if comments else ""
        cat = src if src.startswith("arxiv") else ""
        cat_badge = f'<span class="badge badge-cat">{cat}</span>' if cat else ""
        hn_link = f' <a class="hn-link" href="{hn_url}" target="_blank" rel="noopener">HN↗</a>' if hn_url and hn_url != url else ""
        return (
            f'<div class="article">'
            f'<div><a href="{url}" target="_blank" rel="noopener">{title}</a>{hn_link}</div>'
            f'<div class="meta">{badge}{cat_badge}</div>'
            f'</div>'
        )

    hn_html = "".join(_item_html(d) for d in hn_items[:15]) if hn_items else '<p class="empty" style="padding:1rem 0">データなし</p>'
    arxiv_html = "".join(_item_html(d) for d in arxiv_items[:15]) if arxiv_items else '<p class="empty" style="padding:1rem 0">データなし</p>'

    return f"""<div class="card">
<h2>📡 HN / arxiv（英語一次情報）</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem">
<div>
<div style="font-size:0.85rem;color:var(--muted);margin-bottom:0.5rem;font-weight:600;">🔶 HackerNews</div>
{hn_html}
</div>
<div>
<div style="font-size:0.85rem;color:var(--muted);margin-bottom:0.5rem;font-weight:600;">📄 arxiv</div>
{arxiv_html}
</div>
</div>
</div>"""


# ━━━━━━━━━━━━━━━━ 施策ページ (strategy.html) ━━━━━━━━━━━━━━━━
# 既存の generate_dashboard() / index.html には一切手を加えない
# この関数のみが docs/strategy.html を生成する


def generate_strategy_page(output_path: str) -> None:
    """data/analysis/ の全履歴 strategy データから docs/strategy.html を生成"""
    analyses = _load_recent_analyses(days=30)
    latest = analyses[0] if analyses else None
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    html = _render_strategy_html(latest, analyses)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, output_path)
    logger.info("Strategy page written → %s", output_path)


def _render_strategy_html(latest: dict | None, all_analyses: list[dict] | None = None) -> str:
    JST = timezone(timedelta(hours=9))
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    STATUS_BANNER = STATUS_BANNER_HTML
    all_analyses = all_analyses or []

    if not latest:
        body = '<p class="empty">まだデータがありません。初回実行をお待ちください。</p>'
        heading = "AI 施策提案"
        selector_html = ""
    else:
        display_date = latest.get("_display_date") or (latest.get("run_time", ""))[:10]
        display_slot = latest.get("_display_slot") or latest.get("slot", "")
        heading = "AI 施策提案"
        body = ""
        selector_html = _render_strategy_selector(all_analyses, display_date, display_slot)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 施策提案</title>
<style>
:root {{
  --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
  --text: #e2e8f0; --muted: #94a3b8; --accent: #818cf8;
  --green: #34d399; --red: #f87171; --yellow: #fbbf24; --blue: #60a5fa;
  --purple: #c084fc; --orange: #fb923c;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding-top: 48px; }}
.topnav {{ position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: #0f172aee; backdrop-filter: blur(8px); border-bottom: 1px solid var(--surface2); display: flex; gap: 0.4rem; justify-content: center; flex-wrap: wrap; padding: 6px 12px; }}
.nav-link {{ display: inline-block; padding: 4px 12px; background: var(--surface2); border-radius: 6px; color: var(--blue); text-decoration: none; font-size: 0.82rem; white-space: nowrap; }}
.nav-link:hover {{ background: #475569; color: #fff; }}
.nav-link.active {{ background: var(--accent); color: #fff; }}
.container {{ max-width: 960px; margin: 0 auto; padding: 1.5rem 1rem 2rem; }}
header {{ text-align: center; margin-bottom: 2rem; }}
header h1 {{ font-size: 1.8rem; color: var(--accent); }}
header .updated {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.3rem; }}
.selector-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.6rem; margin-top: 0.5rem; }}
.selector-item {{ display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; padding: 0.55rem 0.9rem; background: var(--surface2); border-radius: 8px; text-decoration: none; color: var(--text); font-size: 0.9rem; cursor: pointer; }}
.selector-item:hover {{ background: #475569; }}
.selector-item.active {{ background: var(--accent); color: #fff; }}
.slot-tag {{ display: inline-block; padding: 1px 8px; border-radius: 4px; background: #ffffff22; font-size: 0.75rem; font-weight: 600; }}
.selector-item.active .slot-tag {{ background: #ffffff33; }}
.section-body {{ display: none; }}
.section-body.active {{ display: block; }}
.card {{ background: var(--surface); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }}
.card h2 {{ font-size: 1.2rem; color: var(--accent); margin-bottom: 1rem; border-bottom: 1px solid var(--surface2); padding-bottom: 0.5rem; }}
.idea-item {{ padding: 1rem; background: var(--surface2); border-radius: 8px; margin-bottom: 0.8rem; }}
.idea-item:last-child {{ margin-bottom: 0; }}
.idea-title {{ font-size: 1.05rem; font-weight: 700; margin-bottom: 0.5rem; }}
.idea-meta {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.5rem; }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 0.78rem; font-weight: 600; }}
.badge-high {{ background: #dc262633; color: var(--red); }}
.badge-medium {{ background: #f59e0b33; color: var(--yellow); }}
.badge-low {{ background: #1e40af33; color: var(--blue); }}
.badge-now {{ background: #dc262633; color: var(--red); }}
.badge-week {{ background: #f59e0b33; color: var(--yellow); }}
.badge-month {{ background: #1e40af33; color: var(--blue); }}
.idea-row {{ margin-top: 0.4rem; font-size: 0.92rem; }}
.idea-row .label {{ color: var(--muted); font-size: 0.82rem; margin-right: 0.3rem; }}
.draft-box {{ background: #0f172a; border: 1px solid var(--surface2); border-radius: 6px; padding: 0.8rem 1rem; margin-top: 0.5rem; font-size: 0.92rem; white-space: pre-wrap; word-break: break-word; }}
.source-links {{ margin-top: 0.7rem; padding-top: 0.6rem; border-top: 1px dashed var(--surface2); }}
.source-links .source-label {{ display: block; font-size: 0.78rem; color: var(--muted); margin-bottom: 0.3rem; }}
.source-link {{ display: flex; align-items: baseline; gap: 0.4rem; padding: 0.3rem 0; color: var(--blue); text-decoration: none; font-size: 0.83rem; line-height: 1.4; }}
.source-link:hover {{ color: var(--accent); }}
.source-icon {{ flex-shrink: 0; }}
.source-from {{ color: var(--muted); font-size: 0.78rem; margin-left: auto; white-space: nowrap; }}
.forecast-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 0.5rem; }}
@media (max-width: 600px) {{ .forecast-grid {{ grid-template-columns: 1fr; }} }}
.forecast-block h3 {{ font-size: 0.95rem; color: var(--muted); margin-bottom: 0.5rem; }}
.forecast-block ul {{ padding-left: 1.2rem; }}
.forecast-block li {{ font-size: 0.92rem; margin-bottom: 0.3rem; }}
.watch li {{ color: var(--green); }}
.fading li {{ color: var(--muted); text-decoration: line-through; }}
.next-big {{ background: var(--surface2); border-radius: 8px; padding: 0.8rem 1rem; margin-bottom: 1rem; font-size: 1rem; }}
.next-big .label {{ color: var(--yellow); font-weight: 700; margin-right: 0.5rem; }}
.trend-detail-section {{ margin: 1rem 0; }}
.trend-subhead {{ font-size: 0.95rem; color: var(--muted); margin-bottom: 0.8rem; padding-bottom: 0.4rem; border-bottom: 1px solid var(--surface2); }}
.trend-detail {{ padding: 0.9rem; background: var(--surface2); border-radius: 8px; margin-bottom: 0.7rem; }}
.trend-detail:last-child {{ margin-bottom: 0; }}
.trend-detail-header {{ display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem; flex-wrap: wrap; }}
.trend-topic {{ font-weight: 700; font-size: 1rem; }}
.trend-desc {{ font-size: 0.9rem; color: var(--muted); margin-bottom: 0.5rem; line-height: 1.6; }}
.trend-tweet {{ background: #0f172a; border-radius: 6px; padding: 0.6rem 0.8rem; margin-top: 0.4rem; }}
.tw-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem; }}
.tw-author {{ color: var(--blue); font-weight: 600; font-size: 0.85rem; text-decoration: none; }}
.tw-author:hover {{ color: var(--accent); }}
.tw-eng {{ color: var(--muted); font-size: 0.8rem; }}
.tw-body {{ font-size: 0.88rem; color: var(--text); line-height: 1.5; }}
.empty {{ text-align: center; color: var(--muted); padding: 4rem 0; font-size: 1.1rem; }}
@media (max-width: 640px) {{
  .container {{ padding: 1rem 0.75rem; }}
  header h1 {{ font-size: 1.3rem; }}
  .nav-links {{ gap: 0.4rem; }}
  .nav-link {{ padding: 0.35rem 0.7rem; font-size: 0.82rem; }}
  .card {{ padding: 1rem 0.9rem; margin-bottom: 1rem; border-radius: 10px; }}
  .card h2 {{ font-size: 1rem; }}
  .selector-grid {{ grid-template-columns: 1fr; }}
  .idea-item {{ padding: 0.8rem; }}
  .idea-title {{ font-size: 0.97rem; }}
  .idea-row {{ font-size: 0.86rem; }}
  .draft-box {{ font-size: 0.86rem; padding: 0.6rem 0.8rem; }}
  .source-link {{ font-size: 0.8rem; }}
  .tw-body {{ font-size: 0.84rem; }}
  .trend-detail {{ padding: 0.7rem; }}
  .trend-topic {{ font-size: 0.93rem; }}
  .trend-desc {{ font-size: 0.85rem; }}
}}
</style>
</head>
<body>
<nav class="topnav">
  <a class="nav-link" href="index.html">📰 ニュース</a>
  <a class="nav-link active" href="strategy.html">🎯 施策提案</a>
  <a class="nav-link" href="buzz.html">🔥 バズりランキング</a>
  <a class="nav-link" href="money.html">🎬 マネタイズ</a>
  <a class="nav-link" href="sns_success.html">🧠 SNS成功者</a>
  <a class="nav-link" href="post_generator.html">✍️ 投稿ストック</a>
  <a class="nav-link" href="tools.html">🔧 ツール追跡</a>
  <a class="nav-link" href="reviews.html">📋 使ってみた</a>
</nav>
<div class="container">
<header>
  <h1>🎯 AI 施策提案</h1>
  <div class="updated">Last updated: {now_str}</div>
</header>
{selector_html}
<div id="strategy-content">
{body}
</div>
</div>
<script>
document.querySelectorAll('.selector-item').forEach(function(el) {{
  el.addEventListener('click', function(e) {{
    e.preventDefault();
    var key = this.dataset.key;
    document.querySelectorAll('.selector-item').forEach(function(x) {{ x.classList.remove('active'); }});
    this.classList.add('active');
    document.querySelectorAll('.section-body').forEach(function(x) {{ x.classList.remove('active'); }});
    var target = document.getElementById('section-' + key);
    if (target) target.classList.add('active');
  }});
}});
</script>
{STATUS_BANNER}
</body>
</html>"""


def _render_strategy_selector(analyses: list[dict], active_date: str, active_slot: str) -> str:
    """日付・スロット選択グリッドと全セクションのHTMLを生成"""
    if not analyses:
        return ""

    items_html: list[str] = []
    sections_html: list[str] = []

    for a in analyses:
        date = a.get("_display_date") or (a.get("run_time", ""))[:10]
        slot = a.get("_display_slot") or a.get("slot", "")
        slot_label = "朝便" if slot == "morning" else "夕便"
        key = f"{date}-{slot}"
        is_active = (date == active_date and slot == active_slot)
        active_cls = " active" if is_active else ""

        items_html.append(
            f'<a class="selector-item{active_cls}" data-key="{escape(key)}" href="#">'
            f'<span>{escape(date)}</span>'
            f'<span class="slot-tag">{slot_label}</span></a>'
        )

        strategy = a.get("strategy") or {}
        section_active = " active" if is_active else ""
        sections_html.append(
            f'<div class="section-body{section_active}" id="section-{escape(key)}">'
            f'{_render_strategy_body(strategy, a)}'
            f'</div>'
        )

    selector = (
        '<div class="card"><h2>📅 日付を選ぶ</h2>'
        f'<div class="selector-grid">{"".join(items_html)}</div></div>'
    )
    return selector + "\n" + "\n".join(sections_html)


def _source_links_html(top_articles: list[dict], count: int = 3) -> str:
    """top_articles の上位N件を根拠リンクとして返す"""
    if not top_articles:
        return ""
    links = []
    for art in top_articles[:count]:
        url = art.get("url", "")
        title = art.get("title", "")
        src = art.get("source_label", "")
        if url:
            short_title = title[:40] + "…" if len(title) > 40 else title
            links.append(
                f'<a href="{escape(url)}" target="_blank" rel="noopener" class="source-link">'
                f'<span class="source-icon">🔗</span>{escape(short_title)}'
                f'<span class="source-from">{escape(src)}</span></a>'
            )
    if not links:
        return ""
    return f'<div class="source-links"><span class="source-label">根拠ポスト</span>{"".join(links)}</div>'


def _render_strategy_body(strategy: dict, analysis: dict) -> str:
    if not strategy:
        return '<p class="empty">施策データがありません。次回の収集後に表示されます。</p>'

    top_articles = analysis.get("top_articles", [])
    parts: list[str] = []

    # ── YouTube企画案 ──────────────────────────────────────────────
    youtube_ideas = strategy.get("youtube_ideas", [])
    if youtube_ideas:
        items_html: list[str] = []
        for i, idea in enumerate(youtube_ideas):
            offset = i * 3
            related = top_articles[offset:offset + 3] or top_articles[:3]
            items_html.append(
                f'<div class="idea-item">'
                f'<div class="idea-title">{escape(idea.get("title", ""))}</div>'
                f'<div class="idea-row"><span class="label">フック</span>{escape(idea.get("hook", ""))}</div>'
                f'<div class="idea-row"><span class="label">なぜ今？</span>{escape(idea.get("reason", ""))}</div>'
                f'<div class="idea-row"><span class="label">差別化</span>{escape(idea.get("angle", ""))}</div>'
                f'{_source_links_html(related)}'
                f'</div>'
            )
        parts.append(f'<div class="card"><h2>🎬 YouTube企画案</h2>{"".join(items_html)}</div>')

    # ── X投稿ネタ（5件表示）──────────────────────────────────────
    x_ideas = strategy.get("x_post_ideas", [])[:5]
    if x_ideas:
        items_html = []
        for i, idea in enumerate(x_ideas):
            draft = escape(idea.get("draft", ""))
            offset = i * 3
            related = top_articles[offset:offset + 3] or top_articles[:3]
            items_html.append(
                f'<div class="idea-item">'
                f'<div class="idea-title">{escape(idea.get("theme", ""))}</div>'
                f'<div class="draft-box">{draft}</div>'
                f'{_source_links_html(related)}'
                f'</div>'
            )
        parts.append(f'<div class="card"><h2>🐦 X投稿ネタ</h2>{"".join(items_html)}</div>')

    # ── ビジネス活用 ───────────────────────────────────────────────
    biz_items = strategy.get("business_insights", [])
    if biz_items:
        items_html = []
        for i, item in enumerate(biz_items):
            offset = i * 3
            related = top_articles[offset:offset + 3] or top_articles[:3]
            items_html.append(
                f'<div class="idea-item">'
                f'<div class="idea-title">{escape(item.get("insight", ""))}</div>'
                f'<div class="idea-row"><span class="label">アクション</span>{escape(item.get("action", ""))}</div>'
                f'{_source_links_html(related)}'
                f'</div>'
            )
        parts.append(f'<div class="card"><h2>💼 ビジネス活用</h2>{"".join(items_html)}</div>')

    # ── トレンド予測 ───────────────────────────────────────────────
    forecast = strategy.get("trend_forecast", {})
    x_trends = analysis.get("x_trends", [])
    if forecast or x_trends:
        trend_parts: list[str] = []

        # 次に来るテーマ
        next_big = escape(forecast.get("next_big_thing", "")) if forecast else ""
        if next_big:
            trend_parts.append(f'<div class="next-big"><span class="label">🔮 次に来るテーマ</span>{next_big}</div>')

        # 今ホットな話題（x_trendsから深掘り）
        if x_trends:
            buzz_labels = {"high": "🔥 急上昇", "medium": "📈 注目", "low": "💬 話題"}
            buzz_css = {"high": "buzz-high", "medium": "buzz-medium", "low": "buzz-low"}
            sentiment_icons = {"positive": "😊", "negative": "😟", "neutral": "😐", "mixed": "🤔"}
            xt_html: list[str] = []
            for tr in x_trends:
                topic = escape(tr.get("topic", ""))
                desc = escape(tr.get("description", ""))
                bl = tr.get("buzz_level", "medium")
                sent = sentiment_icons.get(tr.get("sentiment", ""), "")
                buzz_tag = f'<span class="buzz {buzz_css.get(bl, "buzz-medium")}">{buzz_labels.get(bl, bl)}</span>'

                tw_html = ""
                for tw in tr.get("representative_tweets", [])[:1]:
                    tw_url = escape(tw.get("url", ""))
                    tw_text = escape(tw.get("text", "")[:180])
                    tw_author = escape(tw.get("author", ""))
                    tw_likes = tw.get("likes", 0)
                    tw_rts = tw.get("retweets", 0)
                    eng_parts = []
                    if tw_likes:
                        eng_parts.append(f"❤️ {tw_likes:,}")
                    if tw_rts:
                        eng_parts.append(f"🔁 {tw_rts:,}")
                    eng = f'<span class="tw-eng">{" · ".join(eng_parts)}</span>' if eng_parts else ""
                    author_link = f'<a href="{tw_url}" target="_blank" rel="noopener" class="tw-author">{tw_author}</a>' if tw_url else f'<span class="tw-author">{tw_author}</span>'
                    tw_html = (
                        f'<div class="trend-tweet">'
                        f'<div class="tw-header">{author_link}{eng}</div>'
                        f'<div class="tw-body">{tw_text}</div>'
                        f'</div>'
                    )
                xt_html.append(
                    f'<div class="trend-detail">'
                    f'<div class="trend-detail-header">'
                    f'<span class="trend-topic">{sent} {topic}</span>{buzz_tag}'
                    f'</div>'
                    f'<div class="trend-desc">{desc}</div>'
                    f'{tw_html}'
                    f'</div>'
                )
            trend_parts.append(
                f'<div class="trend-detail-section">'
                f'<h3 class="trend-subhead">📡 今日の注目トピック詳細</h3>'
                f'{"".join(xt_html)}'
                f'</div>'
            )

        # 要注目 / 下火
        if forecast:
            watch = forecast.get("watch_topics", [])
            fading = forecast.get("fading_topics", [])
            watch_html = "".join(f"<li>{escape(t)}</li>" for t in watch)
            fading_html = "".join(f"<li>{escape(t)}</li>" for t in fading)
            trend_parts.append(
                f'<div class="forecast-grid">'
                f'<div class="forecast-block watch"><h3>👀 これから来る</h3><ul>{watch_html}</ul></div>'
                f'<div class="forecast-block fading"><h3>📉 下火になりそう</h3><ul>{fading_html}</ul></div>'
                f'</div>'
            )

        parts.append(
            f'<div class="card"><h2>🔭 トレンド予測</h2>'
            f'{"".join(trend_parts)}'
            f'</div>'
        )

    return "\n".join(parts) if parts else '<p class="empty">施策データがありません。</p>'



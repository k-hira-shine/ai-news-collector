"""GitHub Pages 用 HTML ダッシュボード生成 (docs/index.html)"""

import json
import logging
import os
from datetime import datetime, timezone
from glob import glob
from html import escape

from utils import data_dir

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
    """docs/diagrams/*.html を新しい順に返す"""
    if not os.path.isdir(diagrams_dir):
        return []
    files = sorted(glob(os.path.join(diagrams_dir, "*.html")), reverse=True)
    results: list[dict] = []
    for f in files[:limit]:
        name = os.path.basename(f)
        base = name.rsplit(".html", 1)[0]
        date_part = base[:10] if len(base) >= 10 else base
        slot_part = base[11:] if len(base) > 11 else ""
        slot_label = {"morning": "朝便", "evening": "夕便"}.get(slot_part, slot_part)
        results.append({
            "name": name,
            "date": date_part,
            "slot": slot_label,
            "rel_path": f"diagrams/{name}",
        })
    return results


def _load_recent_analyses(days: int = 7) -> list[dict]:
    analysis_dir = data_dir("analysis")
    if not os.path.isdir(analysis_dir):
        return []
    files = sorted(glob(os.path.join(analysis_dir, "*.json")), reverse=True)
    results: list[dict] = []
    for f in files[: days * 2]:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                results.append(json.load(fh))
        except (json.JSONDecodeError, OSError):
            continue
    return results


def _render(latest: dict | None, history: list[dict], diagrams: list[dict] | None = None) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    diagrams = diagrams or []
    if not latest:
        body = '<p class="empty">まだ分析データがありません。初回実行をお待ちください。</p>'
    else:
        body = _render_diagrams(diagrams) + _render_latest(latest) + _render_history(history)

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
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
.container {{ max-width: 960px; margin: 0 auto; padding: 2rem 1rem; }}
header {{ text-align: center; margin-bottom: 2rem; }}
header h1 {{ font-size: 1.8rem; color: var(--accent); }}
header .updated {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.3rem; }}
.card {{ background: var(--surface); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }}
.card h2 {{ font-size: 1.2rem; color: var(--accent); margin-bottom: 1rem; border-bottom: 1px solid var(--surface2); padding-bottom: 0.5rem; }}
.trend {{ font-size: 1rem; }}
.since-last {{ margin-top: 1rem; padding: 0.8rem; background: var(--surface2); border-radius: 8px; font-size: 0.95rem; }}
.trend-evo {{ margin-top: 1rem; }}
.trend-evo .evo-item {{ padding: 0.5rem 0; border-bottom: 1px solid var(--surface2); display: flex; align-items: baseline; gap: 0.5rem; }}
.trend-evo .evo-item:last-child {{ border-bottom: none; }}
.trend-evo .status-badge {{ display: inline-block; padding: 1px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600; white-space: nowrap; }}
.trend-evo .st-NEW {{ background: #16a34a33; color: var(--green); }}
.trend-evo .st-RISING {{ background: #dc262633; color: var(--red); }}
.trend-evo .st-SUSTAINED {{ background: #1e40af33; color: var(--blue); }}
.trend-evo .st-FADING {{ background: #6b728033; color: var(--muted); }}
.trend-evo .st-RESURFACED {{ background: #f59e0b33; color: var(--yellow); }}
.trend-evo .evo-topic {{ font-weight: 600; }}
.trend-evo .evo-streak {{ color: var(--muted); font-size: 0.85rem; }}
.trend-evo .evo-desc {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.2rem; }}
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
.diagram-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.75rem; margin-top: 0.5rem; }}
.diagram-item {{ display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; padding: 0.6rem 0.9rem; background: var(--surface2); border-radius: 8px; text-decoration: none; color: var(--text); font-size: 0.9rem; }}
.diagram-item:hover {{ background: #475569; }}
.diagram-item .slot-tag {{ display: inline-block; padding: 1px 8px; border-radius: 4px; background: var(--accent); color: #fff; font-size: 0.75rem; font-weight: 600; }}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>🤖 AI News Dashboard</h1>
  <div class="updated">Last updated: {now_str}</div>
</header>
{body}
</div>
</body>
</html>"""


def _render_latest(a: dict) -> str:
    slot_label = "朝便" if a.get("slot") == "morning" else "夕便"
    run_date = (a.get("run_time", ""))[:10]

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
            streak_str = f'<span class="evo-streak">({streak}日目)</span>' if streak and streak > 1 else ""
            evolution = escape(t.get("evolution", ""))
            evo_desc = f'<div class="evo-desc">{evolution}</div>' if evolution else ""
            evo_items.append(
                f'<div class="evo-item">'
                f'<span class="status-badge st-{status}">{icon} {status}</span>'
                f'<span class="evo-topic">{topic}</span>{streak_str}'
                f'{evo_desc}</div>'
            )
        evo_html = f'<div class="trend-evo">{"".join(evo_items)}</div>'

    parts.append(
        f'<div class="card">'
        f"<h2>📊 {run_date} {slot_label}</h2>"
        f'<div class="trend">{trend}</div>'
        f"{since_html}{evo_html}</div>"
    )

    # X Trends (TOP 記事の前に配置)
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
                author_link = f'<a href="{tw_url}" target="_blank" rel="noopener">@{tw_author}</a>' if tw_url else f"@{tw_author}"
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

        parts.append(f'<div class="card"><h2>🐦 X/Twitter で話題</h2>{"".join(trends_html)}</div>')

    # Top articles
    articles_html: list[str] = []
    for art in a.get("top_articles", [])[:10]:
        rank = art.get("rank", 0)
        cls = {1: " gold", 2: " silver", 3: " bronze"}.get(rank, "")
        title = escape(art.get("title", ""))
        url = escape(art.get("url", ""))
        summary = escape(art.get("summary", ""))
        cat = escape(art.get("category", ""))
        src = escape(art.get("source_label", ""))

        link = f'<a href="{url}" target="_blank" rel="noopener">{title}</a>' if url else title
        articles_html.append(
            f'<div class="article">'
            f'<span class="rank{cls}">{rank}</span>{link}'
            f'<div class="meta">{cat} · {src}</div>'
            f'<div class="summary">{summary}</div></div>'
        )

    parts.append(f'<div class="card"><h2>⭐ TOP {len(articles_html)}</h2>{"".join(articles_html)}</div>')

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
        items.append(
            f'<a class="diagram-item" href="{href}" target="_blank" rel="noopener">'
            f'<span>{date}</span><span class="slot-tag">{slot}</span></a>'
        )
    return (
        '<div class="card"><h2>🖼️ 図解版アーカイブ</h2>'
        f'<div class="diagram-grid">{"".join(items)}</div></div>'
    )


def _render_history(history: list[dict]) -> str:
    if len(history) < 2:
        return ""

    counts = []
    for h in reversed(history[:14]):
        date = (h.get("run_time", ""))[:10]
        n = h.get("item_count", 0)
        counts.append((date, n))

    if not counts:
        return ""

    max_n = max(c[1] for c in counts) or 1
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

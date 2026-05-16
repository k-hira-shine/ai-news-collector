"""トップページ（home.html）生成モジュール"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from glob import glob
from html import escape
from zoneinfo import ZoneInfo

logger = logging.getLogger("ai-news.build_home")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_PATH = os.path.join(DOCS_DIR, "home.html")
JST = ZoneInfo("Asia/Tokyo")

PAGES = [
    {"file": "index.html",          "title": "📰 ニュース",        "desc": "RSS・X・HNから収集したAI関連ニュースを毎日自動更新",                    "color": "#38bdf8"},
    {"file": "tools.html",          "title": "🔧 ツール追跡",      "desc": "AIツール・機能リリースをリアルタイムで追跡。日付・ファミリー・影響度でフィルター可能", "color": "#a78bfa"},
    {"file": "reviews.html",        "title": "📋 使ってみた",      "desc": "試したAIツールの所感・評価を記録。履歴管理・編集機能付き",               "color": "#34d399"},
    {"file": "buzz.html",           "title": "🔥 バズりランキング", "desc": "いいね・RT数でランキング化。バズったAI情報を見逃さない",                  "color": "#fb923c"},
    {"file": "strategy.html",       "title": "🎯 施策提案",        "desc": "収集ニュースからYouTube施策をAIが自動提案",                            "color": "#f472b6"},
    {"file": "money.html",          "title": "🎬 マネタイズ",      "desc": "収益化・マネタイズ関連情報を自動収集・整理",                              "color": "#fbbf24"},
    {"file": "sns_success.html",    "title": "🧠 SNS成功者",       "desc": "SNSで成功した人の思考法・習慣を自動収集",                               "color": "#60a5fa"},
    {"file": "post_generator.html", "title": "✍️ 投稿ストック",    "desc": "AI生成の投稿案をストック。すぐ使えるコンテンツを常備",                    "color": "#4ade80"},
]


# ── データ取得ヘルパー ──────────────────────────────

def _get_last_updated(html_file: str) -> str:
    path = os.path.join(DOCS_DIR, html_file)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read(4000)
        m = re.search(r"Last updated:\s*([\d\-]+ [\d:]+\s*JST)", content)
        return m.group(1).strip() if m else ""
    except Exception:
        return ""


def _get_git_log(n: int = 8) -> list[dict]:
    try:
        result = subprocess.run(
            ["git", "log", f"-{n * 3}", "--format=%H\t%ai\t%s"],
            capture_output=True, text=True, cwd=BASE_DIR,
        )
        logs = []
        skip_prefixes = ("build:", "Merge", "data:")
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t", 2)
            if len(parts) < 3:
                continue
            sha, date_str, subject = parts
            if any(subject.startswith(p) for p in skip_prefixes):
                continue
            dt = datetime.fromisoformat(date_str).astimezone(JST)
            logs.append({"sha": sha[:7], "date": dt.strftime("%m/%d %H:%M"), "subject": subject})
            if len(logs) >= n:
                break
        return logs
    except Exception:
        return []


def _get_latest_news() -> list[dict]:
    """最新分析から top_articles を最大5件返す"""
    files = sorted(glob(os.path.join(DATA_DIR, "analysis", "*.json")), reverse=True)
    for fpath in files[:3]:
        try:
            with open(fpath, encoding="utf-8") as f:
                d = json.load(f)
            articles = d.get("top_articles") or []
            trend = d.get("trend_summary") or ""
            if articles:
                return {"articles": articles[:5], "trend": trend, "slot": d.get("slot", ""), "run_time": d.get("run_time", "")}
        except Exception:
            continue
    return {"articles": [], "trend": "", "slot": "", "run_time": ""}


def _get_latest_tools() -> list[dict]:
    """tools/ から impact:high の最新3件を返す"""
    files = sorted(glob(os.path.join(DATA_DIR, "tools", "*.jsonl")), reverse=True)
    items = []
    for fpath in files[:3]:
        try:
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("tool_name") and obj.get("impact") in ("high", "medium"):
                        items.append(obj)
        except Exception:
            continue
        if len(items) >= 3:
            break
    # impact high 優先でソート
    order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda x: (order.get(x.get("impact", "low"), 2), -(x.get("priority_score") or 0)))
    return items[:3]


def _get_latest_buzz() -> list[dict]:
    """buzz.json から最新3件を返す"""
    path = os.path.join(DATA_DIR, "buzz.json")
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        accounts = d.get("accounts") or []
        posts = []
        for acc in accounts:
            for post in (acc.get("top_posts") or [])[:1]:
                posts.append({
                    "author": acc.get("handle") or acc.get("name") or "",
                    "content": post.get("content") or post.get("text") or "",
                    "url": post.get("url") or "",
                    "likes": post.get("likes") or post.get("like_count") or 0,
                })
        posts.sort(key=lambda x: x["likes"], reverse=True)
        return posts[:3]
    except Exception:
        return []


def _get_latest_diagram() -> dict:
    """最新の図解HTMLパスを返す"""
    files = sorted(glob(os.path.join(DOCS_DIR, "diagrams", "*.html")), reverse=True)
    if not files:
        return {}
    latest = os.path.basename(files[0])
    return {"href": f"diagrams/{latest}", "label": latest.replace(".html", "")}


# ── HTML生成 ────────────────────────────────────────

def build_home_page(output_path: str = OUTPUT_PATH) -> None:
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    git_logs = _get_git_log()
    news_data = _get_latest_news()
    tools = _get_latest_tools()
    buzz = _get_latest_buzz()
    diagram = _get_latest_diagram()

    # ── 機能カード ──
    cards_html = ""
    for page in PAGES:
        updated = _get_last_updated(page["file"])
        color = page["color"]
        extra = ""
        # ニュースカードに図解リンクを埋め込む
        if page["file"] == "index.html" and diagram:
            extra = f'<span class="page-diagram-link">📊 最新図解: <a href="{diagram["href"]}" onclick="event.stopPropagation()">{escape(diagram["label"])}</a></span>'
        updated_html = f'<span class="page-updated">{escape(updated)}</span>' if updated else ""
        cards_html += f"""<a href="{page['file']}" class="page-card" style="--card-color:{color}">
  <div class="page-card-title">{escape(page['title'])}</div>
  <div class="page-card-desc">{escape(page['desc'])}</div>
  {extra}
  {updated_html}
</a>
"""

    # ── 最新ニュース ──
    trend_html = ""
    if news_data["trend"]:
        slot_label = {"morning": "朝", "evening": "夜"}.get(news_data["slot"], news_data["slot"])
        run_time = news_data["run_time"][:10] if news_data["run_time"] else ""
        trend_html = f'<div class="trend-summary"><span class="trend-date">{escape(run_time)} {escape(slot_label)}</span>{escape(news_data["trend"][:120])}…</div>'

    news_rows = ""
    for art in news_data["articles"]:
        rank = art.get("rank", "")
        title = escape((art.get("title") or "")[:70])
        url = escape(art.get("url") or "#")
        cat = escape(art.get("category") or "")
        src = escape(art.get("source_label") or "")
        news_rows += f"""<a href="{url}" target="_blank" rel="noopener" class="topic-row">
  <span class="topic-rank">#{rank}</span>
  <span class="topic-title">{title}</span>
  <span class="topic-meta">{cat} {src}</span>
</a>"""

    news_section = f"""<div class="topic-section">
  <div class="section-header"><span class="section-title">📰 最新ニュース</span><a href="index.html" class="section-more">もっと見る →</a></div>
  {trend_html}
  <div class="topic-list">{news_rows or '<div class="topic-empty">データなし</div>'}</div>
</div>"""

    # ── 最新ツール ──
    IMPACT = {"high": ("🔴", "#ef4444"), "medium": ("🟡", "#f59e0b"), "low": ("⚪", "#64748b")}
    tool_rows = ""
    for t in tools:
        name = escape(t.get("tool_name") or "")
        summary = escape((t.get("summary_ja") or "")[:60])
        imp = t.get("impact", "low")
        icon, color = IMPACT.get(imp, IMPACT["low"])
        rt = escape(t.get("release_type") or "")
        url = escape(t.get("url") or "#")
        tool_rows += f"""<a href="{url}" target="_blank" rel="noopener" class="topic-row">
  <span class="topic-rank" style="color:{color}">{icon}</span>
  <span class="topic-title"><strong>{name}</strong>{' — ' + summary if summary else ''}</span>
  <span class="topic-meta">{rt}</span>
</a>"""

    tools_section = f"""<div class="topic-section">
  <div class="section-header"><span class="section-title">🔧 最新ツール</span><a href="tools.html" class="section-more">もっと見る →</a></div>
  <div class="topic-list">{tool_rows or '<div class="topic-empty">データなし</div>'}</div>
</div>"""

    # ── バズ ──
    buzz_rows = ""
    for b in buzz:
        content = escape((b.get("content") or "")[:60])
        author = escape(b.get("author") or "")
        likes = b.get("likes", 0)
        url = escape(b.get("url") or "#")
        buzz_rows += f"""<a href="{url}" target="_blank" rel="noopener" class="topic-row">
  <span class="topic-rank">❤️ {likes:,}</span>
  <span class="topic-title">{content}</span>
  <span class="topic-meta">@{author}</span>
</a>"""

    buzz_section = f"""<div class="topic-section">
  <div class="section-header"><span class="section-title">🔥 バズりトップ</span><a href="buzz.html" class="section-more">もっと見る →</a></div>
  <div class="topic-list">{buzz_rows or '<div class="topic-empty">データなし</div>'}</div>
</div>"""

    # ── git ログ ──
    log_rows = ""
    for log in git_logs:
        log_rows += f"""<div class="log-row">
  <span class="log-date">{escape(log['date'])}</span>
  <span class="log-sha">{escape(log['sha'])}</span>
  <span class="log-subject">{escape(log['subject'])}</span>
</div>"""
    if not log_rows:
        log_rows = '<div class="log-empty">ログが取得できませんでした</div>'

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI News Collector — ホーム</title>
<style>
  :root {{
    --bg: #0a0f1e; --surface: #111827; --card: #1a2236;
    --accent: #38bdf8; --accent2: #0284c7; --text: #e2e8f0;
    --muted: #94a3b8; --border: #2d3748;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, sans-serif; min-height: 100vh; padding-top: 48px; }}
  .topnav {{ position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: #0a0f1eee; backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); display: flex; gap: 0.4rem; justify-content: center; flex-wrap: wrap; padding: 6px 12px; }}
  .topnav a {{ display: inline-block; padding: 4px 12px; background: var(--card); border-radius: 6px; color: var(--muted); text-decoration: none; font-size: 0.82rem; white-space: nowrap; }}
  .topnav a:hover {{ color: var(--accent); background: rgba(56,189,248,0.1); }}
  .topnav a.active {{ background: var(--accent2); color: #fff; }}
  header {{ background: linear-gradient(135deg, #0c1a35, #0a0f1e); padding: 28px 32px 24px; border-bottom: 1px solid var(--border); text-align: center; }}
  .site-title {{ font-size: 1.8rem; font-weight: 800; color: var(--accent); }}
  .site-sub {{ font-size: 0.85rem; color: var(--muted); margin-top: 6px; }}
  .site-updated {{ font-size: 0.75rem; color: #4b5563; margin-top: 4px; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 28px 16px; display: flex; flex-direction: column; gap: 32px; }}
  /* 機能カード */
  .section-title {{ font-size: 0.82rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; }}
  .pages-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin-top: 14px; }}
  .page-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px 18px; text-decoration: none; color: var(--text);
    display: flex; flex-direction: column; gap: 6px;
    transition: border-color 0.2s, transform 0.15s;
    border-left: 3px solid var(--card-color, var(--border));
  }}
  .page-card:hover {{ border-color: var(--card-color); transform: translateY(-2px); }}
  .page-card-title {{ font-size: 0.95rem; font-weight: 700; color: var(--card-color); }}
  .page-card-desc {{ font-size: 0.8rem; color: var(--muted); line-height: 1.55; flex: 1; }}
  .page-updated {{ font-size: 0.7rem; color: #4b5563; }}
  .page-diagram-link {{ font-size: 0.75rem; color: var(--muted); }}
  .page-diagram-link a {{ color: var(--accent); text-decoration: none; }}
  .page-diagram-link a:hover {{ text-decoration: underline; }}
  /* トピックセクション */
  .topics-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }}
  .topic-section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; display: flex; flex-direction: column; gap: 10px; }}
  .section-header {{ display: flex; align-items: center; justify-content: space-between; }}
  .section-more {{ font-size: 0.75rem; color: var(--muted); text-decoration: none; }}
  .section-more:hover {{ color: var(--accent); }}
  .trend-summary {{ font-size: 0.78rem; color: var(--muted); background: rgba(56,189,248,0.06); border-left: 2px solid var(--accent); padding: 6px 10px; border-radius: 4px; line-height: 1.6; }}
  .trend-date {{ font-size: 0.72rem; color: #4b5563; margin-right: 6px; }}
  .topic-list {{ display: flex; flex-direction: column; gap: 2px; }}
  .topic-row {{ display: flex; align-items: baseline; gap: 8px; padding: 7px 6px; border-radius: 6px; text-decoration: none; color: var(--text); transition: background 0.15s; }}
  .topic-row:hover {{ background: rgba(255,255,255,0.04); }}
  .topic-rank {{ font-size: 0.75rem; color: var(--muted); min-width: 36px; flex-shrink: 0; }}
  .topic-title {{ font-size: 0.83rem; flex: 1; line-height: 1.4; }}
  .topic-meta {{ font-size: 0.72rem; color: var(--muted); flex-shrink: 0; text-align: right; max-width: 80px; }}
  .topic-empty {{ font-size: 0.8rem; color: #4b5563; padding: 8px 6px; }}
  /* git ログ */
  .log-section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; }}
  .log-row {{ display: flex; gap: 10px; align-items: baseline; padding: 6px 0; border-bottom: 1px solid rgba(45,55,72,0.5); font-size: 0.8rem; }}
  .log-row:last-child {{ border-bottom: none; }}
  .log-date {{ color: var(--muted); min-width: 76px; flex-shrink: 0; }}
  .log-sha {{ font-family: monospace; font-size: 0.72rem; color: #4b5563; flex-shrink: 0; }}
  .log-subject {{ color: var(--text); }}
  .log-empty {{ color: var(--muted); font-size: 0.82rem; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.78rem; padding: 28px; border-top: 1px solid var(--border); }}
  @media (max-width: 640px) {{
    header {{ padding: 18px 12px; }}
    .site-title {{ font-size: 1.4rem; }}
    .pages-grid, .topics-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<nav class="topnav">
  <a href="home.html" class="active">🏠 ホーム</a>
  <a href="index.html">📰 ニュース</a>
  <a href="strategy.html">🎯 施策提案</a>
  <a href="buzz.html">🔥 バズりランキング</a>
  <a href="money.html">🎬 マネタイズ</a>
  <a href="sns_success.html">🧠 SNS成功者</a>
  <a href="post_generator.html">✍️ 投稿ストック</a>
  <a href="tools.html">🔧 ツール追跡</a>
  <a href="reviews.html">📋 使ってみた</a>
</nav>
<header>
  <div class="site-title">🤖 AI News Collector</div>
  <div class="site-sub">RSS・X・HackerNews・Redditから自動収集 → Geminiが分析・整理</div>
  <div class="site-updated">Generated: {now_str}</div>
</header>
<div class="container">
  <div>
    <div class="section-title">機能一覧</div>
    <div class="pages-grid">{cards_html}</div>
  </div>
  <div>
    <div class="section-title" style="margin-bottom:0">最新トピック</div>
    <div class="topics-grid" style="margin-top:14px">
      {news_section}
      {tools_section}
      {buzz_section}
    </div>
  </div>
  <div class="log-section">
    <div class="section-title" style="margin-bottom:10px">🕐 最近の更新</div>
    {log_rows}
  </div>
</div>
<footer>AI News Collector — 自動収集・分析パイプライン</footer>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, output_path)
    logger.info("Home page generated → %s", output_path)


def build() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_home_page()


if __name__ == "__main__":
    build()

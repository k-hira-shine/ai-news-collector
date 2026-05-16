"""トップページ（home.html）生成モジュール

各ページの Last updated と git ログを表示する機能一覧ページ。
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

logger = logging.getLogger("ai-news.build_home")

DOCS_DIR = os.path.join(os.path.dirname(__file__), "docs")
OUTPUT_PATH = os.path.join(DOCS_DIR, "home.html")
JST = ZoneInfo("Asia/Tokyo")

PAGES = [
    {
        "file": "index.html",
        "title": "📰 ニュース",
        "desc": "RSS・X・HNから収集したAI関連ニュースを毎日自動更新",
        "color": "#38bdf8",
    },
    {
        "file": "tools.html",
        "title": "🔧 ツール追跡",
        "desc": "AIツール・機能リリースをリアルタイムで追跡。日付・ファミリー・影響度でフィルター可能",
        "color": "#a78bfa",
    },
    {
        "file": "reviews.html",
        "title": "📋 使ってみた",
        "desc": "試したAIツールの所感・評価を記録。履歴管理・編集機能付き",
        "color": "#34d399",
    },
    {
        "file": "buzz.html",
        "title": "🔥 バズりランキング",
        "desc": "いいね・RT数でランキング化。バズったAI情報を見逃さない",
        "color": "#fb923c",
    },
    {
        "file": "strategy.html",
        "title": "🎯 施策提案",
        "desc": "収集ニュースからYouTube施策をAIが自動提案",
        "color": "#f472b6",
    },
    {
        "file": "money.html",
        "title": "🎬 マネタイズ",
        "desc": "収益化・マネタイズ関連情報を自動収集・整理",
        "color": "#fbbf24",
    },
    {
        "file": "sns_success.html",
        "title": "🧠 SNS成功者",
        "desc": "SNSで成功した人の思考法・習慣を自動収集",
        "color": "#60a5fa",
    },
    {
        "file": "post_generator.html",
        "title": "✍️ 投稿ストック",
        "desc": "AI生成の投稿案をストック。すぐ使えるコンテンツを常備",
        "color": "#4ade80",
    },
]


def _get_last_updated(html_file: str) -> str:
    """HTMLファイルから 'Last updated: YYYY-MM-DD HH:MM JST' を抽出する"""
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


def _get_git_log(n: int = 10) -> list[dict]:
    """直近 n 件の git コミットを JST で返す（build: / memo: 系は除外）"""
    try:
        result = subprocess.run(
            ["git", "log", f"-{n * 3}", "--format=%H\t%ai\t%s"],
            capture_output=True, text=True,
            cwd=os.path.dirname(__file__),
        )
        logs = []
        skip_prefixes = ("build:", "Merge")
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
            logs.append({
                "sha": sha[:7],
                "date": dt.strftime("%m/%d %H:%M"),
                "subject": subject,
            })
            if len(logs) >= n:
                break
        return logs
    except Exception:
        return []


def build_home_page(output_path: str = OUTPUT_PATH) -> None:
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    git_logs = _get_git_log(10)

    # ページカード生成
    cards_html = ""
    for page in PAGES:
        updated = _get_last_updated(page["file"])
        color = page["color"]
        href = page["file"]
        title = escape(page["title"])
        desc = escape(page["desc"])
        updated_html = f'<span class="page-updated">{escape(updated)}</span>' if updated else ""
        cards_html += f"""<a href="{href}" class="page-card" style="--card-color:{color}">
  <div class="page-card-title">{title}</div>
  <div class="page-card-desc">{desc}</div>
  {updated_html}
</a>
"""

    # git ログ生成
    if git_logs:
        log_rows = ""
        for log in git_logs:
            log_rows += f"""<div class="log-row">
  <span class="log-date">{escape(log['date'])}</span>
  <span class="log-sha">{escape(log['sha'])}</span>
  <span class="log-subject">{escape(log['subject'])}</span>
</div>
"""
    else:
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
  header {{ background: linear-gradient(135deg, #0c1a35, #0a0f1e); padding: 40px 32px 32px; border-bottom: 1px solid var(--border); text-align: center; }}
  .site-title {{ font-size: 2rem; font-weight: 800; color: var(--accent); letter-spacing: -0.5px; }}
  .site-sub {{ font-size: 0.9rem; color: var(--muted); margin-top: 8px; }}
  .site-updated {{ font-size: 0.78rem; color: var(--muted); margin-top: 6px; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 32px 16px; display: flex; flex-direction: column; gap: 40px; }}
  /* ページカード */
  .section-title {{ font-size: 1rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 16px; }}
  .pages-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }}
  .page-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    padding: 20px; text-decoration: none; color: var(--text);
    display: flex; flex-direction: column; gap: 8px;
    transition: border-color 0.2s, transform 0.15s;
    border-left: 3px solid var(--card-color, var(--border));
  }}
  .page-card:hover {{ border-color: var(--card-color); transform: translateY(-2px); }}
  .page-card-title {{ font-size: 1.05rem; font-weight: 700; color: var(--card-color); }}
  .page-card-desc {{ font-size: 0.83rem; color: var(--muted); line-height: 1.6; flex: 1; }}
  .page-updated {{ font-size: 0.72rem; color: #4b5563; margin-top: 4px; }}
  /* git ログ */
  .log-section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
  .log-row {{ display: flex; gap: 12px; align-items: baseline; padding: 7px 0; border-bottom: 1px solid rgba(45,55,72,0.6); font-size: 0.82rem; }}
  .log-row:last-child {{ border-bottom: none; }}
  .log-date {{ color: var(--muted); min-width: 80px; flex-shrink: 0; }}
  .log-sha {{ font-family: monospace; font-size: 0.75rem; color: #4b5563; flex-shrink: 0; }}
  .log-subject {{ color: var(--text); }}
  .log-empty {{ color: var(--muted); font-size: 0.85rem; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 32px; border-top: 1px solid var(--border); }}
  @media (max-width: 640px) {{
    header {{ padding: 24px 16px; }}
    .site-title {{ font-size: 1.5rem; }}
    .pages-grid {{ grid-template-columns: 1fr; }}
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
    <div class="pages-grid">
      {cards_html}
    </div>
  </div>
  <div class="log-section">
    <div class="section-title" style="margin-bottom:12px">🕐 最近の更新</div>
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

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


def _latest_news_topic() -> str:
    """最新分析から top_articles #1 のタイトルを返す"""
    files = sorted(glob(os.path.join(DATA_DIR, "analysis", "*.json")), reverse=True)
    for fpath in files[:3]:
        try:
            with open(fpath, encoding="utf-8") as f:
                d = json.load(f)
            arts = d.get("top_articles") or []
            if arts:
                t = arts[0].get("title") or ""
                url = arts[0].get("url") or ""
                return {"text": t[:80], "url": url}
        except Exception:
            continue
    return {}


def _latest_tool_topic() -> dict:
    """tools/ から impact:high の最新1件を返す"""
    files = sorted(glob(os.path.join(DATA_DIR, "tools", "*.jsonl")), reverse=True)
    for fpath in files[:3]:
        try:
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("tool_name") and obj.get("impact") == "high":
                        name = obj.get("tool_name", "")
                        summary = obj.get("summary_ja", "")[:60]
                        url = obj.get("url") or ""
                        return {"text": f"{name} — {summary}", "url": url}
        except Exception:
            continue
    return {}


def _latest_review_topic() -> dict:
    """reviews.json から最新の使ってみた1件を返す"""
    path = os.path.join(DATA_DIR, "reviews.json")
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        entries = list(d.values()) if isinstance(d, dict) else d
        # updated_at で最新順
        entries.sort(key=lambda x: x.get("updated_at") or x.get("updated") or "", reverse=True)
        if entries:
            e = entries[0]
            name = e.get("tool_name") or e.get("name") or ""
            verdict = e.get("verdict") or ""
            memo = (e.get("memo") or "")[:50]
            text = f"{name}{('：' + verdict) if verdict else ''}{(' / ' + memo) if memo else ''}"
            return {"text": text, "url": "reviews.html"}
    except Exception:
        pass
    return {}


def _latest_buzz_topic() -> dict:
    """buzz.json からいいね最多の投稿1件を返す"""
    path = os.path.join(DATA_DIR, "buzz.json")
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        accounts = d.get("accounts") or []
        best = None
        best_likes = -1
        for acc in accounts:
            for post in (acc.get("tweets") or acc.get("top_posts") or [])[:3]:
                likes = post.get("likes") or post.get("like_count") or 0
                if likes > best_likes:
                    best_likes = likes
                    best = {"text": (post.get("content") or post.get("text") or "")[:70],
                            "url": post.get("url") or "buzz.html",
                            "likes": likes}
        return best or {}
    except Exception:
        return {}


def _latest_strategy_topic() -> dict:
    """analysis から youtube_ideas #1 を返す"""
    files = sorted(glob(os.path.join(DATA_DIR, "analysis", "*.json")), reverse=True)
    for fpath in files[:3]:
        try:
            with open(fpath, encoding="utf-8") as f:
                d = json.load(f)
            ideas = (d.get("strategy") or {}).get("youtube_ideas") or []
            if ideas:
                return {"text": (ideas[0].get("title") or "")[:70], "url": "strategy.html"}
        except Exception:
            continue
    return {}


def _latest_money_topic() -> dict:
    """money/ から最新1件を返す"""
    files = sorted(glob(os.path.join(DATA_DIR, "money", "*.jsonl")), reverse=True)
    for fpath in files[:1]:
        try:
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    t = obj.get("title") or obj.get("content") or ""
                    return {"text": t[:70], "url": "money.html"}
        except Exception:
            pass
    return {}


def _latest_sns_topic() -> dict:
    """sns_success/ から最新1件を返す"""
    files = sorted(glob(os.path.join(DATA_DIR, "sns_success", "*.jsonl")), reverse=True)
    for fpath in files[:1]:
        try:
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    t = obj.get("title") or obj.get("content") or ""
                    return {"text": t[:70], "url": "sns_success.html"}
        except Exception:
            pass
    return {}


def _latest_post_topic() -> dict:
    """generated_posts から最新1件を返す"""
    files = sorted(glob(os.path.join(DATA_DIR, "generated_posts", "*.json")), reverse=True)
    for fpath in files[:1]:
        try:
            with open(fpath, encoding="utf-8") as f:
                posts = json.load(f)
            if posts:
                p = posts[0]
                text = (p.get("text") or p.get("template_name") or "")[:70]
                return {"text": text, "url": "post_generator.html"}
        except Exception:
            pass
    return {}


def _get_latest_diagram() -> dict:
    files = sorted(glob(os.path.join(DOCS_DIR, "diagrams", "*.html")), reverse=True)
    if not files:
        return {}
    latest = os.path.basename(files[0])
    return {"href": f"diagrams/{latest}", "label": latest.replace(".html", "")}


# ── ページ定義（topic_fn: そのページの最新トピック取得関数）──

PAGES = [
    {
        "file": "index.html",
        "title": "📰 ニュース",
        "desc": "RSS・X・HNから収集したAI関連ニュースを毎日自動更新。Geminiがトレンド分析・要約を生成",
        "color": "#38bdf8",
        "topic_fn": _latest_news_topic,
    },
    {
        "file": "tools.html",
        "title": "🔧 ツール追跡",
        "desc": "AIツール・機能リリースをリアルタイムで追跡。日付・ファミリー・影響度でフィルター可能",
        "color": "#a78bfa",
        "topic_fn": _latest_tool_topic,
    },
    {
        "file": "reviews.html",
        "title": "📋 使ってみた",
        "desc": "試したAIツールの所感・評価を記録。ステータス・判定・メモを履歴付きで管理",
        "color": "#34d399",
        "topic_fn": _latest_review_topic,
    },
    {
        "file": "buzz.html",
        "title": "🔥 バズりランキング",
        "desc": "いいね・RT数でランキング化。バズったAI情報を見逃さない",
        "color": "#fb923c",
        "topic_fn": _latest_buzz_topic,
    },
    {
        "file": "strategy.html",
        "title": "🎯 施策提案",
        "desc": "収集ニュースからYouTube施策をAIが自動提案。今すぐ使える企画アイデアを毎日更新",
        "color": "#f472b6",
        "topic_fn": _latest_strategy_topic,
    },
    {
        "file": "money.html",
        "title": "🎬 マネタイズ",
        "desc": "収益化・マネタイズ関連情報を自動収集・整理",
        "color": "#fbbf24",
        "topic_fn": _latest_money_topic,
    },
    {
        "file": "sns_success.html",
        "title": "🧠 SNS成功者",
        "desc": "SNSで成功した人の思考法・習慣を自動収集",
        "color": "#60a5fa",
        "topic_fn": _latest_sns_topic,
    },
    {
        "file": "post_generator.html",
        "title": "✍️ 投稿ストック",
        "desc": "AI生成の投稿案をストック。すぐ使えるコンテンツを常備",
        "color": "#4ade80",
        "topic_fn": _latest_post_topic,
    },
]


# ── HTML生成 ────────────────────────────────────────

def build_home_page(output_path: str = OUTPUT_PATH) -> None:
    now_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    git_logs = _get_git_log()
    diagram = _get_latest_diagram()

    # ── 機能リスト（1行1機能、3行構成）──
    rows_html = ""
    for page in PAGES:
        updated = _get_last_updated(page["file"])
        color = page["color"]
        href = page["file"]
        title = escape(page["title"])
        desc = escape(page["desc"])
        updated_html = f'<span class="row-updated">{escape(updated)}</span>' if updated else ""

        # 最新トピック取得
        topic = {}
        try:
            topic = page["topic_fn"]() or {}
        except Exception:
            pass

        # ニュースには図解リンクも追加
        extra_html = ""
        if page["file"] == "index.html" and diagram:
            extra_html = f'<a href="{escape(diagram["href"])}" class="diagram-chip" target="_blank" rel="noopener" onclick="event.stopPropagation()">📊 最新図解: {escape(diagram["label"])}</a>'

        if topic and topic.get("text"):
            topic_url = escape(topic.get("url") or href)
            topic_text = escape(topic["text"])
            # 外部URLかどうか判定
            is_external = topic_url.startswith("http")
            target = ' target="_blank" rel="noopener"' if is_external else ""
            topic_html = f'<a href="{topic_url}"{target} class="row-topic" onclick="event.stopPropagation()">{topic_text}</a>'
        else:
            topic_html = '<span class="row-topic-empty">データなし</span>'

        rows_html += f"""<a href="{href}" class="feature-row" style="--row-color:{color}">
  <div class="row-line1">
    <span class="row-title">{title}</span>
    {updated_html}
    {extra_html}
  </div>
  <div class="row-line2">{desc}</div>
  <div class="row-line3">💬 最新: {topic_html}</div>
</a>
"""

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
  header {{ background: linear-gradient(135deg, #0c1a35, #0a0f1e); padding: 22px 32px 18px; border-bottom: 1px solid var(--border); text-align: center; }}
  .site-title {{ font-size: 1.6rem; font-weight: 800; color: var(--accent); }}
  .site-sub {{ font-size: 0.82rem; color: var(--muted); margin-top: 5px; }}
  .site-updated {{ font-size: 0.72rem; color: #4b5563; margin-top: 4px; }}
  .container {{ max-width: 860px; margin: 0 auto; padding: 28px 16px; display: flex; flex-direction: column; gap: 32px; }}
  /* セクションタイトル */
  .section-label {{ font-size: 0.78rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }}
  /* 機能リスト */
  .feature-list {{ display: flex; flex-direction: column; gap: 8px; }}
  .feature-row {{
    background: var(--card); border: 1px solid var(--border); border-radius: 12px;
    padding: 14px 18px; text-decoration: none; color: var(--text);
    display: flex; flex-direction: column; gap: 5px;
    border-left: 3px solid var(--row-color, var(--border));
    transition: border-color 0.2s, transform 0.15s;
  }}
  .feature-row:hover {{ border-color: var(--row-color); transform: translateX(3px); }}
  .row-line1 {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .row-title {{ font-size: 1rem; font-weight: 700; color: var(--row-color); }}
  .row-updated {{ font-size: 0.7rem; color: #4b5563; margin-left: auto; }}
  .row-line2 {{ font-size: 0.82rem; color: var(--muted); line-height: 1.55; }}
  .row-line3 {{ font-size: 0.8rem; color: #64748b; }}
  .row-topic {{ color: var(--text); text-decoration: none; }}
  .row-topic:hover {{ color: var(--accent); text-decoration: underline; }}
  .row-topic-empty {{ color: #4b5563; }}
  .diagram-chip {{ font-size: 0.72rem; background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.3); color: var(--accent); padding: 2px 8px; border-radius: 20px; text-decoration: none; white-space: nowrap; }}
  .diagram-chip:hover {{ background: rgba(56,189,248,0.2); }}
  /* git ログ */
  .log-section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; }}
  .log-row {{ display: flex; gap: 10px; align-items: baseline; padding: 6px 0; border-bottom: 1px solid rgba(45,55,72,0.5); font-size: 0.8rem; }}
  .log-row:last-child {{ border-bottom: none; }}
  .log-date {{ color: var(--muted); min-width: 76px; flex-shrink: 0; }}
  .log-sha {{ font-family: monospace; font-size: 0.72rem; color: #4b5563; flex-shrink: 0; }}
  .log-subject {{ color: var(--text); }}
  .log-empty {{ color: var(--muted); font-size: 0.82rem; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.75rem; padding: 24px; border-top: 1px solid var(--border); }}
  @media (max-width: 600px) {{
    header {{ padding: 14px 12px; }}
    .site-title {{ font-size: 1.3rem; }}
    .row-updated {{ margin-left: 0; }}
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
    <div class="section-label">機能一覧</div>
    <div class="feature-list">
      {rows_html}
    </div>
  </div>
  <div class="log-section">
    <div class="section-label" style="margin-bottom:10px">🕐 最近の更新</div>
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

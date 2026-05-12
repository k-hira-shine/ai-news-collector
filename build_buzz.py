"""
build_buzz.py — data/buzz.json → docs/buzz.html を生成する

ai-news-collector の GitHub Actions から呼ばれる。
x-research の run.py が data/buzz.json を書き出した後に実行。
"""

import html
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).parent
BUZZ_JSON = BASE / "data" / "buzz.json"
OUT_HTML = BASE / "docs" / "buzz.html"


def fmt_date(date_raw: str) -> tuple[str, str]:
    try:
        dt = datetime.strptime(date_raw, "%a %b %d %H:%M:%S +0000 %Y").replace(tzinfo=timezone.utc)
        date_str = dt.strftime("%Y/%m/%d")
        days_ago = (datetime.now(timezone.utc) - dt).days
        ago_str = "今日" if days_ago == 0 else ("1日前" if days_ago == 1 else f"{days_ago}日前")
        return date_str, ago_str
    except Exception:
        return date_raw[:10], ""


def render_tweet(rank: int, t: dict, median: float | None) -> str:
    likes = t.get("likes", 0)
    er = t.get("eng_rate")
    er_str = f"{er:.4f}%" if er is not None else "—"
    views = t.get("views", 0)
    retweets = t.get("retweets", 0)
    replies = t.get("replies", 0)
    followers = t.get("author_followers")
    followers_str = f"{followers:,}" if followers else "—"
    buzz_mult = f"{round(likes / median, 1)}×" if median and median > 0 else "—"
    url = t.get("url", "")
    text = html.escape(t.get("text", ""))
    date_str, ago_str = fmt_date(t.get("created_at", ""))

    is_buzz = median and likes > median * 3
    rank_cls = "gold" if rank == 1 else ("silver" if rank == 2 else ("bronze" if rank == 3 else ""))
    buzz_badge = '<span class="buzz-badge">🔥 バズり</span>' if is_buzz else ""
    open_link = f'<a href="{url}" target="_blank" class="open-link">↗ Xで開く</a>' if url else ""

    return f"""
<div class="tweet-row">
  <div class="tweet-header">
    <span class="rank {rank_cls}">#{rank}</span>
    <span class="followers">フォロワー {followers_str}</span>
    <span class="date">{date_str}　<span class="ago">{ago_str}</span></span>
    {buzz_badge}
    <span class="tweet-stats">
      <span class="likes">♥ {likes:,}</span>
      <span class="eng">エンゲ {er_str}</span>
      <span class="mult">中央値比 {buzz_mult}</span>
      {open_link}
    </span>
  </div>
  <div class="tweet-meta">
    <span>🔁 {retweets:,}</span>
    <span>💬 {replies:,}</span>
    <span>👁 {views:,}</span>
  </div>
  <div class="tweet-text">{text}</div>
</div>"""


def build() -> None:
    if not BUZZ_JSON.exists():
        print(f"buzz.json が見つかりません: {BUZZ_JSON}")
        return

    data = json.loads(BUZZ_JSON.read_text(encoding="utf-8"))
    updated_at = data.get("updated_at", "—")
    accounts = data.get("accounts", [])

    # タブHTML生成
    tabs_nav = ""
    tabs_content = ""
    for i, ac in enumerate(accounts):
        account = ac["account"]
        display_name = html.escape(ac.get("display_name", ""))
        snap_date = ac.get("snap_date", "—")
        median = ac.get("median_likes")
        median_str = str(int(median)) if median is not None else "—"
        tweets = ac.get("tweets", [])
        count = len(tweets)
        active = "active" if i == 0 else ""

        tabs_nav += f"""
<button class="tab-btn {active}" onclick="switchTab('{account}', this)">
  <span class="tab-name">{display_name}</span>
  <span class="tab-handle">@{account}</span>
</button>"""

        rows = "".join(render_tweet(rank + 1, t, median) for rank, t in enumerate(tweets))

        tabs_content += f"""
<div class="tab-panel {active}" id="tab-{account}">
  <div class="account-header">
    <div class="account-info">
      <span class="account-display">{display_name}</span>
      <a href="https://x.com/{account}" target="_blank" class="account-handle">@{account} ↗</a>
    </div>
    <div class="account-pills">
      <span class="pill pill-blue">更新: {snap_date}</span>
      <span class="pill pill-gray">{count}件</span>
      <span class="pill pill-green">中央値いいね {median_str}</span>
    </div>
  </div>
  <div class="tweet-list">
    {rows if rows else '<div class="empty">データがありません</div>'}
  </div>
</div>"""

    html_out = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🔥 バズりランキング | AI News Dashboard</title>
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
.nav-links {{ display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap; margin-top: 0.8rem; }}
.nav-link {{ display: inline-block; padding: 0.4rem 1.2rem; background: var(--surface2); border-radius: 8px; color: var(--blue); text-decoration: none; font-size: 0.9rem; }}
.nav-link:hover {{ background: #475569; }}
.nav-link.active {{ background: var(--accent); color: #fff; }}

/* タブ */
.tabs-nav {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1.5rem; }}
.tab-btn {{ background: var(--surface); border: 1px solid var(--surface2); border-radius: 10px; padding: 0.6rem 1rem; cursor: pointer; color: var(--muted); text-align: left; transition: all .15s; }}
.tab-btn:hover {{ border-color: var(--accent); color: var(--text); }}
.tab-btn.active {{ background: var(--surface2); border-color: var(--accent); color: var(--text); }}
.tab-name {{ display: block; font-size: 0.85rem; font-weight: 700; color: var(--text); }}
.tab-handle {{ display: block; font-size: 0.72rem; color: var(--blue); margin-top: 1px; }}
.tab-panel {{ display: none; }}
.tab-panel.active {{ display: block; }}

/* アカウントヘッダー */
.account-header {{ display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 1.2rem; }}
.account-info {{ display: flex; flex-direction: column; gap: 2px; }}
.account-display {{ font-size: 1.1rem; font-weight: 700; color: var(--text); }}
.account-handle {{ font-size: 0.82rem; font-weight: 600; color: var(--blue); text-decoration: none; }}
.account-handle:hover {{ text-decoration: underline; }}
.account-pills {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
.pill {{ font-size: 0.72rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; }}
.pill-blue {{ background: #1e3a5f; color: var(--blue); }}
.pill-gray {{ background: var(--surface2); color: var(--muted); }}
.pill-green {{ background: #14532d; color: var(--green); }}

/* ツイートリスト */
.tweet-row {{ padding: 12px 0; border-bottom: 1px solid var(--surface2); }}
.tweet-row:last-child {{ border-bottom: none; }}
.tweet-header {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; font-size: 0.82rem; }}
.rank {{ font-weight: 700; min-width: 30px; color: var(--muted); }}
.rank.gold {{ color: #f59e0b; }}
.rank.silver {{ color: #9ca3af; }}
.rank.bronze {{ color: #b45309; }}
.followers {{ color: var(--muted); }}
.date {{ color: var(--muted); }}
.ago {{ color: #475569; }}
.buzz-badge {{ background: #3d1a1a; color: var(--red); font-size: 0.68rem; font-weight: 700; padding: 2px 7px; border-radius: 4px; }}
.tweet-stats {{ margin-left: auto; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
.likes {{ color: var(--red); font-weight: 600; }}
.eng {{ color: var(--green); }}
.mult {{ color: var(--blue); }}
.open-link {{ color: var(--blue); font-size: 0.75rem; font-weight: 600; text-decoration: none; border: 1px solid var(--surface2); padding: 2px 8px; border-radius: 5px; white-space: nowrap; }}
.open-link:hover {{ border-color: var(--accent); }}
.tweet-meta {{ display: flex; gap: 14px; padding-left: 38px; font-size: 0.72rem; color: var(--muted); margin-bottom: 4px; }}
.tweet-text {{ font-size: 0.85rem; color: #94a3b8; line-height: 1.6; padding-left: 38px; white-space: pre-wrap; word-break: break-word; }}
.empty {{ text-align: center; color: var(--muted); padding: 3rem; }}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>🔥 バズりランキング</h1>
  <div class="updated">最終更新: {updated_at}</div>
  <nav class="nav-links">
    <a href="index.html" class="nav-link">📊 ニュース</a>
    <a href="buzz.html" class="nav-link active">🔥 バズりランキング</a>
    <a href="strategy.html" class="nav-link">📁 図解アーカイブ</a>
  </nav>
</header>

<div class="tabs-nav">
{tabs_nav}
</div>

{tabs_content}

</div>
<script>
function switchTab(account, btn) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + account).classList.add('active');
}}
</script>
</body>
</html>"""

    OUT_HTML.write_text(html_out, encoding="utf-8")
    print(f"buzz.html 生成完了: {len(accounts)}アカウント → {OUT_HTML}")


if __name__ == "__main__":
    build()

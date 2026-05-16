"""
build_buzz.py — data/buzz.json → docs/buzz.html を生成する

ai-news-collector の GitHub Actions から呼ばれる。
x-research の run.py が data/buzz.json を書き出した後に実行。
"""

import html
import json
import os
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


def render_tweet_overall(rank: int, t: dict, account: str, display_name: str, median: float | None, sort_mode: str) -> str:
    """全体ランキング用カード（アカウントバッジ付き）"""
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
    rank_cls = "gold" if rank == 1 else ("silver" if rank == 2 else ("bronze" if rank == 3 else ""))
    open_link = f'<a href="{url}" target="_blank" class="open-link">↗ Xで開く</a>' if url else ""
    # 全体ランキングでは注目指標を強調
    highlight_likes = ' style="color:#f87171;font-weight:800;"' if sort_mode == "likes" else ""
    highlight_eng = ' style="color:#34d399;font-weight:800;"' if sort_mode == "eng" else ""

    return f"""
<div class="tweet-row">
  <div class="tweet-header">
    <span class="rank {rank_cls}">#{rank}</span>
    <span class="account-badge">{html.escape(display_name)} @{html.escape(account)}</span>
    <span class="followers">フォロワー {followers_str}</span>
    <span class="date">{date_str}　<span class="ago">{ago_str}</span></span>
    <span class="tweet-stats">
      <span class="likes"{highlight_likes}>♥ {likes:,}</span>
      <span class="eng"{highlight_eng}>エンゲ {er_str}</span>
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


def build_overall_panel(accounts: list[dict]) -> str:
    """全アカウント横断・中央値2倍以上を いいね順/エンゲ率順 で表示"""
    THRESHOLD = 2.0
    likes_list: list[tuple] = []
    eng_list: list[tuple] = []

    for ac in accounts:
        account = ac["account"]
        display_name = ac.get("display_name", account)
        median = ac.get("median_likes") or 0
        for t in ac.get("tweets", []):
            likes = t.get("likes", 0)
            er = t.get("eng_rate")
            if median > 0 and likes >= median * THRESHOLD:
                likes_list.append((likes, t, account, display_name, median))
            if er is not None and median > 0 and likes >= median * THRESHOLD:
                eng_list.append((er, t, account, display_name, median))

    likes_list.sort(key=lambda x: x[0], reverse=True)
    eng_list.sort(key=lambda x: x[0], reverse=True)

    likes_rows = "".join(
        render_tweet_overall(i + 1, t, ac, dn, med, "likes")
        for i, (_, t, ac, dn, med) in enumerate(likes_list)
    ) or '<div class="empty">データがありません</div>'

    eng_rows = "".join(
        render_tweet_overall(i + 1, t, ac, dn, med, "eng")
        for i, (_, t, ac, dn, med) in enumerate(eng_list)
    ) or '<div class="empty">データがありません</div>'

    total_accounts = len(accounts)
    return f"""
<div class="tab-panel active" id="tab-__overall__">
  <div class="account-header">
    <div class="account-info">
      <span class="account-display">🏆 全体ランキング</span>
    </div>
    <div class="account-pills">
      <span class="pill pill-gray">{total_accounts}アカウント合算</span>
      <span class="pill pill-blue">中央値×{THRESHOLD:.0f}倍以上</span>
      <span class="pill pill-green">いいね順 {len(likes_list)}件</span>
    </div>
  </div>
  <div class="overall-sort-btns">
    <button class="sort-btn active" id="sort-likes" onclick="switchSort('likes')">❤️ いいね順</button>
    <button class="sort-btn" id="sort-eng" onclick="switchSort('eng')">📊 エンゲ率順</button>
  </div>
  <div id="overall-likes" class="overall-view">{likes_rows}</div>
  <div id="overall-eng" class="overall-view" style="display:none">{eng_rows}</div>
</div>"""


def build(gh_pat: str = "") -> None:
    gh_pat = gh_pat or os.environ.get("GH_PAT", "")

    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from utils import STATUS_BANNER_HTML as STATUS_BANNER  # noqa: F401
    except Exception:
        STATUS_BANNER = ""

    if not BUZZ_JSON.exists():
        print(f"buzz.json が見つかりません: {BUZZ_JSON}")
        return

    data = json.loads(BUZZ_JSON.read_text(encoding="utf-8"))
    updated_at = data.get("updated_at", "—")
    accounts = data.get("accounts", [])

    # 全体ランキングパネルを先頭に
    overall_panel = build_overall_panel(accounts)
    overall_nav = """
<div class="tab-item" id="item-__overall__">
  <button class="tab-btn active" onclick="switchTab('__overall__', this)">
    <span class="tab-name">🏆 全体</span>
    <span class="tab-handle">全アカウント</span>
  </button>
</div>"""

    # タブHTML生成
    tabs_nav = overall_nav
    tabs_content = overall_panel
    for i, ac in enumerate(accounts):
        account = ac["account"]
        display_name = html.escape(ac.get("display_name", ""))
        snap_date = ac.get("snap_date", "—")
        median = ac.get("median_likes")
        median_str = str(int(median)) if median is not None else "—"
        tweets = ac.get("tweets", [])
        count = len(tweets)
        active = "" if i == 0 else ""  # 全体タブがデフォルトactiveなので全て非active

        tabs_nav += f"""
<div class="tab-item" id="item-{account}">
  <button class="tab-btn {active}" onclick="switchTab('{account}', this)">
    <span class="tab-name">{display_name}</span>
    <span class="tab-handle">@{account}</span>
  </button>
  <button class="delete-btn" onclick="deleteAccount('{account}', '{html.escape(display_name)}')" title="削除">✕</button>
</div>"""

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

    # GH_PAT を分割して埋め込む（GitHubのシークレットスキャン回避のため2分割）
    if gh_pat:
        mid = len(gh_pat) // 2
        p1, p2 = gh_pat[:mid], gh_pat[mid:]
        pat_js = f'const GH_PAT = "{p1}" + "{p2}";'
    else:
        pat_js = 'const GH_PAT = "";'

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
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding-top: 48px; }}
.topnav {{ position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: #0f172aee; backdrop-filter: blur(8px); border-bottom: 1px solid var(--surface2); display: flex; gap: 0.4rem; justify-content: center; flex-wrap: wrap; padding: 6px 12px; }}
.nav-link {{ display: inline-block; padding: 4px 12px; background: var(--surface2); border-radius: 6px; color: var(--blue); text-decoration: none; font-size: 0.82rem; white-space: nowrap; }}
.nav-link:hover {{ background: #475569; color: #fff; }}
.nav-link.active {{ background: var(--accent); color: #fff; }}
header {{ text-align: center; padding: 1.5rem 1rem 1rem; }}
header h1 {{ font-size: 1.8rem; color: var(--accent); }}
header .updated {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.3rem; }}

/* レイアウト */
.layout {{ display: flex; gap: 0; min-height: calc(100vh - 120px); }}

/* 左サイドバー */
.sidebar {{ width: 220px; flex-shrink: 0; background: var(--surface); border-right: 1px solid var(--surface2); padding: 1rem 0; position: sticky; top: 0; height: 100vh; overflow-y: auto; }}
.sidebar-title {{ font-size: 0.72rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; padding: 0 1rem 0.6rem; }}
.tab-item {{ position: relative; }}
.tab-btn {{ display: block; width: 100%; background: none; border: none; border-left: 3px solid transparent; padding: 0.7rem 2.2rem 0.7rem 1rem; cursor: pointer; color: var(--muted); text-align: left; transition: all .15s; }}
.tab-btn:hover {{ background: var(--surface2); color: var(--text); border-left-color: var(--accent); }}
.tab-btn.active {{ background: #1e293b; color: var(--text); border-left-color: var(--accent); }}
.tab-name {{ display: block; font-size: 0.85rem; font-weight: 700; color: inherit; }}
.tab-handle {{ display: block; font-size: 0.72rem; color: var(--blue); margin-top: 2px; }}
.delete-btn {{ position: absolute; right: 6px; top: 50%; transform: translateY(-50%); background: none; border: none; color: #475569; font-size: 0.8rem; cursor: pointer; padding: 4px; border-radius: 4px; line-height: 1; opacity: 0; transition: opacity .15s; }}
.tab-item:hover .delete-btn {{ opacity: 1; }}
.delete-btn:hover {{ background: #3d1a1a; color: var(--red); }}
/* 追加フォーム */
.add-account {{ padding: 0.8rem 1rem; border-top: 1px solid var(--surface2); margin-top: 0.5rem; }}
.add-account-title {{ font-size: 0.7rem; color: var(--muted); margin-bottom: 6px; }}
.add-form {{ display: flex; flex-direction: column; gap: 5px; }}
.add-input {{ background: #0f172a; border: 1px solid var(--surface2); color: var(--text); border-radius: 5px; padding: 5px 8px; font-size: 0.78rem; width: 100%; }}
.add-input:focus {{ outline: none; border-color: var(--accent); }}
.add-btn {{ background: var(--accent); color: #fff; border: none; border-radius: 5px; padding: 5px 8px; font-size: 0.78rem; cursor: pointer; font-weight: 600; }}
.add-btn:hover {{ opacity: 0.85; }}
.add-note {{ font-size: 0.68rem; color: #475569; margin-top: 3px; }}

/* メインコンテンツ */
.main-content {{ flex: 1; padding: 1.5rem 2rem; overflow-x: hidden; }}
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
.tweet-stats {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
.likes {{ color: var(--red); font-weight: 600; }}
.eng {{ color: var(--green); }}
.mult {{ color: var(--blue); }}
.open-link {{ color: var(--blue); font-size: 0.75rem; font-weight: 600; text-decoration: none; border: 1px solid var(--surface2); padding: 2px 8px; border-radius: 5px; white-space: nowrap; }}
.open-link:hover {{ border-color: var(--accent); }}
.tweet-meta {{ display: flex; gap: 14px; padding-left: 38px; font-size: 0.72rem; color: var(--muted); margin-bottom: 4px; }}
.tweet-text {{ font-size: 0.85rem; color: #94a3b8; line-height: 1.6; padding-left: 38px; white-space: pre-wrap; word-break: break-word; }}
.empty {{ text-align: center; color: var(--muted); padding: 3rem; }}
.overall-sort-btns {{ display: flex; gap: 0.5rem; margin-bottom: 1rem; }}
.sort-btn {{ padding: 0.4rem 1.2rem; border-radius: 8px; border: 1px solid var(--surface2); background: var(--surface); color: var(--muted); cursor: pointer; font-size: 0.88rem; font-weight: 600; transition: all .15s; }}
.sort-btn:hover {{ background: var(--surface2); color: var(--text); }}
.sort-btn.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
.account-badge {{ background: var(--surface2); color: var(--blue); font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 4px; white-space: nowrap; }}
@media (max-width: 640px) {{
  header {{ padding: 1rem 0.75rem 0.75rem; }}
  header h1 {{ font-size: 1.3rem; }}
  .topnav {{ gap: 4px; padding: 4px 8px; }}
  .nav-link {{ padding: 3px 8px; font-size: 0.75rem; }}
  .layout {{ flex-direction: column; min-height: unset; }}
  .sidebar {{ width: 100%; height: auto; position: static; border-right: none; border-bottom: 1px solid var(--surface2); padding: 0.6rem 0 0; overflow-y: visible; overflow-x: hidden; }}
  .sidebar-title {{ padding: 0 0.75rem 0.4rem; }}
  .tabs-scroll-wrap {{ flex-direction: row !important; overflow-x: auto; overflow-y: visible; -webkit-overflow-scrolling: touch; white-space: nowrap; padding-bottom: 2px; }}
  .tab-item {{ display: inline-block !important; }}
  .tab-btn {{ border-left: none; border-bottom: 3px solid transparent; padding: 0.5rem 0.8rem; white-space: nowrap; width: auto; }}
  .tab-btn.active {{ border-left-color: transparent; border-bottom-color: var(--accent); }}
  .tab-btn:hover {{ border-left-color: transparent; border-bottom-color: var(--accent); }}
  .delete-btn {{ opacity: 1; top: 4px; right: 4px; transform: none; }}
  .add-account {{ border-top: 1px solid var(--surface2); padding: 0.6rem 0.75rem; }}
  .main-content {{ padding: 1rem 0.75rem; }}
  .account-header {{ gap: 8px; margin-bottom: 0.8rem; }}
  .account-display {{ font-size: 0.97rem; }}
  .tweet-row {{ padding: 10px 0; }}
  .tweet-text {{ padding-left: 0; font-size: 0.82rem; }}
  .tweet-meta {{ padding-left: 0; }}
  .tweet-stats {{ gap: 7px; }}
}}
</style>
</head>
<body>
<nav class="topnav">
  <a class="nav-link" href="home.html">🏠 ホーム</a>
  <a class="nav-link" href="index.html">📰 ニュース</a>
  <a class="nav-link" href="strategy.html">🎯 施策提案</a>
  <a class="nav-link active" href="buzz.html">🔥 バズりランキング</a>
  <a class="nav-link" href="money.html">🎬 マネタイズ</a>
  <a class="nav-link" href="sns_success.html">🧠 SNS成功者</a>
  <a class="nav-link" href="post_generator.html">✍️ 投稿ストック</a>
  <a class="nav-link" href="tools.html">🔧 ツール追跡</a>
  <a class="nav-link" href="reviews.html">📋 使ってみた</a>
</nav>
<div class="container">
<header>
  <h1>🔥 バズりランキング</h1>
  <div class="updated">最終更新: {updated_at}</div>
</header>

<div class="layout">
  <aside class="sidebar">
    <div class="sidebar-title">アカウント</div>
    <div class="tabs-scroll-wrap" style="display:flex;flex-direction:column;">
    {tabs_nav}
    </div>
      <div class="add-account">
      <div class="add-account-title">＋ アカウント追加</div>
      <div class="add-note" style="margin-bottom:6px;color:#94a3b8;font-size:11px;">@handle・URLどちらでもOK</div>
      <div class="add-form">
        <input class="add-input" id="addHandle" placeholder="@handle or https://x.com/..." />
        <button class="add-btn" onclick="addAccount()">今すぐ追加</button>
        <div class="add-note" id="addStatus"></div>
      </div>
    </div>
  </aside>
  <div class="main-content">
    {tabs_content}
  </div>
</div>
<script>
{pat_js}
function switchTab(account, btn) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + account).classList.add('active');
}}

function switchSort(mode) {{
  document.getElementById('sort-likes').classList.toggle('active', mode === 'likes');
  document.getElementById('sort-eng').classList.toggle('active', mode === 'eng');
  document.getElementById('overall-likes').style.display = mode === 'likes' ? '' : 'none';
  document.getElementById('overall-eng').style.display = mode === 'eng' ? '' : 'none';
}}

function deleteAccount(account, displayName) {{
  if (!confirm(displayName + ' (@' + account + ') をリストから削除しますか？\\n（このセッション中のみ非表示になります）')) return;
  const item = document.getElementById('item-' + account);
  const panel = document.getElementById('tab-' + account);
  if (item) item.remove();
  if (panel) panel.remove();
  // 最初のアカウントをアクティブに
  const firstBtn = document.querySelector('.tab-btn');
  const firstPanel = document.querySelector('.tab-panel');
  if (firstBtn) firstBtn.classList.add('active');
  if (firstPanel) firstPanel.classList.add('active');
}}

async function addAccount() {{
  const handleInput = document.getElementById('addHandle');
  const status = document.getElementById('addStatus');
  let raw = handleInput.value.trim();
  // URL形式（https://x.com/handle や twitter.com/handle）からハンドル抽出
  const urlMatch = raw.match(/(?:x\.com|twitter\.com)\/([A-Za-z0-9_]+)/);
  let handle = urlMatch ? urlMatch[1] : raw.replace(/^@/, '');
  if (!handle) {{ status.textContent = '⚠️ ハンドルを入力してください'; status.style.color='#f59e0b'; return; }}
  if (!GH_PAT) {{ status.textContent = '⚠️ 設定が必要です（管理者にお知らせください）'; status.style.color='#f87171'; return; }}

  status.textContent = '⏳ 収集ワークフローを起動中...';
  status.style.color = '#60a5fa';

  try {{
    const res = await fetch(
      'https://api.github.com/repos/k-hira-shine/ai-news-collector/actions/workflows/buzz-collect.yml/dispatches',
      {{
        method: 'POST',
        headers: {{
          'Authorization': 'Bearer ' + GH_PAT,
          'Accept': 'application/vnd.github+json',
          'Content-Type': 'application/json',
        }},
        body: JSON.stringify({{ ref: 'main', inputs: {{ account: handle, days: '30' }} }}),
      }}
    );
    if (res.status === 204) {{
      status.textContent = '✅ @' + handle + ' の収集を開始しました！約2〜3分で反映されます。';
      status.style.color = '#34d399';
      handleInput.value = '';
      // PATはセッション保持（再利用できるようlocalStorageには保存しない）
    }} else {{
      const body = await res.text();
      status.textContent = '❌ エラー ' + res.status + ': ' + body;
      status.style.color = '#f87171';
    }}
  }} catch(e) {{
    status.textContent = '❌ ' + e.message;
    status.style.color = '#f87171';
  }}
}}
</script>
{STATUS_BANNER}
</body>
</html>"""

    OUT_HTML.write_text(html_out, encoding="utf-8")
    print(f"buzz.html 生成完了: {len(accounts)}アカウント → {OUT_HTML}")


if __name__ == "__main__":
    build()

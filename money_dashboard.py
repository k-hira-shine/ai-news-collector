"""動画マネタイズ事例ダッシュボード生成

docs/money.html を生成する。
既存の index.html / strategy.html には一切触れない。
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("ai-news.money_dashboard")

JST = timezone(timedelta(hours=9))
CATEGORY_ICONS = {
    "YouTube収益化": "▶️",
    "ショート動画/Reels/TikTok": "📱",
    "AI動画生成": "🎬",
    "ライブ配信": "🔴",
    "動画編集代行": "✂️",
    "動画×教育/コンサル": "📚",
    "動画×SaaS/プロダクト": "💻",
    "その他": "💡",
}


def generate_money_page(output_path: str) -> None:
    from money_analyzer import load_all_money_analyses
    import yaml
    config = {}
    try:
        with open(os.path.join(os.path.dirname(__file__) or ".", "config.yaml"), encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        pass

    cases = load_all_money_analyses()
    html = _render_money_html(cases, config)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("Money page generated → %s (%d cases)", output_path, len(cases))


def _render_money_html(cases: list[dict], config: dict = None) -> str:
    config = config or {}
    now_jst = datetime.now(JST)
    now_str = now_jst.strftime("%Y-%m-%d %H:%M JST")

    # カテゴリ別に集計
    by_category: dict[str, list[dict]] = {}
    for case in cases:
        cat = case.get("category") or "その他"
        by_category.setdefault(cat, []).append(case)

    # 日本 / 海外 集計
    jp_count = sum(1 for c in cases if c.get("is_japanese"))
    global_count = len(cases) - jp_count

    total = len(cases)

    # 収集基準の設定値
    money_cfg = config.get("money_collection", {})
    min_followers = money_cfg.get("min_followers", 1000)
    accounts = money_cfg.get("accounts", [])
    account_labels = "、".join(f'@{a["handle"]}' for a in accounts) if accounts else "なし"
    search_query_count = len(money_cfg.get("search_queries", []))
    cache_days = money_cfg.get("cache_retention_days", 90)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>動画マネタイズ事例集</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f1a; color: #e0e0f0; min-height: 100vh; }}
    header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-bottom: 1px solid #2a2a4a; padding: 20px 24px; }}
    .header-inner {{ max-width: 1100px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }}
    .header-title {{ font-size: 1.4rem; font-weight: 700; color: #f0c060; }}
    .header-title span {{ font-size: 0.9rem; color: #888; margin-left: 10px; font-weight: 400; }}
    .nav-links {{ display: flex; gap: 12px; }}
    .nav-links a {{ color: #7aa0d4; text-decoration: none; font-size: 0.85rem; padding: 4px 10px; border: 1px solid #2a4060; border-radius: 4px; }}
    .nav-links a:hover {{ background: #1e3050; }}
    .main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
    .stats-bar {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
    .stat-card {{ background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 10px; padding: 16px 20px; flex: 1; min-width: 140px; text-align: center; }}
    .stat-number {{ font-size: 2rem; font-weight: 700; color: #f0c060; }}
    .stat-label {{ font-size: 0.8rem; color: #888; margin-top: 4px; }}
    .filter-bar {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; align-items: center; }}
    .filter-btn {{ background: #1a1a2e; border: 1px solid #2a2a4a; color: #aaa; padding: 6px 14px; border-radius: 20px; cursor: pointer; font-size: 0.85rem; transition: all 0.2s; }}
    .filter-btn.active, .filter-btn:hover {{ background: #f0c060; color: #1a1a2e; border-color: #f0c060; font-weight: 600; }}
    .filter-label {{ color: #666; font-size: 0.8rem; margin-right: 4px; }}
    .sort-bar {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; align-items: center; }}
    .sort-btn {{ background: #1a1a2e; border: 1px solid #2a2a4a; color: #aaa; padding: 5px 14px; border-radius: 6px; cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }}
    .sort-btn.active {{ background: #334155; color: #e0e0f0; border-color: #556; font-weight: 600; }}
    .select-filters {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-left: auto; }}
    .select-group {{ display: flex; align-items: center; gap: 6px; font-size: 0.82rem; color: #888; }}
    .select-group select {{ background: #1a1a2e; border: 1px solid #2a2a4a; color: #e0e0f0; padding: 4px 10px; border-radius: 6px; font-size: 0.82rem; cursor: pointer; }}
    .filter-section {{ margin-bottom: 16px; }}
    .filter-section-label {{ font-size: 0.75rem; color: #666; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em; }}
    .cat-filter-grid {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .cases-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }}
    .case-card {{ background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 12px; padding: 16px; transition: border-color 0.2s, box-shadow 0.2s; cursor: pointer; }}
    .case-card:hover {{ border-color: #f0c060; box-shadow: 0 0 12px rgba(240,192,96,0.15); }}
    .case-card a {{ color: inherit; text-decoration: none; }}
    .case-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; gap: 8px; }}
    .case-category {{ font-size: 0.75rem; background: #2a2a4a; color: #aaa; padding: 3px 8px; border-radius: 12px; white-space: nowrap; }}
    .case-income {{ font-size: 0.85rem; font-weight: 700; color: #4ade80; background: #0f2a1a; padding: 3px 8px; border-radius: 12px; white-space: nowrap; }}
    .case-summary {{ font-size: 0.95rem; font-weight: 600; color: #e0e0f0; margin-bottom: 8px; line-height: 1.5; }}
    .case-method {{ font-size: 0.85rem; color: #aaa; margin-bottom: 8px; }}
    .case-body {{ font-size: 0.82rem; color: #94a3b8; background: #0f172a; border-left: 3px solid #2a4060; padding: 8px 12px; border-radius: 0 6px 6px 0; margin-bottom: 10px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }}
    .case-tools {{ display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }}
    .tool-tag {{ font-size: 0.75rem; background: #16213e; color: #7aa0d4; border: 1px solid #2a4060; padding: 2px 8px; border-radius: 10px; }}
    .case-footer {{ display: flex; justify-content: space-between; align-items: center; margin-top: 8px; padding-top: 8px; border-top: 1px solid #2a2a4a; font-size: 0.78rem; color: #666; }}
    .case-footer a {{ color: #7aa0d4; text-decoration: none; }}
    .case-footer a:hover {{ text-decoration: underline; }}
    .flag {{ font-size: 0.75rem; }}
    .engagement {{ display: flex; gap: 10px; }}
    .empty-state {{ text-align: center; padding: 60px 20px; color: #555; }}
    .empty-state .emoji {{ font-size: 3rem; margin-bottom: 16px; }}
    .criteria-box {{ background: #0f172a; border: 1px solid #2a4060; border-radius: 10px; padding: 14px 20px; margin-bottom: 20px; font-size: 0.82rem; color: #94a3b8; line-height: 1.8; }}
    .criteria-box strong {{ color: #7aa0d4; }}
    .criteria-box .criteria-title {{ font-size: 0.88rem; font-weight: 700; color: #f0c060; margin-bottom: 8px; }}
    section.cat-section {{ margin-bottom: 32px; }}
    .cat-title {{ font-size: 1.1rem; font-weight: 700; color: #f0c060; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #2a2a4a; }}
    footer {{ text-align: center; padding: 20px; color: #444; font-size: 0.8rem; border-top: 1px solid #1a1a2e; margin-top: 40px; }}
    @media (max-width: 640px) {{
      header {{ padding: 14px 12px; }}
      .header-title {{ font-size: 1.1rem; }}
      .header-title span {{ display: block; margin-left: 0; margin-top: 2px; font-size: 0.78rem; }}
      .nav-links {{ gap: 6px; flex-wrap: wrap; }}
      .nav-links a {{ font-size: 0.78rem; padding: 3px 7px; }}
      .main {{ padding: 16px 10px; }}
      .stats-bar {{ gap: 8px; }}
      .stat-card {{ padding: 10px 12px; min-width: 100px; }}
      .stat-number {{ font-size: 1.5rem; }}
      .cases-grid {{ grid-template-columns: 1fr; gap: 12px; }}
      .case-card {{ padding: 12px; }}
      .case-summary {{ font-size: 0.9rem; }}
      .case-body {{ font-size: 0.8rem; padding: 6px 10px; }}
      .filter-bar {{ gap: 6px; }}
      .filter-btn {{ font-size: 0.8rem; padding: 5px 10px; }}
      .cat-title {{ font-size: 0.97rem; }}
      .criteria-box {{ padding: 10px 12px; font-size: 0.8rem; }}
    }}
  </style>
</head>
<body>
<header>
  <div class="header-inner">
    <div>
      <div class="header-title">🎬 動画マネタイズ事例集 <span>Last updated: {now_str}</span></div>
    </div>
    <nav class="nav-links">
      <a href="index.html">📰 ニュース</a>
      <a href="buzz.html">🔥 バズりランキング</a>
      <a href="strategy.html">🎯 施策提案</a>
    </nav>
  </div>
</header>

<div class="main">
  <!-- 収集基準の説明 -->
  <div class="criteria-box">
    <div class="criteria-title">📋 収集・掲載基準</div>
    <strong>収集元：</strong>指定アカウント（{account_labels}）＋ 日英{search_query_count}種の検索クエリ &nbsp;|&nbsp;
    <strong>フォロワー：</strong>{min_followers:,}人以上の投稿のみ採用 &nbsp;|&nbsp;
    <strong>判定：</strong>Gemini AIが「動画を使って稼いでいる・稼げた」具体的事例を自動フィルタリング &nbsp;|&nbsp;
    <strong>蓄積期間：</strong>過去{cache_days}日分を継続収集（since制限なし）
  </div>
  <!-- 統計バー -->
  <div class="stats-bar">
    <div class="stat-card">
      <div class="stat-number">{total}</div>
      <div class="stat-label">総事例数</div>
    </div>
    <div class="stat-card">
      <div class="stat-number">{jp_count}</div>
      <div class="stat-label">🇯🇵 日本の事例</div>
    </div>
    <div class="stat-card">
      <div class="stat-number">{global_count}</div>
      <div class="stat-label">🌍 海外の事例</div>
    </div>
    <div class="stat-card">
      <div class="stat-number">{len(by_category)}</div>
      <div class="stat-label">カテゴリ数</div>
    </div>
  </div>

  <!-- 並べ替え＆絞り込みコントロール -->
  <div class="sort-bar">
    <span class="filter-label">並べ替え：</span>
    <button class="sort-btn active" id="sortEngBtn" onclick="setSort('eng', this)">📈 エンゲ率順</button>
    <button class="sort-btn" id="sortDateBtn" onclick="setSort('date', this)">🕐 新着順</button>
    <div class="select-filters">
      <div class="select-group">
        <label for="engSelect">エンゲ率：</label>
        <select id="engSelect" onchange="applyFilters()">
          <option value="0">制限なし</option>
          <option value="0.001">0.1%以上</option>
          <option value="0.003">0.3%以上</option>
          <option value="0.005">0.5%以上</option>
          <option value="0.01">1%以上</option>
          <option value="0.03">3%以上</option>
        </select>
      </div>
      <div class="select-group">
        <label for="incomeSelect">💰 月収：</label>
        <select id="incomeSelect" onchange="applyFilters()">
          <option value="0">制限なし</option>
          <option value="-1">金額記載あり</option>
          <option value="30000">3万円以上/月</option>
          <option value="100000">10万円以上/月</option>
          <option value="300000">30万円以上/月</option>
          <option value="1000000">100万円以上/月</option>
          <option value="5000000">500万円以上/月</option>
        </select>
      </div>
      <div class="select-group">
        <label for="diffSelect">🎯 手軽さ：</label>
        <select id="diffSelect" onchange="applyFilters()">
          <option value="all">すべて</option>
          <option value="beginner">🟢 初心者向け</option>
          <option value="intermediate">🟡 中級者向け</option>
          <option value="advanced">🔴 上級者向け</option>
        </select>
      </div>
    </div>
  </div>
  <!-- カテゴリ・地域フィルター -->
  <div class="filter-section">
    <div class="filter-section-label">地域</div>
    <div class="filter-bar" id="regionBar" style="margin-bottom:10px;">
      <button class="filter-btn active" onclick="filterRegion('all', this)">🌐 すべて ({total})</button>
      <button class="filter-btn" onclick="filterRegion('jp', this)">🇯🇵 日本 ({jp_count})</button>
      <button class="filter-btn" onclick="filterRegion('global', this)">🌍 海外 ({global_count})</button>
    </div>
    <div class="filter-section-label">カテゴリ</div>
    <div class="cat-filter-grid" id="catFilterBar">
      <button class="filter-btn active" onclick="filterCategory('all', this)">すべて</button>
      {"".join(f'<button class="filter-btn" onclick="filterCategory(\'{cat}\', this)" title="{cat}">{CATEGORY_ICONS.get(cat, "💡")} {cat} <span style=\"opacity:0.6;font-size:0.78rem;\">({len(items)})</span></button>' for cat, items in sorted(by_category.items(), key=lambda x: -len(x[1])))}
    </div>
  </div>

  <!-- 事例グリッド -->
  <div class="cases-grid" id="casesGrid">
    {_render_all_cases(cases) if cases else _render_empty()}
  </div>
</div>

<footer>動画マネタイズ事例集 — 収集データをもとにGeminiが自動分類</footer>

<script>
let activeCategory = 'all';
let activeRegion = 'all';
let activeSort = 'eng';

function filterCategory(cat, btn) {{
  activeCategory = cat;
  document.querySelectorAll('#catFilterBar .filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}}

function filterRegion(region, btn) {{
  activeRegion = region;
  document.querySelectorAll('#regionBar .filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}}

function setSort(mode, btn) {{
  activeSort = mode;
  document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}}

function applyFilters() {{
  const grid = document.getElementById('casesGrid');
  const engMin = parseFloat(document.getElementById('engSelect').value) || 0;
  const incomeFilter = parseInt(document.getElementById('incomeSelect').value) || 0;
  const diffFilter = document.getElementById('diffSelect').value;
  const allCards = Array.from(grid.querySelectorAll('.case-card'));

  const visible = allCards.filter(card => {{
    const catMatch = activeCategory === 'all' || card.dataset.category === activeCategory;
    const regionMatch = activeRegion === 'all' ||
      (activeRegion === 'jp' && card.dataset.jp === 'true') ||
      (activeRegion === 'global' && card.dataset.jp === 'false');
    const engMatch = parseFloat(card.dataset.eng || '0') >= engMin;
    const incomeVal = parseInt(card.dataset.incomeVal || '0');
    const incomeMatch = incomeFilter === 0 ||
      (incomeFilter === -1 && incomeVal > 0) ||
      (incomeFilter > 0 && incomeVal >= incomeFilter);
    const diffMatch = diffFilter === 'all' || card.dataset.difficulty === diffFilter;
    return catMatch && regionMatch && engMatch && incomeMatch && diffMatch;
  }});

  visible.sort((a, b) => {{
    if (activeSort === 'date') {{
      return (b.dataset.date || '').localeCompare(a.dataset.date || '');
    }} else {{
      return parseFloat(b.dataset.eng || '0') - parseFloat(a.dataset.eng || '0');
    }}
  }});

  allCards.forEach(c => c.style.display = 'none');
  visible.forEach(c => {{ c.style.display = ''; grid.appendChild(c); }});
}}
</script>
</body>
</html>"""


def _render_all_cases(cases: list[dict]) -> str:
    html = ""
    # エンゲージメント率（いいね÷フォロワー）の高い順にソート
    def _eng_rate(c):
        likes = c.get("engagement", {}).get("likes", 0)
        followers = c.get("author_followers") or 1
        return likes / followers
    sorted_cases = sorted(cases, key=_eng_rate, reverse=True)
    for case in sorted_cases:
        html += _render_case_card(case)
    return html


def _parse_income_monthly_jpy(income_str: str) -> int:
    """金額文字列を月次円換算（概算）して返す。不明な場合は0。"""
    if not income_str:
        return 0
    import re
    s = income_str.replace(",", "").replace("，", "").replace("、", "").replace(" ", "")

    # 億 → 円
    m = re.search(r"([\d.]+)億", s)
    if m:
        base = float(m.group(1)) * 100_000_000
        if "年" in s:
            return int(base / 12)
        return int(base)

    # 千万 → 円
    m = re.search(r"([\d.]+)千万", s)
    if m:
        base = float(m.group(1)) * 10_000_000
        if "年" in s:
            return int(base / 12)
        return int(base)

    # 万 → 円
    m = re.search(r"([\d.]+)万", s)
    if m:
        base = float(m.group(1)) * 10_000
        if "年" in s:
            return int(base / 12)
        return int(base)

    # $K → 円（1ドル=150円換算）
    m = re.search(r"\$([\d.]+)[Kk]", s)
    if m:
        base = float(m.group(1)) * 1000 * 150
        if "/mo" in s.lower() or "month" in s.lower():
            return int(base)
        if "year" in s.lower() or "yearly" in s.lower():
            return int(base / 12)
        return int(base)

    # $数値 → 円
    m = re.search(r"\$([\d.]+)", s)
    if m:
        base = float(m.group(1)) * 150
        if "year" in s.lower() or "yearly" in s.lower():
            return int(base / 12)
        return int(base)

    # 数値のみ（円と仮定）
    m = re.search(r"(\d{4,})", s)
    if m:
        return int(m.group(1))

    return 0


def _render_case_card(case: dict) -> str:
    category = case.get("category") or "その他"
    icon = CATEGORY_ICONS.get(category, "💡")
    summary = case.get("summary") or case.get("title") or ""
    method = case.get("method") or ""
    tools = case.get("tools") or []
    income = case.get("income_mentioned") or ""
    is_jp = case.get("is_japanese", True)
    flag = "🇯🇵" if is_jp else "🌍"
    url = case.get("url") or "#"
    author = case.get("author_display") or case.get("author") or ""
    pub_date = ""
    raw_date = case.get("published_at") or ""
    if raw_date:
        try:
            # "Sun May 10 08:42:16 +0000 2026" 形式
            dt = datetime.strptime(raw_date, "%a %b %d %H:%M:%S %z %Y")
            pub_date = dt.astimezone(JST).strftime("%Y/%m/%d")
        except ValueError:
            # "2026-05-10T08:42:16Z" 等の形式
            pub_date = raw_date[:10].replace("-", "/")
    likes = case.get("engagement", {}).get("likes", 0)
    views = case.get("engagement", {}).get("views", 0)

    tools_html = "".join(f'<span class="tool-tag">{t}</span>' for t in tools[:6])
    income_html = f'<span class="case-income">💰 {income}</span>' if income else ""
    views_str = f"{views:,}" if views else ""
    # 元ポスト本文（最大200文字）
    raw_content = case.get("content") or case.get("title") or ""
    content_short = raw_content[:200] + "…" if len(raw_content) > 200 else raw_content
    content_escaped = content_short.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # エンゲ率・日付・手軽さのdata属性を計算
    followers = case.get("author_followers") or 1
    eng_rate = likes / followers
    date_val = ""
    if raw_date:
        try:
            dt2 = datetime.strptime(raw_date, "%a %b %d %H:%M:%S %z %Y")
            date_val = dt2.strftime("%Y%m%d%H%M%S")
        except ValueError:
            date_val = raw_date[:19].replace("-", "").replace(":", "").replace("T", "").replace(" ", "")
    difficulty = case.get("difficulty") or "intermediate"
    income_monthly_jpy = _parse_income_monthly_jpy(income)
    diff_labels = {"beginner": "🟢 初心者向け", "intermediate": "🟡 中級者向け", "advanced": "🔴 上級者向け"}
    diff_label = diff_labels.get(difficulty, "")

    return f"""<div class="case-card" data-category="{category}" data-jp="{str(is_jp).lower()}" data-eng="{eng_rate:.6f}" data-date="{date_val}" data-income-val="{income_monthly_jpy}" data-difficulty="{difficulty}">
  <div class="case-header">
    <span class="case-category">{icon} {category}</span>
    <div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center;">
      {f'<span style="font-size:0.72rem;color:#aaa;">{diff_label}</span>' if diff_label else ''}
      {income_html}
    </div>
  </div>
  <div class="case-summary">{summary}</div>
  {f'<div class="case-method">📌 {method}</div>' if method else ''}
  {f'<div class="case-tools">{tools_html}</div>' if tools_html else ''}
  {f'<div class="case-body">"{content_escaped}"</div>' if content_escaped else ''}
  <div class="case-footer">
    <span>{flag} @{author} · {pub_date}</span>
    <div class="engagement">
      {f'❤️ {likes:,}' if likes else ''}
      {f'👁 {views_str}' if views_str else ''}
      <a href="{url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">ポストを見る →</a>
    </div>
  </div>
</div>"""


def _render_empty() -> str:
    return """<div class="empty-state" style="grid-column: 1/-1;">
  <div class="emoji">🔍</div>
  <p>まだ事例データがありません。<br>ワークフローを実行すると事例が蓄積されます。</p>
</div>"""

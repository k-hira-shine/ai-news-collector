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

    cases = load_all_money_analyses()
    html = _render_money_html(cases)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("Money page generated → %s (%d cases)", output_path, len(cases))


def _render_money_html(cases: list[dict]) -> str:
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
    .cases-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }}
    .case-card {{ background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 12px; padding: 16px; transition: border-color 0.2s, box-shadow 0.2s; cursor: pointer; }}
    .case-card:hover {{ border-color: #f0c060; box-shadow: 0 0 12px rgba(240,192,96,0.15); }}
    .case-card a {{ color: inherit; text-decoration: none; }}
    .case-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; gap: 8px; }}
    .case-category {{ font-size: 0.75rem; background: #2a2a4a; color: #aaa; padding: 3px 8px; border-radius: 12px; white-space: nowrap; }}
    .case-income {{ font-size: 0.85rem; font-weight: 700; color: #4ade80; background: #0f2a1a; padding: 3px 8px; border-radius: 12px; white-space: nowrap; }}
    .case-summary {{ font-size: 0.95rem; font-weight: 600; color: #e0e0f0; margin-bottom: 8px; line-height: 1.5; }}
    .case-method {{ font-size: 0.85rem; color: #aaa; margin-bottom: 8px; }}
    .case-tools {{ display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }}
    .tool-tag {{ font-size: 0.75rem; background: #16213e; color: #7aa0d4; border: 1px solid #2a4060; padding: 2px 8px; border-radius: 10px; }}
    .case-footer {{ display: flex; justify-content: space-between; align-items: center; margin-top: 8px; padding-top: 8px; border-top: 1px solid #2a2a4a; font-size: 0.78rem; color: #666; }}
    .case-footer a {{ color: #7aa0d4; text-decoration: none; }}
    .case-footer a:hover {{ text-decoration: underline; }}
    .flag {{ font-size: 0.75rem; }}
    .engagement {{ display: flex; gap: 10px; }}
    .empty-state {{ text-align: center; padding: 60px 20px; color: #555; }}
    .empty-state .emoji {{ font-size: 3rem; margin-bottom: 16px; }}
    section.cat-section {{ margin-bottom: 32px; }}
    .cat-title {{ font-size: 1.1rem; font-weight: 700; color: #f0c060; margin-bottom: 14px; padding-bottom: 8px; border-bottom: 1px solid #2a2a4a; }}
    footer {{ text-align: center; padding: 20px; color: #444; font-size: 0.8rem; border-top: 1px solid #1a1a2e; margin-top: 40px; }}
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

  <!-- フィルターバー -->
  <div class="filter-bar" id="filterBar">
    <span class="filter-label">カテゴリ：</span>
    <button class="filter-btn active" onclick="filterCategory('all', this)">すべて ({total})</button>
    <button class="filter-btn" onclick="filterRegion('jp', this)">🇯🇵 日本 ({jp_count})</button>
    <button class="filter-btn" onclick="filterRegion('global', this)">🌍 海外 ({global_count})</button>
    {"".join(f'<button class="filter-btn" onclick="filterCategory(\'{cat}\', this)">{CATEGORY_ICONS.get(cat, "💡")} {cat} ({len(items)})</button>' for cat, items in sorted(by_category.items(), key=lambda x: -len(x[1])))}
  </div>

  <!-- 事例グリッド -->
  <div class="cases-grid" id="casesGrid">
    {_render_all_cases(cases) if cases else _render_empty()}
  </div>
</div>

<footer>動画マネタイズ事例集 — 収集データをもとにGeminiが自動分類</footer>

<script>
const allCards = document.querySelectorAll('.case-card');
let activeCategory = 'all';
let activeRegion = 'all';

function filterCategory(cat, btn) {{
  activeCategory = cat;
  document.querySelectorAll('#filterBar .filter-btn').forEach(b => {{
    if (b.textContent.includes('日本') || b.textContent.includes('海外')) return;
    b.classList.remove('active');
  }});
  btn.classList.add('active');
  applyFilters();
}}

function filterRegion(region, btn) {{
  activeRegion = activeRegion === region ? 'all' : region;
  document.querySelectorAll('#filterBar .filter-btn').forEach(b => {{
    if (!b.textContent.includes('日本') && !b.textContent.includes('海外')) return;
    b.classList.remove('active');
  }});
  if (activeRegion !== 'all') btn.classList.add('active');
  applyFilters();
}}

function applyFilters() {{
  allCards.forEach(card => {{
    const catMatch = activeCategory === 'all' || card.dataset.category === activeCategory;
    const regionMatch = activeRegion === 'all' ||
      (activeRegion === 'jp' && card.dataset.jp === 'true') ||
      (activeRegion === 'global' && card.dataset.jp === 'false');
    card.style.display = (catMatch && regionMatch) ? '' : 'none';
  }});
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

    return f"""<div class="case-card" data-category="{category}" data-jp="{str(is_jp).lower()}" onclick="window.open('{url}','_blank')">
  <div class="case-header">
    <span class="case-category">{icon} {category}</span>
    {income_html}
  </div>
  <div class="case-summary"><a href="{url}" target="_blank" rel="noopener">{summary}</a></div>
  {f'<div class="case-method">📌 {method}</div>' if method else ''}
  {f'<div class="case-tools">{tools_html}</div>' if tools_html else ''}
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

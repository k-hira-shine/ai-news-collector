"""AIツール使ってみたレビューページ生成 — docs/reviews.html"""

import json
import logging
import os
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

logger = logging.getLogger("ai-news.build_reviews")

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "reviews.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "reviews.html")

STATUS_LABELS = {
    "using":   ("✅ 使用中",   "#10b981"),
    "trying":  ("🔄 試用中",   "#f59e0b"),
    "untried": ("⬜ 未試用",   "#64748b"),
    "rejected":("❌ 不採用",   "#ef4444"),
}

VERDICT_LABELS = {
    "use":    ("👍 使う",    "#10b981"),
    "no":     ("👎 使わない","#ef4444"),
    "maybe":  ("🤔 検討中",  "#f59e0b"),
    "":       ("— 未判定",   "#64748b"),
}

USE_FOR_LABELS = {
    "x":        "𝕏 X投稿",
    "youtube":  "▶ YouTube",
    "school":   "📚 スクール教材",
    "line":     "💬 LINE特典",
    "work":     "💼 業務効率化",
    "other":    "📌 その他",
}

NAV_LINKS = [
    ("index.html",          "📰 ニュース"),
    ("strategy.html",       "🎯 施策提案"),
    ("buzz.html",           "🔥 バズりランキング"),
    ("money.html",          "🎬 マネタイズ"),
    ("sns_success.html",    "🧠 SNS成功者"),
    ("tools.html",          "🔧 ツール追跡"),
    ("reviews.html",        "📋 使ってみた"),
    ("post_generator.html", "✍️ 投稿ストック"),
    ("hn.html",             "📡 HN/arxiv"),
]


def load_reviews() -> list[dict]:
    if not os.path.exists(DATA_PATH):
        return []
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tools", [])


def _use_for_badges(use_for: list[str]) -> str:
    if not use_for:
        return ""
    badges = "".join(
        f'<span class="use-badge">{escape(USE_FOR_LABELS.get(u, u))}</span>'
        for u in use_for
    )
    return f'<div class="use-for">{badges}</div>'


def _field_row(label: str, value: str) -> str:
    if not value:
        return ""
    return f"""<div class="field-row">
  <span class="field-label">{escape(label)}</span>
  <span class="field-value">{escape(value)}</span>
</div>"""


def _review_card(tool: dict) -> str:
    name = escape(tool.get("name") or "")
    category = escape(tool.get("category") or "")
    url = escape(tool.get("url") or "#")
    status_key = tool.get("status") or "untried"
    verdict_key = tool.get("verdict") or ""
    status_label, status_color = STATUS_LABELS.get(status_key, STATUS_LABELS["untried"])
    verdict_label, verdict_color = VERDICT_LABELS.get(verdict_key, VERDICT_LABELS[""])
    updated = escape(tool.get("updated") or "")
    use_for = tool.get("use_for") or []
    memo = escape(tool.get("memo") or "")

    fields = "".join([
        _field_row("理由",           tool.get("reason") or ""),
        _field_row("目的・用途",      tool.get("purpose") or ""),
        _field_row("使い方・方法",    tool.get("method") or ""),
        _field_row("注意点",          tool.get("caution") or ""),
        _field_row("アクションプラン", tool.get("action_plan") or ""),
    ])

    data_status = escape(status_key)
    data_verdict = escape(verdict_key) if verdict_key else "none"
    data_category = escape(tool.get("category") or "")

    return f"""<div class="review-card" data-status="{data_status}" data-verdict="{data_verdict}" data-category="{data_category}">
  <div class="card-header">
    <div class="tool-name-row">
      <a href="{url}" target="_blank" rel="noopener" class="tool-name">{name}</a>
      <span class="category-badge">{category}</span>
    </div>
    <div class="badge-row">
      <span class="status-badge" style="color:{status_color}">{status_label}</span>
      <span class="verdict-badge" style="color:{verdict_color}">{verdict_label}</span>
      {f'<span class="updated">更新 {updated}</span>' if updated else ''}
    </div>
  </div>
  {_use_for_badges(use_for)}
  {f'<div class="fields">{fields}</div>' if fields.strip() else ''}
  {f'<div class="memo">📝 {memo}</div>' if memo else ''}
</div>"""


def build_reviews_page(output_path: str = OUTPUT_PATH) -> None:
    tools = load_reviews()
    now_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M JST")

    # 集計
    total = len(tools)
    using = sum(1 for t in tools if t.get("status") == "using")
    trying = sum(1 for t in tools if t.get("status") == "trying")
    untried = sum(1 for t in tools if t.get("status") == "untried")
    rejected = sum(1 for t in tools if t.get("status") == "rejected")
    use_verdict = sum(1 for t in tools if t.get("verdict") == "use")

    # カテゴリ一覧
    categories = sorted(set(t.get("category") or "未分類" for t in tools))

    # カード生成
    cards_html = "\n".join(_review_card(t) for t in tools) if tools else \
        '<div class="empty-state"><p>まだレビューデータがありません。data/reviews.json に追記してください。</p></div>'

    # フィルタボタン
    status_btns = '<button class="filter-btn active" data-filter-status="all">すべて</button>\n'
    for k, (label, _) in STATUS_LABELS.items():
        status_btns += f'<button class="filter-btn" data-filter-status="{k}">{label}</button>\n'

    verdict_btns = '<button class="filter-btn active" data-filter-verdict="all">すべて</button>\n'
    for k, (label, _) in VERDICT_LABELS.items():
        if k:
            verdict_btns += f'<button class="filter-btn" data-filter-verdict="{k}">{label}</button>\n'

    category_btns = '<button class="filter-btn active" data-filter-category="all">すべて</button>\n'
    for cat in categories:
        category_btns += f'<button class="filter-btn" data-filter-category="{escape(cat)}">{escape(cat)}</button>\n'

    nav_html = "\n".join(
        f'<a href="{href}" {"class=\"active\"" if href == "reviews.html" else ""}>{label}</a>'
        for href, label in NAV_LINKS
    )
    topnav_html = f'<nav class="topnav">\n{nav_html}\n</nav>'

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIツール 使ってみたレビュー</title>
<style>
  :root {{
    --bg: #0a0f1e; --surface: #111827; --card: #1a2236;
    --accent: #38bdf8; --accent2: #0284c7; --text: #e2e8f0;
    --muted: #94a3b8; --border: #2d3748;
    --green: #10b981; --yellow: #f59e0b; --red: #ef4444;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, sans-serif; min-height: 100vh; padding-top: 48px; }}
  .topnav {{ position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: #0a0f1eee; backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); display: flex; gap: 0.4rem; justify-content: center; flex-wrap: wrap; padding: 6px 12px; }}
  .topnav a {{ display: inline-block; padding: 4px 12px; background: var(--card); border-radius: 6px; color: var(--muted); text-decoration: none; font-size: 0.82rem; white-space: nowrap; }}
  .topnav a:hover {{ color: var(--accent); background: rgba(56,189,248,0.1); }}
  .topnav a.active {{ background: var(--accent2); color: #fff; }}
  header {{ background: linear-gradient(135deg, #0c1a35, #0a0f1e); padding: 16px 32px; border-bottom: 1px solid var(--border); }}
  .header-title {{ font-size: 1.4rem; font-weight: 700; color: var(--accent); }}
  .header-title span {{ font-size: 0.85rem; color: var(--muted); margin-left: 10px; font-weight: 400; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px; }}
  .stats-bar {{ display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }}
  .stat-chip {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 8px 16px; font-size: 0.85rem; color: var(--muted); }}
  .stat-chip strong {{ color: var(--accent); }}
  .filter-section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin-bottom: 20px; display: flex; flex-direction: column; gap: 10px; }}
  .filter-row {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
  .filter-label {{ font-size: 0.76rem; color: var(--muted); min-width: 60px; }}
  .filter-btn {{ background: var(--card); border: 1px solid var(--border); color: var(--muted); padding: 5px 12px; border-radius: 16px; cursor: pointer; font-size: 0.8rem; transition: all 0.2s; }}
  .filter-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
  .filter-btn.active {{ background: var(--accent2); border-color: var(--accent); color: #fff; }}
  .reviews-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 14px; }}
  .review-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; display: flex; flex-direction: column; gap: 10px; transition: border-color 0.2s; }}
  .review-card:hover {{ border-color: var(--accent); }}
  .card-header {{ display: flex; flex-direction: column; gap: 6px; }}
  .tool-name-row {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
  .tool-name {{ font-size: 1.05rem; font-weight: 700; color: var(--accent); text-decoration: none; }}
  .tool-name:hover {{ text-decoration: underline; }}
  .category-badge {{ font-size: 0.72rem; background: rgba(148,163,184,0.15); border: 1px solid var(--border); color: var(--muted); padding: 2px 8px; border-radius: 10px; }}
  .badge-row {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
  .status-badge, .verdict-badge {{ font-size: 0.8rem; font-weight: 600; }}
  .updated {{ font-size: 0.72rem; color: var(--muted); margin-left: auto; }}
  .use-for {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .use-badge {{ font-size: 0.75rem; background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.25); color: var(--accent); padding: 2px 8px; border-radius: 10px; }}
  .fields {{ display: flex; flex-direction: column; gap: 6px; border-top: 1px solid var(--border); padding-top: 8px; }}
  .field-row {{ display: flex; gap: 8px; font-size: 0.85rem; }}
  .field-label {{ color: var(--muted); min-width: 110px; flex-shrink: 0; font-size: 0.78rem; }}
  .field-value {{ color: var(--text); line-height: 1.5; }}
  .memo {{ font-size: 0.85rem; color: var(--muted); background: rgba(148,163,184,0.08); border-radius: 6px; padding: 8px 10px; line-height: 1.6; border-top: 1px solid var(--border); }}
  .empty-state {{ text-align: center; padding: 60px 20px; color: var(--muted); grid-column: 1/-1; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 32px; margin-top: 20px; border-top: 1px solid var(--border); }}
  @media (max-width: 640px) {{
    header {{ padding: 12px; }}
    .topnav {{ gap: 4px; padding: 4px 8px; }}
    .topnav a {{ font-size: 0.75rem; padding: 3px 8px; }}
    .reviews-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
{topnav_html}
<header>
  <div class="header-title" style="max-width:1200px;margin:0 auto;">📋 AIツール使ってみたレビュー <span>Last updated: {now_str}</span></div>
</header>
<div class="container">
  <div class="stats-bar">
    <div class="stat-chip">合計 <strong>{total}</strong> ツール</div>
    <div class="stat-chip">✅ 使用中 <strong>{using}</strong></div>
    <div class="stat-chip">🔄 試用中 <strong>{trying}</strong></div>
    <div class="stat-chip">⬜ 未試用 <strong>{untried}</strong></div>
    <div class="stat-chip">❌ 不採用 <strong>{rejected}</strong></div>
    <div class="stat-chip">👍 採用判定 <strong id="visibleCount">{total}</strong> / {total}</div>
  </div>
  <div class="filter-section">
    <div class="filter-row">
      <span class="filter-label">ステータス</span>
      {status_btns}
    </div>
    <div class="filter-row">
      <span class="filter-label">判定</span>
      {verdict_btns}
    </div>
    <div class="filter-row">
      <span class="filter-label">カテゴリ</span>
      {category_btns}
    </div>
  </div>
  <div class="reviews-grid" id="reviewsGrid">
    {cards_html}
  </div>
</div>
<footer>地上にあるAIツールを全て触っている状態を目指す — data/reviews.json に追記して更新</footer>
<script>
let activeStatus = 'all';
let activeVerdict = 'all';
let activeCategory = 'all';

function applyFilters() {{
  const cards = Array.from(document.querySelectorAll('.review-card'));
  let visible = 0;
  cards.forEach(card => {{
    const sm = activeStatus === 'all' || card.dataset.status === activeStatus;
    const vm = activeVerdict === 'all' || card.dataset.verdict === activeVerdict;
    const cm = activeCategory === 'all' || card.dataset.category === activeCategory;
    const show = sm && vm && cm;
    card.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  document.getElementById('visibleCount').textContent = visible;
}}

document.querySelectorAll('[data-filter-status]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('[data-filter-status]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeStatus = btn.dataset.filterStatus;
    applyFilters();
  }});
}});
document.querySelectorAll('[data-filter-verdict]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('[data-filter-verdict]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeVerdict = btn.dataset.filterVerdict;
    applyFilters();
  }});
}});
document.querySelectorAll('[data-filter-category]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('[data-filter-category]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeCategory = btn.dataset.filterCategory;
    applyFilters();
  }});
}});

// ?tool=ToolName でリンクされた場合、該当カードをハイライト
(function() {{
  const params = new URLSearchParams(window.location.search);
  const toolParam = (params.get('tool') || '').toLowerCase().trim();
  if (!toolParam) return;
  const cards = Array.from(document.querySelectorAll('.review-card'));
  let found = null;
  cards.forEach(card => {{
    const nameEl = card.querySelector('.tool-name');
    if (nameEl && nameEl.textContent.toLowerCase().trim() === toolParam) {{
      card.style.outline = '2px solid var(--accent)';
      card.style.background = 'rgba(56,189,248,0.07)';
      if (!found) found = card;
    }}
  }});
  if (found) {{
    setTimeout(() => found.scrollIntoView({{ behavior: 'smooth', block: 'center' }}), 200);
  }}
}})();
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, output_path)
    logger.info("Reviews page generated → %s (%d tools)", output_path, total)


def build() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_reviews_page()


if __name__ == "__main__":
    build()

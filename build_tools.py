"""AIツール・機能リリース追跡 — docs/tools.html 生成モジュール"""

import json
import logging
import os
from datetime import datetime, timezone
from glob import glob
from html import escape

logger = logging.getLogger("ai-news.build_tools")

TOOLS_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "tools")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "tools.html")

RELEASE_TYPE_ICONS = {
    "新規リリース": "🆕",
    "アップデート": "🔄",
    "機能追加": "✨",
    "廃止・終了": "🚫",
    "その他": "📌",
}

IMPACT_LABELS = {
    "high": ("🔴 重要", "#ef4444"),
    "medium": ("🟡 注目", "#f59e0b"),
    "low": ("⚪ 参考", "#64748b"),
}

SOURCE_ICONS = {
    "rss": "📰",
    "x": "🐦",
    "hn": "🔶",
    "arxiv": "📄",
}


def load_all_items(days: int = 30) -> list[dict]:
    """data/tools/ から直近 days 日分を全件ロード（分析済みのみ）"""
    if not os.path.isdir(TOOLS_DATA_DIR):
        return []
    files = sorted(glob(os.path.join(TOOLS_DATA_DIR, "*.jsonl")), reverse=True)
    items: list[dict] = []
    for fpath in files[:days]:
        with open(fpath, encoding="utf-8") as f:
            for line in f.read().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("tool_name"):  # 分析済みのみ
                        items.append(obj)
                except Exception:
                    continue
    return items


def _fmt_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%Y/%m/%d %H:%M")
    except Exception:
        return iso[:10]


def _tool_card(item: dict) -> str:
    tool_name = escape(item.get("tool_name") or "")
    release_type = item.get("release_type") or "その他"
    release_icon = RELEASE_TYPE_ICONS.get(release_type, "📌")
    summary_ja = escape(item.get("summary_ja") or "")
    title = escape(item.get("title") or "")
    url = escape(item.get("url") or "#")
    source = item.get("source") or "rss"
    source_label = escape(item.get("source_label") or source)
    source_icon = SOURCE_ICONS.get(source, "📰")
    impact = item.get("impact") or "low"
    impact_label, impact_color = IMPACT_LABELS.get(impact, ("⚪ 参考", "#64748b"))
    age = _fmt_date(item.get("published_at") or item.get("analyzed_at") or "")

    # フィルタ用data属性
    data_release = escape(release_type)
    data_impact = escape(impact)
    data_source = escape(source)

    return f"""<div class="tool-card" data-release="{data_release}" data-impact="{data_impact}" data-source="{data_source}">
  <div class="tool-card-header">
    <div class="tool-name-row">
      <span class="tool-name">{tool_name}</span>
      <span class="release-badge">{release_icon} {escape(release_type)}</span>
      <span class="impact-badge" style="color:{impact_color}">{impact_label}</span>
    </div>
    <div class="source-age">
      <span class="source-label">{source_icon} {source_label}</span>
      <span class="age">{age}</span>
    </div>
  </div>
  {f'<div class="summary-ja">{summary_ja}</div>' if summary_ja else ''}
  <div class="card-footer">
    <a href="{url}" target="_blank" rel="noopener" class="article-link">{title[:80] + ('…' if len(title) > 80 else '') if title else '記事を見る'} →</a>
  </div>
</div>"""


def build_tools_page(output_path: str = OUTPUT_PATH) -> None:
    items = load_all_items()
    from zoneinfo import ZoneInfo
    now_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M JST")

    # リリース種別・影響度・ソース一覧
    release_types = sorted(set(i.get("release_type", "その他") for i in items if i.get("release_type")))
    sources = sorted(set(i.get("source_label", "") for i in items if i.get("source_label")))

    cards_html = "\n".join(_tool_card(i) for i in items) if items else \
        '<div class="empty-state"><p>まだデータがありません。ワークフローを実行すると蓄積されます。</p></div>'

    release_filter_btns = '<button class="filter-btn active" data-filter-release="all">すべて</button>\n'
    for rt in release_types:
        icon = RELEASE_TYPE_ICONS.get(rt, "📌")
        release_filter_btns += f'<button class="filter-btn" data-filter-release="{escape(rt)}">{icon} {escape(rt)}</button>\n'

    impact_filter_btns = '<button class="filter-btn active" data-filter-impact="all">すべて</button>\n'
    for imp, (label, _) in IMPACT_LABELS.items():
        impact_filter_btns += f'<button class="filter-btn" data-filter-impact="{imp}">{label}</button>\n'

    source_filter_btns = '<button class="filter-btn active" data-filter-source="all">すべて</button>\n'
    for src_label in sources:
        # source属性はsource_labelから逆引きできないのでlabelで絞り込む
        source_filter_btns += f'<button class="filter-btn" data-filter-source="{escape(src_label)}">{escape(src_label)}</button>\n'

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AIツール・機能リリース追跡</title>
<style>
  :root {{
    --bg: #0a0f1e; --surface: #111827; --card: #1a2236;
    --accent: #38bdf8; --accent2: #0284c7; --text: #e2e8f0;
    --muted: #94a3b8; --border: #2d3748; --success: #10b981;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, sans-serif; min-height: 100vh; }}
  header {{ background: linear-gradient(135deg, #0c1a35, #0a0f1e); padding: 20px 32px; border-bottom: 1px solid var(--border); }}
  .header-inner {{ max-width: 1200px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }}
  .header-title {{ font-size: 1.4rem; font-weight: 700; color: var(--accent); }}
  .header-title span {{ font-size: 0.85rem; color: var(--muted); margin-left: 10px; font-weight: 400; }}
  nav {{ display: flex; gap: 8px; padding: 10px 32px; background: var(--surface); border-bottom: 1px solid var(--border); flex-wrap: wrap; max-width: 100%; }}
  nav a {{ color: var(--muted); text-decoration: none; font-size: 0.85rem; padding: 4px 10px; border-radius: 6px; }}
  nav a:hover {{ color: var(--accent); background: rgba(56,189,248,0.1); }}
  nav a.active {{ color: var(--accent); background: rgba(56,189,248,0.15); }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px; }}
  .stats-bar {{ display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }}
  .stat-chip {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 8px 16px; font-size: 0.85rem; color: var(--muted); }}
  .stat-chip strong {{ color: var(--accent); }}
  .filter-section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin-bottom: 20px; display: flex; flex-direction: column; gap: 10px; }}
  .filter-row {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
  .filter-label {{ font-size: 0.76rem; color: var(--muted); min-width: 60px; }}
  .filter-btn {{ background: var(--card); border: 1px solid var(--border); color: var(--muted); padding: 5px 12px; border-radius: 16px; cursor: pointer; font-size: 0.8rem; transition: all 0.2s; }}
  .filter-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
  .filter-btn.active {{ background: var(--accent2); border-color: var(--accent); color: #fff; }}
  .tools-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 14px; }}
  .tool-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; display: flex; flex-direction: column; gap: 10px; transition: border-color 0.2s; }}
  .tool-card:hover {{ border-color: var(--accent); }}
  .tool-card-header {{ display: flex; flex-direction: column; gap: 6px; }}
  .tool-name-row {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
  .tool-name {{ font-size: 1rem; font-weight: 700; color: var(--accent); }}
  .release-badge {{ font-size: 0.75rem; background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.3); color: var(--accent); padding: 2px 8px; border-radius: 10px; }}
  .impact-badge {{ font-size: 0.75rem; font-weight: 600; }}
  .source-age {{ display: flex; gap: 10px; align-items: center; font-size: 0.76rem; color: var(--muted); }}
  .summary-ja {{ font-size: 0.9rem; color: var(--text); line-height: 1.65; }}
  .card-footer {{ border-top: 1px solid var(--border); padding-top: 8px; }}
  .article-link {{ color: var(--muted); font-size: 0.8rem; text-decoration: none; word-break: break-word; }}
  .article-link:hover {{ color: var(--accent); }}
  .empty-state {{ text-align: center; padding: 60px 20px; color: var(--muted); grid-column: 1/-1; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 32px; margin-top: 20px; border-top: 1px solid var(--border); }}
  @media (max-width: 640px) {{
    header {{ padding: 14px 12px; }}
    nav {{ padding: 8px 12px; }}
    .tools-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<header>
  <div class="header-inner">
    <div class="header-title">🔧 AIツール・機能リリース追跡 <span>Last updated: {now_str}</span></div>
    <nav style="padding:0;border:none;background:none;">
      <a href="index.html">📰 ニュース</a>
      <a href="sns_success.html">🧠 SNS成功者</a>
      <a href="money.html">🎬 マネタイズ</a>
      <a href="tools.html" class="active">🔧 ツール追跡</a>
      <a href="hn.html">📡 HN/arxiv</a>
    </nav>
  </div>
</header>
<div class="container">
  <div class="stats-bar">
    <div class="stat-chip">収録件数 <strong id="visibleCount">{len(items)}</strong> / {len(items)} 件</div>
  </div>
  <div class="filter-section">
    <div class="filter-row">
      <span class="filter-label">種別</span>
      {release_filter_btns}
    </div>
    <div class="filter-row">
      <span class="filter-label">影響度</span>
      {impact_filter_btns}
    </div>
    <div class="filter-row">
      <span class="filter-label">ソース</span>
      {source_filter_btns}
    </div>
  </div>
  <div class="tools-grid" id="toolsGrid">
    {cards_html}
  </div>
</div>
<footer>AIツール・機能リリース情報 — RSS・X・HackerNewsから自動収集し、GeminiがAI分析</footer>
<script>
let activeRelease = 'all';
let activeImpact = 'all';
let activeSource = 'all';

function applyFilters() {{
  const cards = Array.from(document.querySelectorAll('.tool-card'));
  let visible = 0;
  cards.forEach(card => {{
    const releaseMatch = activeRelease === 'all' || card.dataset.release === activeRelease;
    const impactMatch = activeImpact === 'all' || card.dataset.impact === activeImpact;
    const sourceMatch = activeSource === 'all' || card.dataset.source === activeSource;
    const show = releaseMatch && impactMatch && sourceMatch;
    card.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  document.getElementById('visibleCount').textContent = visible;
}}

document.querySelectorAll('[data-filter-release]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('[data-filter-release]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeRelease = btn.dataset.filterRelease;
    applyFilters();
  }});
}});

document.querySelectorAll('[data-filter-impact]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('[data-filter-impact]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeImpact = btn.dataset.filterImpact;
    applyFilters();
  }});
}});

document.querySelectorAll('[data-filter-source]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('[data-filter-source]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    // sourceフィルタはsource_labelで絞り込む
    const val = btn.dataset.filterSource;
    document.querySelectorAll('.tool-card').forEach(card => {{
      if (val === 'all') {{ card.dataset.sourceActive = ''; return; }}
      const srcLabel = card.querySelector('.source-label') ? card.querySelector('.source-label').textContent.trim().replace(/^[^\\s]+\\s/, '') : '';
      card.dataset.source = val === 'all' ? card.dataset.source : (card.querySelector('.source-label')?.textContent.includes(val) ? val : card.dataset.source);
    }});
    activeSource = val;
    // source_labelベースで直接フィルタ
    document.querySelectorAll('.tool-card').forEach(card => {{
      const releaseMatch = activeRelease === 'all' || card.dataset.release === activeRelease;
      const impactMatch = activeImpact === 'all' || card.dataset.impact === activeImpact;
      let sourceMatch = true;
      if (val !== 'all') {{
        const srcEl = card.querySelector('.source-label');
        sourceMatch = srcEl ? srcEl.textContent.includes(val) : false;
      }}
      card.style.display = (releaseMatch && impactMatch && sourceMatch) ? '' : 'none';
    }});
    document.getElementById('visibleCount').textContent =
      Array.from(document.querySelectorAll('.tool-card')).filter(c => c.style.display !== 'none').length;
  }});
}});
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, output_path)
    logger.info("Tools page generated → %s (%d items)", output_path, len(items))


def build() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_tools_page()


if __name__ == "__main__":
    build()

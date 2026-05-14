"""SNS成功者マインドダッシュボード生成

docs/sns_success.html を生成する。
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("ai-news.sns_dashboard")

JST = timezone(timedelta(hours=9))

CATEGORY_ICONS = {
    "マインドセット/思考法": "🧠",
    "習慣/ルーティン": "⏰",
    "潜在意識/引き寄せ": "✨",
    "SNS戦略/成長法": "📈",
    "FIRE/資産形成": "🔥",
    "副業/収益化": "💰",
    "人間関係/環境整備": "🤝",
    "自己啓発/メンタル": "💪",
    "その他": "💡",
}


def generate_sns_page(output_path: str) -> None:
    from sns_analyzer import load_all_sns_analyses
    import yaml

    config = {}
    try:
        with open(os.path.join(os.path.dirname(__file__) or ".", "config.yaml"), encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception:
        pass

    posts = load_all_sns_analyses()
    html = _render_sns_html(posts, config)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("SNS page generated → %s (%d posts)", output_path, len(posts))


def _render_sns_html(posts: list[dict], config: dict = None) -> str:
    config = config or {}
    now_jst = datetime.now(JST)
    now_str = now_jst.strftime("%Y-%m-%d %H:%M JST")

    try:
        _script_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, _script_dir)
        from utils import STATUS_BANNER_HTML as STATUS_BANNER  # noqa: F401
    except Exception:
        STATUS_BANNER = ""

    # テンプレートJSONを事前生成（f-string内でのネスト回避）
    raw_templates = config.get("post_templates", {}).get("templates", [])
    templates_js = json.dumps(
        [{"id": t["id"], "name": t["name"], "prompt_hint": t.get("prompt_hint", "")} for t in raw_templates],
        ensure_ascii=False,
    )

    by_category: dict[str, list[dict]] = {}
    for post in posts:
        cat = post.get("category") or "その他"
        by_category.setdefault(cat, []).append(post)

    jp_count = sum(1 for p in posts if p.get("is_japanese"))
    global_count = len(posts) - jp_count
    total = len(posts)

    sns_cfg = config.get("sns_success", {})
    min_followers = sns_cfg.get("min_followers", 5000)
    search_query_count = len(sns_cfg.get("search_queries", []))
    account_count = len(sns_cfg.get("accounts", []))
    cache_days = sns_cfg.get("cache_retention_days", 180)
    search_since_days = sns_cfg.get("search_since_days", 90)
    account_since_days = sns_cfg.get("account_since_days", 365)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SNS成功者マインド集</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0f1e; color: #e0e4f0; min-height: 100vh; }}
    header {{ background: linear-gradient(135deg, #0f1a35 0%, #1a0f35 100%); border-bottom: 1px solid #2a2a5a; padding: 20px 24px; }}
    .header-inner {{ max-width: 1100px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }}
    .header-title {{ font-size: 1.4rem; font-weight: 700; color: #a78bfa; }}
    .header-title span {{ font-size: 0.9rem; color: #888; margin-left: 10px; font-weight: 400; }}
    .nav-links {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .nav-links a {{ color: #7aa0d4; text-decoration: none; font-size: 0.85rem; padding: 4px 10px; border: 1px solid #2a4060; border-radius: 4px; }}
    .nav-links a:hover {{ background: #1e2050; }}
    .main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
    .stats-bar {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
    .stat-card {{ background: #111827; border: 1px solid #2a2a5a; border-radius: 10px; padding: 16px 20px; flex: 1; min-width: 140px; text-align: center; }}
    .stat-number {{ font-size: 2rem; font-weight: 700; color: #a78bfa; }}
    .stat-label {{ font-size: 0.8rem; color: #888; margin-top: 4px; }}
    .filter-bar {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; align-items: center; }}
    .filter-btn {{ background: #111827; border: 1px solid #2a2a5a; color: #aaa; padding: 6px 14px; border-radius: 20px; cursor: pointer; font-size: 0.85rem; transition: all 0.2s; }}
    .filter-btn.active, .filter-btn:hover {{ background: #a78bfa; color: #0a0f1e; border-color: #a78bfa; font-weight: 600; }}
    .filter-label {{ color: #666; font-size: 0.8rem; margin-right: 4px; }}
    .sort-bar {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; align-items: center; }}
    .sort-btn {{ background: #111827; border: 1px solid #2a2a5a; color: #aaa; padding: 5px 14px; border-radius: 6px; cursor: pointer; font-size: 0.82rem; transition: all 0.2s; }}
    .sort-btn.active {{ background: #1e1e40; color: #e0e4f0; border-color: #4a4a8a; font-weight: 600; }}
    .select-filters {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-left: auto; }}
    .select-group {{ display: flex; align-items: center; gap: 6px; font-size: 0.82rem; color: #888; }}
    .select-group select {{ background: #111827; border: 1px solid #2a2a5a; color: #e0e4f0; padding: 4px 10px; border-radius: 6px; font-size: 0.82rem; cursor: pointer; }}
    .filter-section {{ margin-bottom: 16px; }}
    .filter-section-label {{ font-size: 0.75rem; color: #666; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em; }}
    .cat-filter-grid {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .posts-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }}
    .post-card {{ background: #111827; border: 1px solid #2a2a5a; border-radius: 12px; padding: 16px; transition: border-color 0.2s, box-shadow 0.2s; }}
    .post-card:hover {{ border-color: #a78bfa; box-shadow: 0 0 16px rgba(167,139,250,0.15); }}
    .post-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; gap: 8px; flex-wrap: wrap; }}
    .post-category {{ font-size: 0.75rem; background: #1e1e40; color: #9d8ee0; padding: 3px 8px; border-radius: 12px; white-space: nowrap; flex-shrink: 0; }}
    .post-credibility {{ font-size: 0.78rem; color: #a78bfa; background: #1a0f35; padding: 3px 8px; border-radius: 12px; white-space: normal; word-break: break-word; max-width: 200px; line-height: 1.4; }}
    .post-summary {{ font-size: 0.97rem; font-weight: 700; color: #e0e4f0; margin-bottom: 6px; line-height: 1.5; }}
    .post-theme {{ font-size: 0.85rem; color: #a78bfa; margin-bottom: 8px; font-style: italic; }}
    .insights-list {{ margin: 8px 0; padding: 10px 12px; background: #0f172a; border-left: 3px solid #a78bfa; border-radius: 0 6px 6px 0; }}
    .insights-list li {{ font-size: 0.83rem; color: #c4b5fd; line-height: 1.7; list-style: none; padding-left: 1.2em; position: relative; }}
    .insights-list li::before {{ content: "→"; position: absolute; left: 0; color: #a78bfa; }}
    .post-body {{ font-size: 0.82rem; color: #94a3b8; background: #0a0f1e; border: 1px solid #1e2050; padding: 8px 12px; border-radius: 6px; margin: 8px 0; line-height: 1.6; white-space: pre-wrap; word-break: break-word; max-height: 120px; overflow: hidden; position: relative; }}
    .post-body.expanded {{ max-height: none; }}
    .post-body-toggle {{ font-size: 0.78rem; color: #7aa0d4; cursor: pointer; margin-top: 4px; display: block; text-align: right; }}
    .post-target {{ font-size: 0.78rem; color: #888; margin: 4px 0 8px; }}
    .post-footer {{ display: flex; justify-content: space-between; align-items: center; padding-top: 8px; border-top: 1px solid #1e2050; font-size: 0.78rem; color: #666; }}
    .post-footer a {{ color: #7aa0d4; text-decoration: none; }}
    .post-footer a:hover {{ text-decoration: underline; }}
    .engagement {{ display: flex; gap: 10px; }}
    .empty-state {{ text-align: center; padding: 60px 20px; color: #555; }}
    .empty-state .emoji {{ font-size: 3rem; margin-bottom: 16px; }}
    .criteria-box {{ background: #0f172a; border: 1px solid #2a2a5a; border-radius: 10px; padding: 14px 20px; margin-bottom: 20px; font-size: 0.82rem; color: #94a3b8; line-height: 1.8; }}
    .criteria-box strong {{ color: #a78bfa; }}
    .criteria-box .criteria-title {{ font-size: 0.88rem; font-weight: 700; color: #a78bfa; margin-bottom: 8px; }}
    footer {{ text-align: center; padding: 20px; color: #444; font-size: 0.8rem; border-top: 1px solid #111827; margin-top: 40px; }}
    .gen-post-btn {{ width: 100%; margin-top: 10px; background: #1e1e40; border: 1px solid #4a4a8a; color: #a78bfa; padding: 8px 0; border-radius: 8px; font-size: 0.83rem; cursor: pointer; transition: all 0.2s; }}
    .gen-post-btn:hover {{ background: #2a2a60; border-color: #a78bfa; }}
    .modal-overlay {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.75); z-index: 1000; align-items: center; justify-content: center; padding: 16px; }}
    .modal-overlay.open {{ display: flex; }}
    .modal-box {{ background: #111827; border: 1px solid #2a2a5a; border-radius: 14px; width: 100%; max-width: 700px; max-height: 90vh; overflow-y: auto; padding: 24px; position: relative; }}
    .modal-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; gap: 12px; }}
    .modal-title {{ font-size: 1rem; font-weight: 700; color: #a78bfa; line-height: 1.4; }}
    .modal-close {{ background: none; border: none; color: #666; font-size: 1.4rem; cursor: pointer; flex-shrink: 0; line-height: 1; }}
    .modal-close:hover {{ color: #aaa; }}
    .modal-source {{ font-size: 0.8rem; color: #94a3b8; margin-bottom: 16px; padding: 8px 12px; background: #0f172a; border-radius: 6px; line-height: 1.5; }}
    .modal-loading {{ text-align: center; padding: 32px; color: #888; font-size: 0.9rem; }}
    .modal-results {{ display: flex; flex-direction: column; gap: 14px; }}
    .result-card {{ background: #0f172a; border: 1px solid #2a2a5a; border-radius: 10px; padding: 14px; }}
    .result-tmpl-name {{ font-size: 0.78rem; color: #7c3aed; margin-bottom: 8px; font-weight: 600; }}
    .result-text {{ color: #e0e4f0; font-size: 0.9rem; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }}
    .result-footer {{ display: flex; align-items: center; justify-content: space-between; margin-top: 10px; flex-wrap: wrap; gap: 6px; }}
    .result-chars {{ font-size: 0.76rem; color: #888; }}
    .result-chars.over {{ color: #f59e0b; font-weight: bold; }}
    .copy-btn {{ background: #7c3aed; color: #fff; border: none; border-radius: 6px; padding: 5px 14px; font-size: 0.8rem; cursor: pointer; }}
    .copy-btn.copied {{ background: #10b981; }}
    .modal-error {{ color: #ef4444; font-size: 0.85rem; padding: 16px; text-align: center; }}
    @media (max-width: 640px) {{
      header {{ padding: 14px 12px; }}
      .header-title {{ font-size: 1.1rem; }}
      .nav-links {{ gap: 6px; }}
      .nav-links a {{ font-size: 0.78rem; padding: 3px 7px; }}
      .main {{ padding: 16px 10px; }}
      .stats-bar {{ gap: 8px; }}
      .stat-card {{ padding: 10px 12px; min-width: 100px; }}
      .stat-number {{ font-size: 1.5rem; }}
      .posts-grid {{ grid-template-columns: 1fr; gap: 12px; }}
      .post-card {{ padding: 12px; }}
    }}
  </style>
</head>
<body>
<header>
  <div class="header-inner">
    <div>
      <div class="header-title">🧠 SNS成功者マインド集 <span>Last updated: {now_str}</span></div>
    </div>
    <nav class="nav-links">
      <a href="index.html">📰 ニュース</a>
      <a href="money.html">🎬 マネタイズ事例</a>
      <a href="post_generator.html">✍️ 投稿ジェネレーター</a>
      <a href="buzz.html">🔥 バズりランキング</a>
      <a href="strategy.html">🎯 施策提案</a>
      <a href="hn.html">📡 英語一次情報</a>
    </nav>
  </div>
</header>

<div class="main">
  <div class="criteria-box">
    <div class="criteria-title">📋 収集・掲載基準</div>
    <strong>収集元：</strong>日英{search_query_count}種のキーワード検索＋追跡アカウント{account_count}件 &nbsp;|&nbsp;
    <strong>対象期間：</strong>検索は過去{search_since_days}日・追跡アカウントは過去{account_since_days}日 &nbsp;|&nbsp;
    <strong>フォロワー：</strong>{min_followers:,}人以上の投稿のみ採用 &nbsp;|&nbsp;
    <strong>判定：</strong>GeminiがSNS成功者の思考法・習慣・マインドとして有益な投稿を自動フィルタリング &nbsp;|&nbsp;
    <strong>蓄積期間：</strong>過去{cache_days}日分を継続収集
  </div>

  <div class="stats-bar">
    <div class="stat-card">
      <div class="stat-number">{total}</div>
      <div class="stat-label">総投稿数</div>
    </div>
    <div class="stat-card">
      <div class="stat-number">{jp_count}</div>
      <div class="stat-label">🇯🇵 日本語</div>
    </div>
    <div class="stat-card">
      <div class="stat-number">{global_count}</div>
      <div class="stat-label">🌍 海外</div>
    </div>
    <div class="stat-card">
      <div class="stat-number">{len(by_category)}</div>
      <div class="stat-label">カテゴリ数</div>
    </div>
  </div>

  <div class="sort-bar">
    <span class="filter-label">並べ替え：</span>
    <button class="sort-btn active" onclick="setSort('eng', this)">📈 エンゲ率順</button>
    <button class="sort-btn" onclick="setSort('date', this)">🕐 新着順</button>
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
        <label for="lengthSelect">本文量：</label>
        <select id="lengthSelect" onchange="applyFilters()">
          <option value="0">制限なし</option>
          <option value="280">280字以上</option>
          <option value="500">500字以上</option>
          <option value="1000">1000字以上</option>
          <option value="1500">1500字以上</option>
          <option value="2000">2000字以上</option>
        </select>
      </div>
    </div>
  </div>

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
      {"".join(f'<button class="filter-btn" onclick="filterCategory(\'{cat}\', this)">{CATEGORY_ICONS.get(cat, "💡")} {cat} <span style="opacity:0.6;font-size:0.78rem;">({len(items)})</span></button>' for cat, items in sorted(by_category.items(), key=lambda x: -len(x[1])))}
    </div>
  </div>

  <div class="posts-grid" id="postsGrid">
    {_render_all_posts(posts) if posts else _render_empty()}
  </div>
</div>

<footer>SNS成功者マインド集 — Xから自動収集し、GeminiがAI分析</footer>

<!-- 投稿文生成モーダル -->
<div class="modal-overlay" id="genModal" onclick="closeModalOnOverlay(event)">
  <div class="modal-box">
    <div class="modal-header">
      <div class="modal-title" id="modalTitle">投稿文を生成中...</div>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-source" id="modalSource"></div>
    <div id="modalBody">
      <div class="modal-loading">⏳ Geminiが6種類の投稿文を生成しています（約20秒）...</div>
    </div>
  </div>
</div>

<script>
const WORKER_URL = 'https://sns-post-generator.imokonoai.workers.dev';
const TEMPLATES = {templates_js};

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
  const grid = document.getElementById('postsGrid');
  const engMin = parseFloat(document.getElementById('engSelect').value) || 0;
  const lengthMin = parseInt(document.getElementById('lengthSelect').value || '0', 10);
  const allCards = Array.from(grid.querySelectorAll('.post-card'));

  const visible = allCards.filter(card => {{
    const catMatch = activeCategory === 'all' || card.dataset.category === activeCategory;
    const regionMatch = activeRegion === 'all' ||
      (activeRegion === 'jp' && card.dataset.jp === 'true') ||
      (activeRegion === 'global' && card.dataset.jp === 'false');
    const engMatch = parseFloat(card.dataset.eng || '0') >= engMin;
    const lengthMatch = parseInt(card.dataset.length || '0', 10) >= lengthMin;
    return catMatch && regionMatch && engMatch && lengthMatch;
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

function toggleBody(el) {{
  const body = el.previousElementSibling;
  if (body.classList.contains('expanded')) {{
    body.classList.remove('expanded');
    el.textContent = '続きを読む ▼';
  }} else {{
    body.classList.add('expanded');
    el.textContent = '閉じる ▲';
  }}
}}

async function openGenerator(btn) {{
  const postData = JSON.parse(btn.getAttribute('data-post').replace(/&quot;/g, '"').replace(/&#39;/g, "'"));
  const modal = document.getElementById('genModal');
  const modalTitle = document.getElementById('modalTitle');
  const modalSource = document.getElementById('modalSource');
  const modalBody = document.getElementById('modalBody');

  modalTitle.textContent = '✍️ 投稿文を生成中...';
  modalSource.innerHTML = `<strong>元ポスト:</strong> ${{postData.summary || postData.author_display}} &nbsp;@${{postData.author_display}} <a href="${{postData.url}}" target="_blank" rel="noopener" style="color:#7aa0d4;">ポストを見る →</a>`;
  modalBody.innerHTML = '<div class="modal-loading">⏳ Geminiが6種類の投稿文を生成しています（約20秒）...</div>';
  modal.classList.add('open');
  document.body.style.overflow = 'hidden';

  try {{
    const res = await fetch(WORKER_URL, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ post: postData, templates: TEMPLATES }}),
    }});
    if (!res.ok) {{
      const err = await res.json().catch(() => ({{}}));
      throw new Error(err.error || `HTTP ${{res.status}}`);
    }}
    const data = await res.json();
    const generated = data.generated || [];
    if (!generated.length) throw new Error('生成結果が空でした');

    modalTitle.textContent = '✍️ 6種の投稿文が生成されました';
    modalBody.innerHTML = '<div class="modal-results">' + generated.map((g, i) => {{
      const text = g.text || '';
      const chars = text.length;
      const overClass = chars > 140 ? 'over' : '';
      const textId = `rtext-${{i}}`;
      return `<div class="result-card">
        <div class="result-tmpl-name">${{g.template_name}}</div>
        <div class="result-text" id="${{textId}}">${{text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}</div>
        <div class="result-footer">
          <span class="result-chars ${{overClass}}">${{chars}}文字</span>
          <button class="copy-btn" onclick="copyResult(this,'${{textId}}')">コピー</button>
        </div>
      </div>`;
    }}).join('') + '</div>';
  }} catch(e) {{
    modalBody.innerHTML = `<div class="modal-error">エラー: ${{e.message}}</div>`;
  }}
}}

function closeModal() {{
  document.getElementById('genModal').classList.remove('open');
  document.body.style.overflow = '';
}}

function closeModalOnOverlay(e) {{
  if (e.target === document.getElementById('genModal')) closeModal();
}}

function copyResult(btn, textId) {{
  const el = document.getElementById(textId);
  if (!el) return;
  navigator.clipboard.writeText(el.innerText).then(() => {{
    btn.textContent = 'コピー済み✓';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = 'コピー'; btn.classList.remove('copied'); }}, 2000);
  }});
}}
</script>
{STATUS_BANNER}
</body>
</html>"""


def _render_all_posts(posts: list[dict]) -> str:
    def _eng_rate(p):
        likes = p.get("engagement", {}).get("likes", 0)
        followers = p.get("author_followers") or 1
        return likes / followers

    sorted_posts = sorted(posts, key=_eng_rate, reverse=True)
    return "".join(_render_post_card(p) for p in sorted_posts)


def _render_post_card(post: dict) -> str:
    category = post.get("category") or "その他"
    icon = CATEGORY_ICONS.get(category, "💡")
    summary = post.get("summary") or ""
    theme = post.get("mind_theme") or ""
    insights = post.get("key_insights") or []
    credibility = post.get("credibility") or ""
    target = post.get("target_audience") or ""
    is_jp = post.get("is_japanese", True)
    flag = "🇯🇵" if is_jp else "🌍"
    url = post.get("url") or "#"
    author = post.get("author_display") or post.get("author") or ""
    likes = post.get("engagement", {}).get("likes", 0)
    views = post.get("engagement", {}).get("views", 0)

    raw_date = post.get("published_at") or ""
    pub_date = ""
    date_val = ""
    if raw_date:
        try:
            dt = datetime.strptime(raw_date, "%a %b %d %H:%M:%S %z %Y")
            pub_date = dt.astimezone(JST).strftime("%Y/%m/%d")
            date_val = dt.strftime("%Y%m%d%H%M%S")
        except ValueError:
            pub_date = raw_date[:10].replace("-", "/")
            date_val = raw_date[:19].replace("-", "").replace(":", "").replace("T", "").replace(" ", "")

    followers = post.get("author_followers") or 1
    eng_rate = likes / followers

    raw_content = post.get("content") or ""
    content_length = len(raw_content)
    content_preview_limit = 400
    content_escaped = raw_content[:content_preview_limit].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    has_more = content_length > content_preview_limit

    insights_html = ""
    if insights:
        items_html = "".join(f"<li>{i}</li>" for i in insights[:3])
        insights_html = f'<ul class="insights-list">{items_html}</ul>'

    views_str = f"{views:,}" if views else ""
    credibility_html = f'<span class="post-credibility">⭐ {credibility}</span>' if credibility else ""
    target_html = f'<div class="post-target">👥 {target}</div>' if target else ""
    toggle_html = '<span class="post-body-toggle" onclick="toggleBody(this)">続きを読む ▼</span>' if has_more else ""

    # 投稿文生成ボタン用にポストデータをJSON化（HTMLエスケープ）
    post_data = {
        "id": post.get("id", ""),
        "author": post.get("author", ""),
        "author_display": author,
        "author_followers": post.get("author_followers", 0),
        "content": raw_content[:800],
        "summary": summary,
        "mind_theme": theme,
        "key_insights": insights,
        "url": url,
    }
    post_data_json = json.dumps(post_data, ensure_ascii=False).replace("'", "&#39;").replace('"', "&quot;")

    return f"""<div class="post-card" data-category="{category}" data-jp="{str(is_jp).lower()}" data-eng="{eng_rate:.6f}" data-date="{date_val}" data-length="{content_length}">
  <div class="post-header">
    <span class="post-category">{icon} {category}</span>
    {credibility_html}
  </div>
  <div class="post-summary">{summary}</div>
  {f'<div class="post-theme">💭 {theme}</div>' if theme else ''}
  {insights_html}
  {target_html}
  {f'<div class="post-body">{content_escaped}</div>{toggle_html}' if content_escaped else ''}
  <div class="post-footer">
    <span>{flag} @{author} · {pub_date}</span>
    <div class="engagement">
      {f'❤️ {likes:,}' if likes else ''}
      {f'👁 {views_str}' if views_str else ''}
      <a href="{url}" target="_blank" rel="noopener">ポストを見る →</a>
    </div>
  </div>
  <button class="gen-post-btn" onclick="openGenerator(this)" data-post="{post_data_json}">✍️ 投稿文を作る</button>
</div>"""


def _render_empty() -> str:
    return """<div class="empty-state" style="grid-column: 1/-1;">
  <div class="emoji">🧠</div>
  <p>まだデータがありません。<br>ワークフローを実行するとSNS成功者の知見が蓄積されます。</p>
</div>"""

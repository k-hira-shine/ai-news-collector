"""SNS投稿ジェネレーター

分析済みSNS成功者ポストを元に、テンプレートに沿った投稿文をGeminiで生成し
docs/post_generator.html として出力する。
"""

import json
import logging
import os
import random
from datetime import datetime, timezone

logger = logging.getLogger("ai-news.post_generator")

GENERATED_DIR_NAME = "generated_posts"


def _data_dir(*parts: str) -> str:
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    return os.path.join(base, *parts)


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_all_analyses() -> list[dict]:
    from sns_analyzer import load_all_sns_analyses
    return load_all_sns_analyses()


def _sample_posts(posts: list[dict], n: int) -> list[dict]:
    """エンゲ率上位の投稿から n 件をランダムサンプリング"""
    def _eng(p: dict) -> float:
        likes = p.get("engagement", {}).get("likes", 0)
        followers = p.get("author_followers") or 1
        return likes / followers

    sorted_posts = sorted(posts, key=_eng, reverse=True)
    pool = sorted_posts[:max(n * 3, 30)]
    return random.sample(pool, min(n, len(pool)))


def _generate_posts_for_template(
    template: dict,
    source_posts: list[dict],
    config: dict,
    api_key: str,
) -> list[dict]:
    """1テンプレート分の投稿文をGeminiで生成して返す"""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    model_name = config.get("analysis", {}).get("models", {}).get(
        "stage1_filter", "gemini-2.5-flash"
    )
    max_chars = config.get("post_templates", {}).get("max_chars", 140)
    n = config.get("post_templates", {}).get("posts_per_template", 5)

    sampled = _sample_posts(source_posts, config.get("post_templates", {}).get("sample_size", 20))

    posts_text = ""
    for p in sampled:
        insights = "\n".join(f"  - {i}" for i in (p.get("key_insights") or []))
        posts_text += f"""
[ID: {p['id']}]
著者: @{p.get('author_display') or p.get('author', '')} (フォロワー {p.get('author_followers', 0):,}人)
URL: {p.get('url', '')}
要約: {p.get('summary', '')}
テーマ: {p.get('mind_theme', '')}
key_insights:
{insights or '  (なし)'}
本文（抜粋）:
{(p.get('content') or '')[:500]}
---"""

    prompt = f"""{template['prompt_hint']}

## 条件
- 日本語で書くこと
- 1投稿あたり{max_chars}字以内
- {n}件の投稿文を生成すること
- 各投稿には元ポストのID（[ID: ...]の値）を必ず対応させること
- コピーしてそのままXに投稿できる形にすること

## 元となるSNS成功者ポスト一覧
{posts_text}
"""

    schema = {
        "type": "object",
        "properties": {
            "generated": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_post_id": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["source_post_id", "text"],
                },
            }
        },
        "required": ["generated"],
    }

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": schema,
                "http_options": types.HttpOptions(timeout=120_000),
            },
        )
        result = json.loads(response.text)
        generated = result.get("generated", [])

        id_to_post = {p["id"]: p for p in sampled}
        output = []
        for g in generated:
            source_id = g.get("source_post_id", "")
            text = (g.get("text") or "").strip()
            if not text:
                continue
            source = id_to_post.get(source_id, {})
            output.append({
                "template_id": template["id"],
                "template_name": template["name"],
                "text": text,
                "char_count": len(text),
                "source_post_id": source_id,
                "source_url": source.get("url", ""),
                "source_author": source.get("author_display") or source.get("author", ""),
                "source_summary": source.get("summary", ""),
            })
        logger.info(
            "Template [%s]: generated %d posts", template["id"], len(output)
        )
        return output
    except Exception as e:
        logger.error("Template [%s] generation failed: %s", template["id"], e)
        return []


def generate_posts(config: dict) -> list[dict]:
    """全テンプレート分の投稿文を生成して data/generated_posts/ に保存"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — skipping post generation")
        return []

    try:
        from google import genai  # noqa: F401
    except ImportError:
        logger.warning("google-genai not installed")
        return []

    all_posts = _load_all_analyses()
    if not all_posts:
        logger.warning("No analyzed posts found")
        return []

    templates = config.get("post_templates", {}).get("templates", [])
    if not templates:
        logger.warning("No post_templates configured")
        return []

    logger.info(
        "Generating posts: %d templates × %d posts, from %d analyzed posts",
        len(templates),
        config.get("post_templates", {}).get("posts_per_template", 5),
        len(all_posts),
    )

    all_generated: list[dict] = []
    for template in templates:
        results = _generate_posts_for_template(template, all_posts, config, api_key)
        all_generated.extend(results)

    if all_generated:
        _save_generated(all_generated)
    return all_generated


def _save_generated(posts: list[dict]) -> str:
    out_dir = _data_dir(GENERATED_DIR_NAME)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{_today_str()}.json")
    existing: list[dict] = []
    if os.path.exists(path):
        try:
            existing = json.loads(open(path, encoding="utf-8").read())
        except Exception:
            existing = []
    merged = existing + posts
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    logger.info("Saved %d generated posts → %s", len(merged), path)
    return path


def _load_all_generated() -> list[dict]:
    out_dir = _data_dir(GENERATED_DIR_NAME)
    if not os.path.isdir(out_dir):
        return []
    posts: list[dict] = []
    for fname in sorted(os.listdir(out_dir), reverse=True):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(out_dir, fname)
        try:
            posts.extend(json.loads(open(path, encoding="utf-8").read()))
        except Exception:
            continue
    return posts


def generate_post_generator_page(output_path: str, config: dict) -> None:
    """docs/post_generator.html を生成する（localStorage に保存された生成済み投稿を表示）"""
    templates = config.get("post_templates", {}).get("templates", [])
    template_names_js = json.dumps(
        {t["id"]: t["name"] for t in templates},
        ensure_ascii=False,
    )
    from zoneinfo import ZoneInfo
    now_jst = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y/%m/%d %H:%M") + " JST"

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>生成済み投稿ストック</title>
<style>
  :root {{
    --bg: #0a0f1e; --surface: #131929; --card: #1a2236;
    --accent: #a78bfa; --accent2: #7c3aed; --text: #e2e8f0;
    --muted: #94a3b8; --border: #2d3748; --success: #10b981;
    --warn: #f59e0b; --error: #ef4444;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, sans-serif; min-height: 100vh; padding-top: 48px; }}
  .topnav {{ position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: #0a0f1eee; backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); display: flex; gap: 0.4rem; justify-content: center; flex-wrap: wrap; padding: 6px 12px; }}
  .topnav a {{ display: inline-block; padding: 4px 12px; background: var(--card); border-radius: 6px; color: var(--muted); text-decoration: none; font-size: 0.82rem; white-space: nowrap; }}
  .topnav a:hover {{ color: var(--accent); background: rgba(167,139,250,0.1); }}
  .topnav a.active {{ background: var(--accent2); color: #fff; }}
  header {{ background: linear-gradient(135deg, #1e1b4b, #0a0f1e); padding: 24px 32px; border-bottom: 1px solid var(--border); }}
  header h1 {{ font-size: 1.6rem; color: var(--accent); }}
  header p {{ color: var(--muted); font-size: 0.85rem; margin-top: 4px; }}
  nav a.active {{ color: var(--accent); background: rgba(167,139,250,0.15); }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
  .toolbar {{ display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }}
  .stat-chip {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 8px 16px; font-size: 0.85rem; color: var(--muted); }}
  .stat-chip strong {{ color: var(--accent); }}
  .clear-btn {{ background: none; border: 1px solid #ef4444; color: #ef4444; border-radius: 8px; padding: 7px 16px; font-size: 0.82rem; cursor: pointer; }}
  .clear-btn:hover {{ background: rgba(239,68,68,0.1); }}
  .tabs {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
  .tab-btn {{ background: var(--card); border: 1px solid var(--border); color: var(--muted); padding: 7px 14px; border-radius: 10px; cursor: pointer; font-size: 0.82rem; transition: all 0.2s; display: flex; align-items: center; gap: 6px; max-width: 200px; }}
  .tab-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
  .tab-btn.active {{ background: var(--accent2); border-color: var(--accent); color: #fff; }}
  .tab-label {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .tab-count {{ background: rgba(255,255,255,0.15); border-radius: 10px; padding: 1px 7px; font-size: 0.74rem; flex-shrink: 0; }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}
  .source-header {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; }}
  .source-summary {{ font-size: 0.9rem; color: var(--text); font-weight: 600; margin-bottom: 4px; }}
  .source-meta {{ font-size: 0.78rem; color: var(--muted); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
  .cards-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }}
  .gen-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; display: flex; flex-direction: column; gap: 10px; position: relative; transition: opacity 0.2s; }}
  .gen-card.posted {{ opacity: 0.4; border-color: var(--success); }}
  .gen-card.posted .tmpl-label::after {{ content: ' ✓ 投稿済み'; color: var(--success); }}
  .tmpl-label {{ font-size: 0.74rem; color: var(--accent); font-weight: 600; }}
  .gen-card-date {{ font-size: 0.74rem; color: var(--muted); }}
  .gen-text {{ color: var(--text); font-size: 0.93rem; line-height: 1.75; white-space: pre-wrap; word-break: break-word; }}
  .gen-footer {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; border-top: 1px solid var(--border); padding-top: 8px; }}
  .char-count {{ font-size: 0.76rem; color: var(--muted); }}
  .char-count.over {{ color: var(--warn); font-weight: bold; }}
  .gen-actions {{ display: flex; gap: 6px; align-items: center; }}
  .copy-btn {{ background: var(--accent2); color: #fff; border: none; border-radius: 6px; padding: 5px 12px; font-size: 0.8rem; cursor: pointer; transition: background 0.2s; }}
  .copy-btn.copied {{ background: var(--success); }}
  .posted-btn {{ background: none; border: 1px solid var(--border); color: var(--muted); border-radius: 6px; padding: 4px 10px; font-size: 0.78rem; cursor: pointer; transition: all 0.2s; }}
  .posted-btn:hover {{ border-color: var(--success); color: var(--success); }}
  .posted-btn.active {{ background: rgba(16,185,129,0.15); border-color: var(--success); color: var(--success); }}
  .del-btn {{ background: none; border: 1px solid var(--border); color: var(--muted); border-radius: 6px; padding: 4px 10px; font-size: 0.78rem; cursor: pointer; }}
  .del-btn:hover {{ border-color: var(--error); color: var(--error); }}
  .source-link {{ color: var(--accent); font-size: 0.77rem; text-decoration: none; }}
  .source-link:hover {{ text-decoration: underline; }}
  .gen-source {{ font-size: 0.76rem; color: var(--muted); }}
  .empty-msg {{ text-align: center; padding: 60px 20px; color: var(--muted); }}
  .empty-msg .icon {{ font-size: 3rem; margin-bottom: 16px; }}
  .empty-msg a {{ color: var(--accent); text-decoration: none; }}
  .empty-msg a:hover {{ text-decoration: underline; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 32px; }}
</style>
</head>
<body>
<nav class="topnav">
  <a class="nav-link" href="home.html">🏠 ホーム</a>
  <a href="index.html">📰 ニュース</a>
  <a href="strategy.html">🎯 施策提案</a>
  <a href="buzz.html">🔥 バズりランキング</a>
  <a href="money.html">🎬 マネタイズ</a>
  <a href="sns_success.html">🧠 SNS成功者</a>
  <a href="post_generator.html" class="active">✍️ 投稿ストック</a>
  <a href="tools.html">🔧 ツール追跡</a>
  <a href="reviews.html">📋 使ってみた</a>
</nav>
<header>
  <h1>📋 生成済み投稿ストック</h1>
  <p><a href="sns_success.html" style="color:var(--accent);">SNS成功者マインド</a> で生成した投稿文の保管場所 &nbsp;|&nbsp; 更新: {now_jst}</p>
</header>
<div class="container">
  <div class="toolbar">
    <div class="stat-chip">保存済み: <strong id="totalCount">0</strong> 件</div>
    <button class="clear-btn" onclick="clearAll()">🗑 全削除</button>
  </div>
  <div class="tabs" id="tabBar"></div>
  <div id="tabContents"></div>
</div>
<footer>投稿文はAI生成です。投稿前に内容を確認してください。</footer>
<script>
const LS_POSTS_KEY = 'sns_generated_posts';
const LS_POSTED_KEY = 'sns_posted_ids';
const TEMPLATE_NAMES = {template_names_js};

function loadPosts() {{
  try {{ return JSON.parse(localStorage.getItem(LS_POSTS_KEY) || '[]'); }} catch {{ return []; }}
}}
function savePosts(posts) {{
  localStorage.setItem(LS_POSTS_KEY, JSON.stringify(posts));
}}
function getPostedIds() {{
  try {{ return new Set(JSON.parse(localStorage.getItem(LS_POSTED_KEY) || '[]')); }} catch {{ return new Set(); }}
}}
function togglePosted(id, cardEl, btn) {{
  const ids = getPostedIds();
  if (ids.has(id)) {{
    ids.delete(id);
    cardEl.classList.remove('posted');
    btn.classList.remove('active');
    btn.textContent = '投稿済みにする';
  }} else {{
    ids.add(id);
    cardEl.classList.add('posted');
    btn.classList.add('active');
    btn.textContent = '✓ 投稿済み';
  }}
  localStorage.setItem(LS_POSTED_KEY, JSON.stringify([...ids]));
}}

function deletePost(id) {{
  const posts = loadPosts().filter(p => p.id !== id);
  savePosts(posts);
  render();
}}

function clearAll() {{
  if (!confirm('保存済みの投稿文をすべて削除しますか？')) return;
  localStorage.removeItem(LS_POSTS_KEY);
  render();
}}

function copyText(btn, text) {{
  navigator.clipboard.writeText(text).then(() => {{
    btn.textContent = 'コピー済み✓';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = 'コピー'; btn.classList.remove('copied'); }}, 2000);
  }});
}}

function formatDate(iso) {{
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('ja-JP', {{ month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }});
}}

function esc(s) {{
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

function render() {{
  const posts = loadPosts();
  document.getElementById('totalCount').textContent = posts.length;

  const tabBar = document.getElementById('tabBar');
  const tabContents = document.getElementById('tabContents');

  if (!posts.length) {{
    tabBar.innerHTML = '';
    tabContents.innerHTML = `<div class="empty-msg"><div class="icon">📭</div><p><a href="sns_success.html">SNS成功者マインド</a> のポストで「✍️ 投稿文を作る」を押すと、ここに保存されます。</p></div>`;
    return;
  }}

  // 元ポストIDでグループ化（生成時刻降順）
  const bySource = {{}};
  posts.forEach(p => {{
    const sid = p.source_post_id || 'unknown';
    if (!bySource[sid]) bySource[sid] = {{ posts: [], meta: p }};
    bySource[sid].posts.push(p);
  }});

  // 元ポストを生成日時の新しい順に並べる
  const sourceIds = Object.keys(bySource).sort((a, b) => {{
    const ta = bySource[a].meta.created_at || '';
    const tb = bySource[b].meta.created_at || '';
    return tb.localeCompare(ta);
  }});

  tabBar.innerHTML = sourceIds.map((sid, i) => {{
    const meta = bySource[sid].meta;
    const label = (meta.source_summary || meta.source_author || sid).slice(0, 18) + ((meta.source_summary || '').length > 18 ? '…' : '');
    const count = bySource[sid].posts.length;
    const active = i === 0 ? ' active' : '';
    return `<button class="tab-btn${{active}}" id="tab-btn-${{i}}" onclick="showTab(${{i}})">
      <span class="tab-label">${{esc(label)}}</span>
      <span class="tab-count">${{count}}</span>
    </button>`;
  }}).join('');

  tabContents.innerHTML = sourceIds.map((sid, i) => {{
    const group = bySource[sid];
    const meta = group.meta;
    const active = i === 0 ? ' active' : '';
    const srcLink = meta.source_url ? `<a class="source-link" href="${{esc(meta.source_url)}}" target="_blank" rel="noopener">元ポストを見る →</a>` : '';
    const sourceInfo = `<div class="source-header">
      <div class="source-summary">${{esc((meta.source_summary || '').slice(0, 80))}}${{(meta.source_summary || '').length > 80 ? '…' : ''}}</div>
      <div class="source-meta">@${{esc(meta.source_author || '')}} &nbsp;·&nbsp; ${{formatDate(meta.created_at)}} &nbsp; ${{srcLink}}</div>
    </div>`;

    // テンプレート定義順に並べ替え
    const tmplOrder = Object.keys(TEMPLATE_NAMES);
    const sorted = group.posts.slice().sort((a, b) => {{
      return tmplOrder.indexOf(a.template_id) - tmplOrder.indexOf(b.template_id);
    }});

    const postedIds = getPostedIds();
    const cards = sorted.map(p => {{
      const text = p.text || '';
      const chars = p.char_count || text.length;
      const overClass = chars > 140 ? ' over' : '';
      const textJson = JSON.stringify(text);
      const isPosted = postedIds.has(p.id);
      const cardId = 'card-' + p.id.replace(/[^a-zA-Z0-9]/g, '_');
      return `<div class="gen-card${{isPosted ? ' posted' : ''}}" id="${{cardId}}">
  <div class="tmpl-label">${{esc(p.template_name || p.template_id)}}</div>
  <div class="gen-text">${{esc(text)}}</div>
  <div class="gen-footer">
    <span class="char-count${{overClass}}">${{chars}}文字</span>
    <div class="gen-actions">
      <button class="copy-btn" onclick="copyText(this, ${{textJson}})">コピー</button>
      <button class="posted-btn${{isPosted ? ' active' : ''}}" onclick="togglePosted('${{p.id}}', document.getElementById('${{cardId}}'), this)">${{isPosted ? '✓ 投稿済み' : '投稿済みにする'}}</button>
      <button class="del-btn" onclick="deletePost('${{p.id}}')">削除</button>
    </div>
  </div>
</div>`;
    }}).join('');

    return `<div class="tab-content${{active}}" id="tab-${{i}}">${{sourceInfo}}<div class="cards-grid">${{cards}}</div></div>`;
  }}).join('');
}}

function showTab(i) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  const btn = document.getElementById('tab-btn-' + i);
  const content = document.getElementById('tab-' + i);
  if (btn) btn.classList.add('active');
  if (content) content.classList.add('active');
}}

render();
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, output_path)
    logger.info("Post generator page (stock) generated → %s", output_path)

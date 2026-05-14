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


WORKER_URL = "https://sns-post-generator.imokonoai.workers.dev"


def generate_post_generator_page(output_path: str, config: dict) -> None:
    """docs/post_generator.html を生成する（Cloudflare Worker経由でリアルタイム生成）"""
    templates = config.get("post_templates", {}).get("templates", [])
    sample_size = config.get("post_templates", {}).get("sample_size", 20)

    # 分析済みポストをサンプリングしてJSに埋め込む
    all_analyzed = _load_all_analyses()
    sample_posts = _sample_posts(all_analyzed, sample_size) if all_analyzed else []

    # JSに渡すポストデータ（必要なフィールドだけ）
    posts_for_js = []
    for p in sample_posts:
        posts_for_js.append({
            "id": p.get("id", ""),
            "author": p.get("author", ""),
            "author_display": p.get("author_display") or p.get("author", ""),
            "author_followers": p.get("author_followers", 0),
            "content": (p.get("content") or "")[:500],
            "summary": p.get("summary", ""),
            "mind_theme": p.get("mind_theme", ""),
            "key_insights": p.get("key_insights") or [],
            "url": p.get("url", ""),
        })

    posts_json = json.dumps(posts_for_js, ensure_ascii=False)
    templates_json = json.dumps([
        {"id": t["id"], "name": t["name"], "description": t.get("description", ""), "prompt_hint": t.get("prompt_hint", "")}
        for t in templates
    ], ensure_ascii=False)

    now_jst = datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M") + " JST"

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SNS投稿ジェネレーター</title>
<style>
  :root {{
    --bg: #0a0f1e; --surface: #131929; --card: #1a2236;
    --accent: #a78bfa; --accent2: #7c3aed; --text: #e2e8f0;
    --muted: #94a3b8; --border: #2d3748; --success: #10b981;
    --warn: #f59e0b; --error: #ef4444;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, sans-serif; min-height: 100vh; }}
  header {{ background: linear-gradient(135deg, #1e1b4b, #0a0f1e); padding: 24px 32px; border-bottom: 1px solid var(--border); }}
  header h1 {{ font-size: 1.6rem; color: var(--accent); }}
  header p {{ color: var(--muted); font-size: 0.85rem; margin-top: 4px; }}
  nav {{ display: flex; gap: 8px; padding: 12px 32px; background: var(--surface); border-bottom: 1px solid var(--border); flex-wrap: wrap; }}
  nav a {{ color: var(--muted); text-decoration: none; font-size: 0.85rem; padding: 4px 10px; border-radius: 6px; }}
  nav a:hover {{ color: var(--accent); background: rgba(167,139,250,0.1); }}
  nav a.active {{ color: var(--accent); background: rgba(167,139,250,0.15); }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
  .tmpl-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; margin-bottom: 32px; }}
  .tmpl-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; display: flex; flex-direction: column; gap: 12px; }}
  .tmpl-card:hover {{ border-color: var(--accent); }}
  .tmpl-name {{ font-size: 1rem; font-weight: 600; color: var(--accent); }}
  .tmpl-desc {{ font-size: 0.83rem; color: var(--muted); line-height: 1.5; }}
  .gen-btn {{ background: var(--accent2); color: #fff; border: none; border-radius: 8px; padding: 10px 20px; font-size: 0.9rem; cursor: pointer; width: 100%; transition: opacity 0.2s; }}
  .gen-btn:hover {{ opacity: 0.85; }}
  .gen-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .result-area {{ margin-top: 12px; display: none; flex-direction: column; gap: 10px; }}
  .result-area.visible {{ display: flex; }}
  .gen-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 14px; display: flex; flex-direction: column; gap: 8px; }}
  .gen-text {{ color: var(--text); font-size: 0.92rem; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }}
  .gen-footer {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }}
  .char-count {{ font-size: 0.76rem; color: var(--muted); }}
  .char-count.over {{ color: var(--warn); font-weight: bold; }}
  .gen-actions {{ display: flex; gap: 8px; align-items: center; }}
  .copy-btn {{ background: var(--accent2); color: #fff; border: none; border-radius: 6px; padding: 5px 12px; font-size: 0.8rem; cursor: pointer; }}
  .copy-btn.copied {{ background: var(--success); }}
  .source-link {{ color: var(--accent); font-size: 0.78rem; text-decoration: none; }}
  .source-link:hover {{ text-decoration: underline; }}
  .gen-source {{ font-size: 0.76rem; color: var(--muted); border-top: 1px solid var(--border); padding-top: 6px; }}
  .loading {{ text-align: center; color: var(--muted); font-size: 0.85rem; padding: 16px; }}
  .error-msg {{ color: var(--error); font-size: 0.85rem; padding: 8px; }}
  .info-bar {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; margin-bottom: 24px; font-size: 0.83rem; color: var(--muted); }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 32px; }}
</style>
</head>
<body>
<header>
  <h1>✍️ SNS投稿ジェネレーター</h1>
  <p>SNS成功者の知見を元にAIがリアルタイムで投稿文を生成 &nbsp;|&nbsp; ページ更新: {now_jst}</p>
</header>
<nav>
  <a href="index.html">📰 ニュース</a>
  <a href="sns_success.html">🧠 SNS成功者マインド</a>
  <a href="money.html">🎬 マネタイズ事例</a>
  <a href="post_generator.html" class="active">✍️ 投稿ジェネレーター</a>
</nav>
<div class="container">
  <div class="info-bar">
    参考ポスト: <strong>{len(sample_posts)}</strong>件 &nbsp;|&nbsp; テンプレート: <strong>{len(templates)}</strong>種 &nbsp;|&nbsp; 生成ボタンを押すとAIがその場で投稿文を作ります（約20秒）
  </div>
  <div class="tmpl-grid" id="tmplGrid"></div>
</div>
<footer>生成文はAIによるものです。投稿前に内容を確認してください。</footer>
<script>
const WORKER_URL = '{WORKER_URL}';
const POSTS = {posts_json};
const TEMPLATES = {templates_json};

function renderTemplates() {{
  const grid = document.getElementById('tmplGrid');
  TEMPLATES.forEach(tmpl => {{
    const card = document.createElement('div');
    card.className = 'tmpl-card';
    card.id = 'card-' + tmpl.id;
    card.innerHTML = `
      <div class="tmpl-name">${{tmpl.name}}</div>
      <div class="tmpl-desc">${{tmpl.description}}</div>
      <button class="gen-btn" onclick="generate('${{tmpl.id}}')">✨ 生成する</button>
      <div class="result-area" id="result-${{tmpl.id}}"></div>
    `;
    grid.appendChild(card);
  }});
}}

async function generate(templateId) {{
  const tmpl = TEMPLATES.find(t => t.id === templateId);
  if (!tmpl) return;

  const btn = document.querySelector(`#card-${{templateId}} .gen-btn`);
  const resultArea = document.getElementById('result-' + templateId);

  btn.disabled = true;
  btn.textContent = '生成中...';
  resultArea.className = 'result-area visible';
  resultArea.innerHTML = '<div class="loading">⏳ Geminiが生成中です（約20秒）...</div>';

  try {{
    const res = await fetch(WORKER_URL, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        template_id: tmpl.id,
        template_name: tmpl.name,
        prompt_hint: tmpl.prompt_hint,
        posts: POSTS,
      }}),
    }});

    if (!res.ok) {{
      const err = await res.json().catch(() => ({{}}));
      throw new Error(err.error || `HTTP ${{res.status}}`);
    }}

    const data = await res.json();
    const generated = data.generated || [];

    if (generated.length === 0) {{
      resultArea.innerHTML = '<div class="error-msg">生成に失敗しました。もう一度お試しください。</div>';
      return;
    }}

    resultArea.innerHTML = generated.map((g, i) => {{
      const text = g.text || '';
      const chars = text.length;
      const overClass = chars > 140 ? 'over' : '';
      const srcLink = g.source_url ? `<a class="source-link" href="${{g.source_url}}" target="_blank" rel="noopener">元ポストを見る →</a>` : '';
      const srcInfo = g.source_summary ? `<div class="gen-source">参考: ${{g.source_summary.slice(0, 60)}}${{g.source_summary.length > 60 ? '...' : ''}} @${{g.source_author}}</div>` : '';
      const textId = `gen-text-${{templateId}}-${{i}}`;
      return `
        <div class="gen-card">
          <div class="gen-text" id="${{textId}}">${{text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}}</div>
          <div class="gen-footer">
            <span class="char-count ${{overClass}}">${{chars}}文字</span>
            <div class="gen-actions">
              <button class="copy-btn" onclick="copyText(this, '${{textId}}')">コピー</button>
              ${{srcLink}}
            </div>
          </div>
          ${{srcInfo}}
        </div>`;
    }}).join('');

  }} catch (e) {{
    resultArea.innerHTML = `<div class="error-msg">エラー: ${{e.message}}</div>`;
  }} finally {{
    btn.disabled = false;
    btn.textContent = '✨ もう一度生成';
  }}
}}

function copyText(btn, elementId) {{
  const el = document.getElementById(elementId);
  if (!el) return;
  navigator.clipboard.writeText(el.innerText).then(() => {{
    btn.textContent = 'コピー済み✓';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = 'コピー'; btn.classList.remove('copied'); }}, 2000);
  }});
}}

renderTemplates();
</script>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp = output_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, output_path)
    logger.info("Post generator page generated → %s (%d source posts embedded)", output_path, len(sample_posts))

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
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

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
    "reddit": "🔴",
    "hn": "🔶",
    "arxiv": "📄",
}

FAMILY_LABELS = {
    "gemini": ("✨ Gemini", "#4285f4"),
    "claude": ("🟠 Claude", "#d97757"),
    "chatgpt": ("💬 ChatGPT", "#10a37f"),
    "other": ("📌 その他", "#64748b"),
}



def _infer_tool_family(item: dict) -> str | None:
    """分析に tool_family が無い旧データ向け。ツール名→タイトル→本文の順で判定。
    ソースラベル（例: Anthropic Blog）も強いシグナルとして使う。
    """
    tool_name = (item.get("tool_name") or "").lower()
    source_label = (item.get("source_label") or "").lower()
    title = (item.get("title") or "").lower()
    summary = (item.get("summary_ja") or "").lower()
    body = (item.get("content") or "")[:400].lower()

    # ── ツール名・ソースラベルで確定（最優先）──────────────
    if any(k in tool_name for k in ("claude", "anthropic")):
        return "claude"
    if any(k in tool_name for k in ("gemini", "google ai studio")):
        return "gemini"
    if any(k in tool_name for k in ("chatgpt", "gpt-", "gpt ")):
        return "chatgpt"

    if "anthropic" in source_label:
        return "claude"
    if "openai" in source_label:
        return "chatgpt"
    if "google ai" in source_label:
        return "gemini"

    # ── タイトル・要約・本文（弱いシグナル、複合判定）──────
    full = f"{title} {summary} {body}"
    claude_score = sum(1 for k in ("claude", "anthropic", "クロード") if k in full)
    gemini_score = sum(1 for k in ("gemini", "ジェミニ", "google ai studio") if k in full)
    chatgpt_score = sum(1 for k in ("chatgpt", "openai", "gpt-", "chat gpt") if k in full)

    best = max(claude_score, gemini_score, chatgpt_score)
    if best == 0:
        return None
    if claude_score == best:
        return "claude"
    if gemini_score == best:
        return "gemini"
    return "chatgpt"


def _resolve_tool_family(item: dict) -> str | None:
    f = (item.get("tool_family") or "").strip().lower()
    if f in ("gemini", "claude", "chatgpt"):
        return f
    if f == "other":
        return None
    return _infer_tool_family(item)


def load_all_items(days: int = 30) -> list[dict]:
    """data/tools/ から直近 days 日分を全件ロード（分析済みのみ、ファミリー解決済み）"""
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
                    if not obj.get("tool_name"):
                        continue
                    enriched = dict(obj)
                    enriched["tool_family"] = _resolve_tool_family(obj) or "other"
                    items.append(enriched)
                except Exception:
                    continue
    return items


AI_KEYWORDS = {
    "ai", "gpt", "llm", "claude", "gemini", "openai", "anthropic", "deepmind",
    "llama", "mistral", "copilot", "cursor", "chatgpt", "bard", "cohere",
    "hugging face", "huggingface", "stable diffusion", "midjourney", "dall-e",
    "whisper", "sora", "grok", "perplexity", "notion ai", "github copilot",
    "agent", "rag", "embedding", "transformer", "diffusion", "generative",
    "machine learning", "deep learning", "neural", "nlp", "computer vision",
    "multimodal", "foundation model", "language model", "image generation",
    "text generation", "vector", "fine-tun", "prompt", "inference",
    "生成ai", "大規模言語", "aiエージェント", "機械学習",
}

def _is_ai_tool(item: dict) -> bool:
    """ツール名・サマリー・タイトルのキーワードでAI関連かを判定する"""
    if item.get("is_ai_tool") is not None:
        return bool(item["is_ai_tool"])
    text = " ".join([
        (item.get("tool_name") or ""),
        (item.get("summary_ja") or ""),
        (item.get("title") or ""),
        (item.get("content") or "")[:200],
    ]).lower()
    return any(kw in text for kw in AI_KEYWORDS)


def _fmt_date(iso: str) -> str:
    if not iso:
        return ""
    from zoneinfo import ZoneInfo
    JST = ZoneInfo("Asia/Tokyo")
    # ISO 8601形式
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(JST).strftime("%Y/%m/%d %H:%M")
    except ValueError:
        pass
    # Twitter形式: "Wed May 13 19:50:53 +0000 2026"
    try:
        dt = datetime.strptime(iso, "%a %b %d %H:%M:%S %z %Y")
        return dt.astimezone(JST).strftime("%Y/%m/%d %H:%M")
    except ValueError:
        pass
    return iso[:10]


def _modal_cards(items: list[dict]) -> str:
    """モーダル内に表示する個別カードのHTML"""
    impact_order = {"high": 0, "medium": 1, "low": 2}
    items_by_date = sorted(items, key=lambda x: (x.get("published_at") or x.get("analyzed_at") or ""), reverse=True)
    html = ""
    for item in items_by_date:
        rt = item.get("release_type") or "その他"
        rt_icon = RELEASE_TYPE_ICONS.get(rt, "📌")
        imp = item.get("impact") or "low"
        imp_label, imp_color = IMPACT_LABELS.get(imp, ("⚪ 参考", "#64748b"))
        src = item.get("source") or "rss"
        src_icon = SOURCE_ICONS.get(src, "📰")
        src_label = escape(item.get("source_label") or src)
        age = _fmt_date(item.get("published_at") or item.get("analyzed_at") or "")
        url = escape(item.get("url") or "#")
        title = escape(item.get("title") or "")
        summary = escape(item.get("summary_ja") or "")
        html += f"""<div class="modal-card">
  <div class="tool-name-row">
    <span class="release-badge">{rt_icon} {escape(rt)}</span>
    <span class="impact-badge" style="color:{imp_color}">{imp_label}</span>
  </div>
  <div class="source-age" style="margin:6px 0 4px">
    <span class="source-label">{src_icon} {src_label}</span>
    <span class="age">{age}</span>
  </div>
  {f'<div class="summary-ja" style="margin-bottom:6px">{summary}</div>' if summary else ''}
  <a href="{url}" target="_blank" rel="noopener" class="article-link">{title[:80]+('…' if len(title)>80 else '') or '記事を見る'} →</a>
</div>"""
    return html


def _tool_card_group(items: list[dict]) -> str:
    """同一ツール名の記事群を1枚のカードにまとめる。複数記事はモーダルで展開。"""
    impact_order = {"high": 0, "medium": 1, "low": 2}
    items_by_date = sorted(items, key=lambda x: (x.get("published_at") or x.get("analyzed_at") or ""), reverse=True)
    rep = items_by_date[0]

    tool_name = escape(rep.get("tool_name") or "")
    fam = rep.get("tool_family") or "other"
    fam_short, fam_color = FAMILY_LABELS.get(fam, FAMILY_LABELS["other"])
    fam_label_esc = escape(fam_short)
    best_impact = min((x.get("impact", "low") for x in items), key=lambda i: impact_order.get(i, 2))
    impact_label, impact_color = IMPACT_LABELS.get(best_impact, ("⚪ 参考", "#64748b"))
    release_type = rep.get("release_type") or "その他"
    release_icon = RELEASE_TYPE_ICONS.get(release_type, "📌")
    summary_ja = escape(rep.get("summary_ja") or "")
    data_ai = "ai" if _is_ai_tool(rep) else "non-ai"
    count = len(items)
    data_release = escape(release_type)
    data_impact = escape(best_impact)
    data_source = escape(rep.get("source") or "rss")

    # 代表記事（最新1件）
    first = items_by_date[0]
    first_src = first.get("source") or "rss"
    first_src_icon = SOURCE_ICONS.get(first_src, "📰")
    first_src_label = escape(first.get("source_label") or first_src)
    first_age = _fmt_date(first.get("published_at") or first.get("analyzed_at") or "")
    first_url = escape(first.get("url") or "#")
    first_title = escape(first.get("title") or "")
    first_title_short = first_title[:70] + ("…" if len(first_title) > 70 else "")

    # 複数件の場合はモーダルボタン
    import uuid as _uuid
    modal_id = "m" + _uuid.uuid4().hex[:8]
    modal_html = ""
    more_btn = ""
    if count > 1:
        modal_cards_html = _modal_cards(items)
        modal_html = f"""<div class="modal-overlay" id="{modal_id}" onclick="if(event.target===this)this.style.display='none'">
  <div class="modal-box">
    <div class="modal-header">
      <span class="modal-title">{tool_name}</span>
      <span class="count-badge">{count}件</span>
      <button class="modal-close" onclick="document.getElementById('{modal_id}').style.display='none'">✕</button>
    </div>
    <div class="modal-cards">{modal_cards_html}</div>
  </div>
</div>"""
        more_btn = f'<button class="more-btn" onclick="document.getElementById(\'{modal_id}\').style.display=\'flex\'">📋 {count}件の記事をすべて見る</button>'

    from urllib.parse import quote as _quote
    review_url = f"reviews.html?tool={_quote(rep.get('tool_name') or '')}"

    first_src_label_raw = first.get("source_label") or first_src
    data_source_label = escape(first_src_label_raw)

    return f"""{modal_html}<div class="tool-card" data-release="{data_release}" data-impact="{data_impact}" data-source="{data_source}" data-ai="{data_ai}" data-family="{escape(fam)}" data-source-label="{data_source_label}">
  <div class="tool-card-header">
    <div class="tool-name-row">
      <span class="tool-name">{tool_name}</span>
      <span class="family-badge" style="border-color:{fam_color};color:{fam_color}">{fam_label_esc}</span>
      <span class="release-badge">{release_icon} {escape(release_type)}</span>
      <span class="impact-badge" style="color:{impact_color}">{impact_label}</span>
      {f'<span class="count-badge">{count}件</span>' if count > 1 else ''}
      <button class="review-link" data-tool="{escape(rep.get('tool_name') or '')}" onclick="openMemoModal(this.dataset.tool)" title="所感を記入する">📋 使ってみた</button>
    </div>
  </div>
  {f'<div class="summary-ja">{summary_ja}</div>' if summary_ja else ''}
  <div class="card-footer">
    <div class="sub-article">
      <div class="sub-meta">{first_src_icon} {first_src_label} <span class="age">{first_age}</span></div>
      <a href="{first_url}" target="_blank" rel="noopener" class="article-link">{first_title_short or '記事を見る'} →</a>
    </div>
    {more_btn}
  </div>
</div>"""


def build_tools_page(output_path: str = OUTPUT_PATH) -> None:
    items = load_all_items()
    from zoneinfo import ZoneInfo
    now_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M JST")

    # リリース種別・影響度・ソース一覧
    release_types = sorted(set(i.get("release_type", "その他") for i in items if i.get("release_type")))
    sources = sorted(set(i.get("source_label", "") for i in items if i.get("source_label")))

    # 同一ツール名＋同一ファミリーでグループ化（tool_nameを正規化してまとめる）
    from collections import defaultdict
    import re as _re

    def _normalize_tool_name(name: str) -> str:
        n = name.strip().lower()
        # 記号・表記ゆれを統一
        n = n.replace("(", "").replace(")", "").replace("[", "").replace("]", "")
        n = n.replace("+", " plus ").replace("＋", " plus ")
        n = n.replace("&", "and").replace("／", "/")
        n = _re.sub(r"\s+", " ", n).strip()
        # バージョン番号の表記ゆれ（v1.0 → 1.0）
        n = _re.sub(r"\bv(\d)", r"\1", n)
        return n

    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        fam = item.get("tool_family") or "other"
        nk = _normalize_tool_name(item.get("tool_name") or "")
        key = f"{nk}|{fam}"
        groups[key].append(item)
    # グループ内最新のpublished_atで全体をソート
    _FAMILY_PRIORITY = {"gemini": 0, "claude": 0, "chatgpt": 0}

    def _group_sort_key(g: list[dict]) -> tuple:
        fam = (g[0].get("tool_family") or "").lower()
        is_priority = 0 if fam in _FAMILY_PRIORITY else 1
        latest = max(
            (x.get("published_at") or x.get("analyzed_at") or "" for x in g),
            default=""
        )
        return (is_priority, latest)

    sorted_groups = sorted(groups.values(), key=_group_sort_key, reverse=True)
    cards_html = "\n".join(_tool_card_group(g) for g in sorted_groups) if sorted_groups else \
        '<div class="empty-state"><p>まだデータがありません。ワークフローを実行すると蓄積されます。</p></div>'
    total_groups = len(sorted_groups)
    total_articles = len(items)

    ai_filter_btns = (
        '<button class="filter-btn active" data-filter-ai="all">すべて</button>\n'
        '<button class="filter-btn" data-filter-ai="ai">🤖 AI関連</button>\n'
        '<button class="filter-btn" data-filter-ai="non-ai">📱 非AI</button>\n'
    )

    family_filter_btns = (
        '<button class="filter-btn active" data-filter-family="all">すべて</button>\n'
        '<button class="filter-btn" data-filter-family="gemini">✨ Gemini</button>\n'
        '<button class="filter-btn" data-filter-family="claude">🟠 Claude</button>\n'
        '<button class="filter-btn" data-filter-family="chatgpt">💬 ChatGPT</button>\n'
    )
    family_filter_btns += '<button class="filter-btn" data-filter-family="other">📌 その他</button>\n'

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
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, sans-serif; min-height: 100vh; padding-top: 48px; }}
  .topnav {{ position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: #0a0f1eee; backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); display: flex; gap: 0.4rem; justify-content: center; flex-wrap: wrap; padding: 6px 12px; }}
  .topnav a {{ display: inline-block; padding: 4px 12px; background: var(--card); border-radius: 6px; color: var(--muted); text-decoration: none; font-size: 0.82rem; white-space: nowrap; }}
  .topnav a:hover {{ color: var(--accent); background: rgba(56,189,248,0.1); }}
  .topnav a.active {{ background: var(--accent2); color: #fff; }}
  header {{ background: linear-gradient(135deg, #0c1a35, #0a0f1e); padding: 16px 32px; border-bottom: 1px solid var(--border); }}
  .header-inner {{ max-width: 1200px; margin: 0 auto; }}
  .header-title {{ font-size: 1.4rem; font-weight: 700; color: var(--accent); }}
  .header-title span {{ font-size: 0.85rem; color: var(--muted); margin-left: 10px; font-weight: 400; }}
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
  .family-badge {{ font-size: 0.72rem; font-weight: 600; padding: 2px 8px; border-radius: 10px; border: 1px solid; background: rgba(0,0,0,0.2); }}
  .impact-badge {{ font-size: 0.75rem; font-weight: 600; }}
  .source-age {{ display: flex; gap: 10px; align-items: center; font-size: 0.76rem; color: var(--muted); }}
  .summary-ja {{ font-size: 0.9rem; color: var(--text); line-height: 1.65; }}
  .card-footer {{ border-top: 1px solid var(--border); padding-top: 8px; }}
  .article-link {{ color: var(--muted); font-size: 0.8rem; text-decoration: none; word-break: break-word; }}
  .article-link:hover {{ color: var(--accent); }}
  .count-badge {{ font-size: 0.72rem; background: rgba(148,163,184,0.15); border: 1px solid var(--border); color: var(--muted); padding: 2px 7px; border-radius: 10px; }}
  .sub-article {{ padding: 4px 0; }}
  .sub-meta {{ font-size: 0.74rem; color: var(--muted); margin-bottom: 2px; }}
  .more-btn {{ margin-top: 8px; background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.3); color: var(--accent); padding: 5px 12px; border-radius: 8px; cursor: pointer; font-size: 0.8rem; width: 100%; text-align: left; }}
  .more-btn:hover {{ background: rgba(56,189,248,0.2); }}
  .modal-overlay {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 1000; align-items: center; justify-content: center; padding: 16px; }}
  .modal-box {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; max-width: 860px; width: 100%; max-height: 85vh; display: flex; flex-direction: column; }}
  .modal-header {{ display: flex; align-items: center; gap: 10px; padding: 16px 20px; border-bottom: 1px solid var(--border); flex-shrink: 0; }}
  .modal-title {{ font-size: 1.1rem; font-weight: 700; color: var(--accent); flex: 1; }}
  .modal-close {{ background: none; border: none; color: var(--muted); font-size: 1.2rem; cursor: pointer; padding: 2px 6px; border-radius: 4px; }}
  .modal-close:hover {{ color: var(--text); background: var(--card); }}
  .modal-cards {{ overflow-y: auto; padding: 16px 20px; display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }}
  .modal-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px; display: flex; flex-direction: column; gap: 6px; }}
  .review-link {{ font-size: 0.75rem; color: var(--muted); text-decoration: none; padding: 2px 8px; border: 1px solid var(--border); border-radius: 10px; margin-left: auto; white-space: nowrap; transition: all 0.2s; }}
  .review-link:hover {{ color: var(--accent); border-color: var(--accent); background: rgba(56,189,248,0.1); }}
  .empty-state {{ text-align: center; padding: 60px 20px; color: var(--muted); grid-column: 1/-1; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 32px; margin-top: 20px; border-top: 1px solid var(--border); }}
  @media (max-width: 640px) {{
    header {{ padding: 12px; }}
    .topnav {{ gap: 4px; padding: 4px 8px; }}
    .topnav a {{ font-size: 0.75rem; padding: 3px 8px; }}
    .tools-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<nav class="topnav">
  <a href="index.html">📰 ニュース</a>
  <a href="strategy.html">🎯 施策提案</a>
  <a href="buzz.html">🔥 バズりランキング</a>
  <a href="money.html">🎬 マネタイズ</a>
  <a href="sns_success.html">🧠 SNS成功者</a>
  <a href="post_generator.html">✍️ 投稿ストック</a>
  <a href="tools.html" class="active">🔧 ツール追跡</a>
  <a href="reviews.html">📋 使ってみた</a>
</nav>
<header>
  <div class="header-inner">
    <div class="header-title">🔧 AIツール・機能リリース追跡 <span>Last updated: {now_str}</span></div>
  </div>
</header>
<div class="container">
  <div class="stats-bar">
    <div class="stat-chip">ツール数 <strong id="visibleCount">{total_groups}</strong> / {total_groups} 件（記事 {total_articles} 件）</div>
  </div>
  <div class="filter-section">
    <div class="filter-row">
      <span class="filter-label">ファミリー</span>
      {family_filter_btns}
    </div>
    <div class="filter-row">
      <span class="filter-label">カテゴリ</span>
      {ai_filter_btns}
    </div>
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
let activeAi = 'all';

let activeFamily = 'all';

function applyFilters() {{
  const cards = Array.from(document.querySelectorAll('.tool-card'));
  let visible = 0;
  cards.forEach(card => {{
    const releaseMatch = activeRelease === 'all' || card.dataset.release === activeRelease;
    const impactMatch = activeImpact === 'all' || card.dataset.impact === activeImpact;
    const aiMatch = activeAi === 'all' || card.dataset.ai === activeAi;
    const familyMatch = activeFamily === 'all' || card.dataset.family === activeFamily;
    let sourceMatch = true;
    if (activeSource !== 'all') {{
      const lbl = card.dataset.sourceLabel || '';
      sourceMatch = lbl.includes(activeSource);
    }}
    const show = releaseMatch && impactMatch && sourceMatch && aiMatch && familyMatch;
    card.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  document.getElementById('visibleCount').textContent = visible;
}}

document.querySelectorAll('[data-filter-family]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('[data-filter-family]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeFamily = btn.dataset.filterFamily;
    applyFilters();
  }});
}});

document.querySelectorAll('[data-filter-ai]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('[data-filter-ai]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeAi = btn.dataset.filterAi;
    applyFilters();
  }});
}});

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
    activeSource = btn.dataset.filterSource;
    applyFilters();
  }});
}});

/* ────────────────────────────────────────────────
   所感入力モーダル（GitHub API で reviews.json を更新）
──────────────────────────────────────────────── */
const REPO = 'k-hira-shine/ai-news-collector';
const FILE_PATH = 'data/reviews.json';
const REVIEWS_PAGE = 'reviews.html';

function getToken() {{
  return localStorage.getItem('gh_pat') || '';
}}

function openMemoModal(toolName) {{
  const existing = window.__reviewsCache || {{}};
  const rev = existing[toolName] || {{}};
  document.getElementById('memoToolName').textContent = toolName;
  document.getElementById('memoToolNameHidden').value = toolName;
  document.getElementById('memoStatus').value = rev.status || 'untried';
  document.getElementById('memoVerdict').value = rev.verdict || '';
  document.getElementById('memoMemo').value = rev.memo || '';
  document.getElementById('memoPurpose').value = rev.purpose || '';
  document.getElementById('memoCaution').value = rev.caution || '';
  document.getElementById('memoSaveMsg').textContent = '';
  document.getElementById('memoModal').style.display = 'flex';
}}

function closeMemoModal() {{
  document.getElementById('memoModal').style.display = 'none';
}}

async function fetchReviews(token) {{
  const res = await fetch(`https://api.github.com/repos/${{REPO}}/contents/${{FILE_PATH}}`, {{
    headers: {{ Authorization: `token ${{token}}`, Accept: 'application/vnd.github.v3+json' }}
  }});
  if (!res.ok) throw new Error(`GitHub API error: ${{res.status}}`);
  const data = await res.json();
  return {{ sha: data.sha, content: JSON.parse(atob(data.content.replace(/\\n/g,''))) }};
}}

async function saveMemo() {{
  let token = getToken();
  if (!token) {{
    token = prompt('GitHub Personal Access Token を入力してください（repo スコープ必要）:\\n\\n※ このトークンはこのブラウザのみに保存されます。');
    if (!token) return;
    localStorage.setItem('gh_pat', token);
  }}

  const toolName = document.getElementById('memoToolNameHidden').value;
  const msg = document.getElementById('memoSaveMsg');
  msg.style.color = 'var(--muted)';
  msg.textContent = '保存中…';

  try {{
    const {{ sha, content }} = await fetchReviews(token);
    window.__reviewsCache = Object.fromEntries((content.tools || []).map(t => [t.name, t]));

    const idx = (content.tools || []).findIndex(t => t.name === toolName);
    const today = new Date().toLocaleDateString('sv');
    const entry = {{
      name: toolName,
      category: idx >= 0 ? content.tools[idx].category : '',
      url: idx >= 0 ? content.tools[idx].url : '',
      status: document.getElementById('memoStatus').value,
      verdict: document.getElementById('memoVerdict').value,
      reason: idx >= 0 ? (content.tools[idx].reason || '') : '',
      purpose: document.getElementById('memoPurpose').value,
      method: idx >= 0 ? (content.tools[idx].method || '') : '',
      caution: document.getElementById('memoCaution').value,
      action_plan: idx >= 0 ? (content.tools[idx].action_plan || '') : '',
      use_for: idx >= 0 ? (content.tools[idx].use_for || []) : [],
      memo: document.getElementById('memoMemo').value,
      updated: today,
    }};

    if (idx >= 0) content.tools[idx] = entry;
    else content.tools.push(entry);

    const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(content, null, 2) + '\\n')));
    const putRes = await fetch(`https://api.github.com/repos/${{REPO}}/contents/${{FILE_PATH}}`, {{
      method: 'PUT',
      headers: {{ Authorization: `token ${{token}}`, Accept: 'application/vnd.github.v3+json', 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ message: `memo: ${{toolName}} の所感を更新`, content: encoded, sha }})
    }});
    if (!putRes.ok) {{
      const err = await putRes.json();
      throw new Error(err.message || putRes.status);
    }}
    msg.style.color = 'var(--success)';
    msg.textContent = '✅ 保存しました（ページ再ビルドに数分かかります）';
    window.__reviewsCache[toolName] = entry;
  }} catch(e) {{
    msg.style.color = 'var(--error)';
    if (e.message.includes('401') || e.message.includes('Bad credentials')) {{
      localStorage.removeItem('gh_pat');
      msg.textContent = '❌ トークンが無効です。再度ボタンを押してトークンを入力してください。';
    }} else {{
      msg.textContent = '❌ ' + e.message;
    }}
  }}
}}

// 初回ロード時に reviews.json をキャッシュ
(async () => {{
  try {{
    const res = await fetch(REVIEWS_PAGE.replace('.html','') + '/../data/reviews.json');
    // GitHub Pages では data/ は公開されていないので API なしでは取れない
    // トークンがあれば取得、なければスキップ
    const token = getToken();
    if (!token) return;
    const {{ content }} = await fetchReviews(token);
    window.__reviewsCache = Object.fromEntries((content.tools || []).map(t => [t.name, t]));
  }} catch {{}}
}})();
</script>

<!-- 所感入力モーダル -->
<div id="memoModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:2000;align-items:center;justify-content:center;padding:16px" onclick="if(event.target===this)closeMemoModal()">
  <div style="background:#111827;border:1px solid #2d3748;border-radius:14px;max-width:540px;width:100%;padding:24px;display:flex;flex-direction:column;gap:14px">
    <div style="display:flex;align-items:center;justify-content:space-between">
      <span style="font-size:1.1rem;font-weight:700;color:#38bdf8" id="memoToolName"></span>
      <button onclick="closeMemoModal()" style="background:none;border:none;color:#94a3b8;font-size:1.3rem;cursor:pointer">✕</button>
    </div>
    <input type="hidden" id="memoToolNameHidden">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      <label style="font-size:0.8rem;color:#94a3b8;display:flex;flex-direction:column;gap:4px">
        使用状況
        <select id="memoStatus" style="background:#1a2236;border:1px solid #2d3748;color:#e2e8f0;padding:6px;border-radius:6px;font-size:0.85rem">
          <option value="untried">未試用</option>
          <option value="trying">試用中</option>
          <option value="using">使ってる</option>
          <option value="rejected">却下</option>
        </select>
      </label>
      <label style="font-size:0.8rem;color:#94a3b8;display:flex;flex-direction:column;gap:4px">
        評価
        <select id="memoVerdict" style="background:#1a2236;border:1px solid #2d3748;color:#e2e8f0;padding:6px;border-radius:6px;font-size:0.85rem">
          <option value="">（未評価）</option>
          <option value="use">使う</option>
          <option value="watch">様子見</option>
          <option value="skip">スキップ</option>
        </select>
      </label>
    </div>
    <label style="font-size:0.8rem;color:#94a3b8;display:flex;flex-direction:column;gap:4px">
      用途・目的
      <input id="memoPurpose" type="text" placeholder="例: YouTube台本作成、調査" style="background:#1a2236;border:1px solid #2d3748;color:#e2e8f0;padding:7px 10px;border-radius:6px;font-size:0.85rem">
    </label>
    <label style="font-size:0.8rem;color:#94a3b8;display:flex;flex-direction:column;gap:4px">
      注意点・制限
      <input id="memoCaution" type="text" placeholder="例: 無料枠に制限あり" style="background:#1a2236;border:1px solid #2d3748;color:#e2e8f0;padding:7px 10px;border-radius:6px;font-size:0.85rem">
    </label>
    <label style="font-size:0.8rem;color:#94a3b8;display:flex;flex-direction:column;gap:4px">
      所感メモ
      <textarea id="memoMemo" rows="4" placeholder="使ってみた感想、気づき、改善点など自由に…" style="background:#1a2236;border:1px solid #2d3748;color:#e2e8f0;padding:8px 10px;border-radius:6px;font-size:0.85rem;resize:vertical;line-height:1.6"></textarea>
    </label>
    <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
      <span id="memoSaveMsg" style="font-size:0.8rem"></span>
      <div style="display:flex;gap:8px">
        <a id="memoReviewLink" href="reviews.html" style="font-size:0.8rem;color:#94a3b8;text-decoration:none;padding:7px 14px;border:1px solid #2d3748;border-radius:8px">詳細ページ →</a>
        <button onclick="saveMemo()" style="background:#0284c7;border:none;color:#fff;padding:8px 20px;border-radius:8px;font-size:0.85rem;cursor:pointer;font-weight:600">保存</button>
      </div>
    </div>
  </div>
</div>
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

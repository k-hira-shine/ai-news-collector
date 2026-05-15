"""AIツール・機能リリース追跡 — Gemini分析モジュール

収集した記事をGeminiで分析し、AIツール/機能のリリース・アップデートとして
有益なものを構造化して data/tools/YYYY-MM-DD.jsonl に保存する。
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("ai-news.tools_analyzer")

TOOLS_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "string"},
                    "is_tool_release": {"type": "boolean"},
                    "tool_name": {"type": "string"},
                    "release_type": {
                        "type": "string",
                        "enum": ["新規リリース", "アップデート", "機能追加", "廃止・終了", "その他"],
                    },
                    "summary_ja": {"type": "string"},
                    "impact": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "is_ai_tool": {"type": "boolean"},
                    "tool_family": {
                        "type": "string",
                        "enum": ["gemini", "claude", "chatgpt", "other"],
                    },
                },
                "required": ["item_id", "is_tool_release"],
            },
        }
    },
    "required": ["items"],
}

RELEASE_TYPE_ICONS = {
    "新規リリース": "🆕",
    "アップデート": "🔄",
    "機能追加": "✨",
    "廃止・終了": "🚫",
    "その他": "📌",
}

IMPACT_COLORS = {
    "high": "#ef4444",
    "medium": "#f59e0b",
    "low": "#64748b",
}


def analyze_tools_items(items: list[dict], config: dict) -> list[dict]:
    """記事リストからAIツール関連記事を抽出・分析して返す"""
    if not items:
        return []

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — skipping tools analysis")
        return []

    try:
        from google import genai  # noqa: F401
    except ImportError:
        logger.warning("google-genai not installed")
        return []

    model_name = config.get("analysis", {}).get("models", {}).get("fallback", "gemini-2.5-flash")

    batch_size = 30
    all_results: list[dict] = []

    for batch_start in range(0, len(items), batch_size):
        batch = items[batch_start: batch_start + batch_size]
        analyzed = _analyze_batch(batch, model_name, api_key, config)
        all_results.extend(analyzed)
        logger.info(
            "Tools analysis batch %d-%d: %d tool items found",
            batch_start, batch_start + len(batch), len(analyzed),
        )

    return all_results


def _analyze_batch(items: list[dict], model_name: str, api_key: str, config: dict) -> list[dict]:
    """1バッチ分を分析して構造化結果を返す"""
    from google import genai
    from google.genai import types

    items_text = ""
    for item in items:
        items_text += f"""
[ID: {item.get('id', '')}]
タイトル: {item.get('title', '')}
ソース: {item.get('source_label', '')}
本文（抜粋）: {(item.get('content') or '')[:600]}
---"""

    prompt = f"""以下の記事リストを分析してください。

## 分析対象記事
{items_text}

## 指示
各記事について以下を判定してください：
1. AIツール・AIモデル・AI機能のリリース/アップデートに関する記事かどうか（is_tool_release）
   - YESの条件: 新しいAIツール発表、モデルアップデート、新機能追加、APIリリースなど
   - NOの条件: 単なるAI活用事例、コラム、研究論文（ツール発表なし）
2. ツール名（例: "Claude 4", "GPT-5", "Cursor 1.0", "Gemini 2.5"）
3. リリース種別: 新規リリース / アップデート / 機能追加 / 廃止・終了 / その他
4. 日本語要約（60字以内。英語記事も日本語に翻訳して要約すること）
5. 影響度（high: 業界に大きな影響 / medium: 注目すべき / low: 参考程度）
6. AI関連かどうか（is_ai_tool）: AIモデル・AIツール・AI機能ならtrue、それ以外（SNS機能・一般アプリ等）ならfalse
7. 主要プロダクトファミリー（tool_family）— 記事の「主題・主役」がどのラインに最も強く属するか **ひとつだけ** 選ぶ
   - gemini: Google Gemini、Gemini API、Google AI Studio（Gemini向け）、Google の Gemini / Bard 系の発表
   - claude: Anthropic Claude、Claude API、Claude Code（Claude製品として）、Anthropic のモデル発表が中心
   - chatgpt: OpenAI の ChatGPT、GPT シリーズ、記事の中心が ChatGPT / GPT 製品・API（OpenAI）である場合
   - other: 上記のどれでも主題になっていない（Llama/Mistral のみ、別社単独、一般的な AI 論評のみなど）

複数言及があっても「読者にとっての主役」を一つに決めること。

is_tool_release=falseの記事も必ず結果に含めてください。"""

    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=TOOLS_SCHEMA,
                thinking_config=types.ThinkingConfig(thinking_budget=128),
            ),
        )
        raw = json.loads(response.text)
    except Exception as e:
        logger.error("Gemini tools analysis failed: %s", e)
        return []

    id_to_item = {item.get("id", ""): item for item in items}
    results: list[dict] = []

    for r in raw.get("items", []):
        if not r.get("is_tool_release"):
            continue
        item_id = r.get("item_id", "")
        source_item = id_to_item.get(item_id, {})
        if not source_item:
            if not r.get("tool_name"):
                continue

        family = r.get("tool_family") or "other"
        results.append({
            **source_item,
            "tool_name": r.get("tool_name", ""),
            "release_type": r.get("release_type", "その他"),
            "summary_ja": r.get("summary_ja", ""),
            "impact": r.get("impact", "low"),
            "is_ai_tool": r.get("is_ai_tool", True),
            "tool_family": family,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        })

    return results


def load_all_tools_analyses(days: int = 30) -> list[dict]:
    """data/tools/ から分析済みアイテムを全件ロード"""
    from tools_collector import load_all_tools_items
    items = load_all_tools_items(days=days)
    # 分析済み（tool_nameがある）のもののみ返す
    return [i for i in items if i.get("tool_name")]


def save_tools_analysis(items: list[dict]) -> str:
    """分析済みレコードを id で既存 JSONL を検索し、該当行をすべて置換する。

    見つからない id は当日の JSONL に追加する。過去日ファイルの行を更新しても
    当日ファイルへ複製しない（従来バグの回避）。
    """
    if not items:
        return ""

    from collections import defaultdict
    from glob import glob

    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tools")
    os.makedirs(base, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_path = os.path.join(base, f"{today}.jsonl")

    paths = sorted(glob(os.path.join(base, "*.jsonl")))
    file_rows: dict[str, list[dict]] = {}
    id_positions: dict[str, list[tuple[str, int]]] = defaultdict(list)

    for p in paths:
        rows: list[dict] = []
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f.read().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
        file_rows[p] = rows
        for idx, obj in enumerate(rows):
            oid = obj.get("id", "")
            if oid:
                id_positions[oid].append((p, idx))

    if today_path not in file_rows:
        file_rows[today_path] = []

    modified_files: set[str] = set()

    for item in items:
        item_id = item.get("id", "")
        if not item_id:
            continue
        positions = id_positions.get(item_id, [])
        if positions:
            for fp, idx in positions:
                file_rows[fp][idx] = item
                modified_files.add(fp)
        else:
            rows_today = file_rows[today_path]
            rows_today.append(item)
            id_positions[item_id].append((today_path, len(rows_today) - 1))
            modified_files.add(today_path)

    for fp in modified_files:
        tmp = fp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for obj in file_rows[fp]:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        os.replace(tmp, fp)

    logger.info(
        "Upserted %d analyzed tools records (%d files touched)",
        len(items),
        len(modified_files),
    )
    return today_path

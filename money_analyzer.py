"""動画マネタイズ事例アナライザー

収集したポストをGeminiで分析し、
「動画を使って稼ぐ事例」に該当するものを構造化して返す。
"""

import json
import logging
import os

logger = logging.getLogger("ai-news.money_analyzer")

MONEY_CASE_SCHEMA = {
    "type": "object",
    "properties": {
        "cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "post_id": {"type": "string"},
                    "is_money_case": {"type": "boolean"},
                    "summary": {"type": "string"},
                    "method": {"type": "string"},
                    "tools": {"type": "array", "items": {"type": "string"}},
                    "income_mentioned": {"type": "string"},
                    "category": {"type": "string"},
                    "difficulty": {"type": "string"},
                    "is_japanese": {"type": "boolean"},
                },
                "required": ["post_id", "is_money_case"],
            },
        }
    },
    "required": ["cases"],
}

CATEGORIES = [
    "YouTube収益化",
    "ショート動画/Reels/TikTok",
    "AI動画生成",
    "ライブ配信",
    "動画編集代行",
    "動画×教育/コンサル",
    "動画×SaaS/プロダクト",
    "その他",
]


def analyze_money_cases(items: list[dict], config: dict) -> list[dict]:
    """ポストリストからAIマネタイズ事例を抽出して返す"""
    if not items:
        return []

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — skipping money analysis")
        return []

    try:
        from google import genai  # noqa: F401
    except ImportError:
        logger.warning("google-genai not installed")
        return []

    model_name = config.get("analysis", {}).get("models", {}).get("stage1_filter", "gemini-2.5-pro")

    # バッチサイズを50件に分割して処理
    batch_size = 50
    all_cases: list[dict] = []

    for batch_start in range(0, len(items), batch_size):
        batch = items[batch_start : batch_start + batch_size]
        cases = _analyze_batch(batch, model_name, api_key, config)
        all_cases.extend(cases)
        logger.info("Money analysis batch %d-%d: %d cases found", batch_start, batch_start + len(batch), len(cases))

    return all_cases


def _analyze_batch(items: list[dict], model_name: str, api_key: str, config: dict) -> list[dict]:
    """50件以下のバッチをGeminiで分析（google-genai 新SDK使用）"""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    posts_text = ""
    for item in items:
        posts_text += f"""
[ID: {item['id']}]
著者: @{item.get('author', '')} ({item.get('author_display', '')})
投稿日: {item.get('published_at', '')[:10]}
いいね: {item.get('engagement', {}).get('likes', 0)}
本文:
{item.get('content', '')[:500]}
---
"""

    prompt = f"""以下のXポスト一覧を分析し、「動画を使って稼いでいる・稼げた」という事例に関するポストを抽出してください。

## 抽出条件
以下のいずれかに該当するものを is_money_case: true とする：
- YouTube・TikTok・Instagram Reels・ショート動画などで収益を得た・稼いだという実績・報告
- AI動画生成ツール（Kling・Runway・Sora・HeyGen・ElevenLabs等）を使って収益化した事例
- 動画コンテンツを使ったビジネス・副業・フリーランスの具体的な手法紹介
- 「この人が動画でこうやって稼いでいる」という事例紹介・まとめ（本人発信でなくてもOK）
- 動画制作代行・動画編集サービスで稼いでいる事例

## 除外するもの（is_money_case: false）
- 動画ツールの単なる紹介・感想（稼ぎに無関係）
- 「動画で稼ごう」という呼びかけのみで実例なし
- リポスト（RTで始まるもの）
- 動画と無関係な事例（コーディング代行・テキスト副業など）

## 分析フィールド
各ポストについて：
- post_id: ポストのID（[ID: ...]の値）
- is_money_case: true/false
- summary: 事例の要約（50文字以内、日本語）※ is_money_case=true のみ
- method: 稼ぎ方の手法（例：「AI美女動画でInstagramサブスク」「YouTubeショートで広告収益」）
- tools: 使用ツール（例：["Kling", "Runway", "ElevenLabs", "HeyGen"]）
- income_mentioned: 言及された収益額（例：「月300万」「年6000万」、なければ空文字）
- category: カテゴリ（{', '.join(CATEGORIES)} から1つ選ぶ）
- difficulty: 手軽さ・難易度（以下の3段階から1つ選ぶ）
  - "beginner": スマホのみ・無料ツール・初心者でも即始められる・特別なスキル不要
  - "intermediate": 一定の学習や機材投資が必要・副業として取り組める・数週間〜数ヶ月で収益化可能
  - "advanced": 高い専門スキル・大きな初期投資・事業として本格的に取り組む必要がある
- is_japanese: 日本語の投稿かどうか

## ポスト一覧
{posts_text}
"""

    try:
        thinking_budget = config.get("analysis", {}).get("thinking_budget", {}).get("stage1", 128)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={
                "thinking_config": {"thinking_budget": thinking_budget},
                "response_mime_type": "application/json",
                "response_json_schema": MONEY_CASE_SCHEMA,
                "http_options": types.HttpOptions(timeout=300_000),
            },
        )
        result = json.loads(response.text)
        raw_cases = result.get("cases", [])

        # is_money_case=True のものだけ返す・post_id で元データを紐付ける
        min_followers = config.get("money_collection", {}).get("min_followers", 1000)
        id_to_item = {item["id"]: item for item in items}
        money_cases = []
        for case in raw_cases:
            if not case.get("is_money_case"):
                continue
            post_id = case.get("post_id", "")
            original = id_to_item.get(post_id, {})
            if not original:
                continue
            # フォロワー数フィルター
            followers = original.get("author_followers") or 0
            if followers < min_followers:
                continue
            merged = {**original, **case}
            money_cases.append(merged)

        return money_cases

    except Exception as e:
        logger.error("Money analysis batch failed: %s", e)
        return []


def save_money_analysis(cases: list[dict], date_str: str, slot: str) -> str:
    """data/money/YYYY-MM-DD_slot_analysis.json に保存"""
    from utils import data_dir
    import os

    money_dir = data_dir("money")
    os.makedirs(money_dir, exist_ok=True)
    path = os.path.join(money_dir, f"{date_str}_{slot}_analysis.json")

    output = {
        "date": date_str,
        "slot": slot,
        "total_cases": len(cases),
        "cases": cases,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info("Money analysis saved → %s (%d cases)", path, len(cases))
    return path


def load_all_money_analyses() -> list[dict]:
    """data/money/ の全 _analysis.json を読み込んで事例リストを返す"""
    from utils import data_dir
    import os

    money_dir = data_dir("money")
    if not os.path.isdir(money_dir):
        return []

    all_cases: list[dict] = []
    seen_ids: set[str] = set()

    for fname in sorted(os.listdir(money_dir), reverse=True):
        if not fname.endswith("_analysis.json"):
            continue
        path = os.path.join(money_dir, fname)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for case in data.get("cases", []):
                case_id = case.get("id", "")
                if case_id and case_id in seen_ids:
                    continue
                if case_id:
                    seen_ids.add(case_id)
                all_cases.append(case)
        except Exception as e:
            logger.warning("Failed to load %s: %s", fname, e)

    logger.info("Loaded %d total money cases", len(all_cases))
    return all_cases

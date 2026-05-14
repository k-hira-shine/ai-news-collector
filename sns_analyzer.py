"""SNS成功者マインド・思考法アナライザー

収集したポストをGeminiで分析し、
「SNSで成功した人の思考法・習慣・マインドセット」として
有益なものを構造化して返す。
"""

import json
import logging
import os

logger = logging.getLogger("ai-news.sns_analyzer")

SNS_MIND_SCHEMA = {
    "type": "object",
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "post_id": {"type": "string"},
                    "is_valuable": {"type": "boolean"},
                    "summary": {"type": "string"},
                    "mind_theme": {"type": "string"},
                    "key_insights": {"type": "array", "items": {"type": "string"}},
                    "target_audience": {"type": "string"},
                    "category": {"type": "string"},
                    "credibility": {"type": "string"},
                    "is_japanese": {"type": "boolean"},
                },
                "required": ["post_id", "is_valuable"],
            },
        }
    },
    "required": ["posts"],
}

CATEGORIES = [
    "マインドセット/思考法",
    "習慣/ルーティン",
    "潜在意識/引き寄せ",
    "SNS戦略/成長法",
    "FIRE/資産形成",
    "副業/収益化",
    "人間関係/環境整備",
    "自己啓発/メンタル",
    "その他",
]


def analyze_sns_posts(items: list[dict], config: dict) -> list[dict]:
    """ポストリストからSNS成功者マインド投稿を抽出して返す"""
    if not items:
        return []

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — skipping sns analysis")
        return []

    try:
        from google import genai  # noqa: F401
    except ImportError:
        logger.warning("google-genai not installed")
        return []

    model_name = config.get("analysis", {}).get("models", {}).get("stage1_filter", "gemini-2.5-pro")

    batch_size = 50
    all_posts: list[dict] = []

    for batch_start in range(0, len(items), batch_size):
        batch = items[batch_start: batch_start + batch_size]
        posts = _analyze_batch(batch, model_name, api_key, config)
        all_posts.extend(posts)
        logger.info(
            "SNS analysis batch %d-%d: %d valuable posts found",
            batch_start, batch_start + len(batch), len(posts),
        )

    return all_posts


def _analyze_batch(items: list[dict], model_name: str, api_key: str, config: dict) -> list[dict]:
    """50件以下のバッチをGeminiで分析（google-genai 新SDK使用）"""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    posts_text = ""
    for item in items:
        posts_text += f"""
[ID: {item['id']}]
著者: @{item.get('author', '')} ({item.get('author_display', '')}) フォロワー: {item.get('author_followers', 0):,}
投稿日: {item.get('published_at', '')[:10]}
いいね: {item.get('engagement', {}).get('likes', 0)}
本文:
{item.get('content', '')[:800]}
---
"""

    prompt = f"""以下のXポスト一覧を分析し、「SNSで成功した人の思考法・習慣・マインドセット」として価値のある投稿を抽出してください。

## 抽出条件
以下のいずれかに該当するものを is_valuable: true とする：
- SNS・副業・FIRE・資産形成などで成功した人が語る「考え方・思考法・マインドセット」
- 「人生が変わった習慣・ルーティン」の具体的な紹介（成功実績のある人による）
- 潜在意識・引き寄せの法則など、成功に至るメンタル・精神的アプローチ
- SNS成長の具体的な戦略・方法論（フォロワーを増やした・バズらせた経験談）
- どん底・逆境からの這い上がり体験談とそこから得た教訓・思考法
- 高フォロワーインフルエンサーが語る「成功の本質・法則」
- 「〇〇万円稼いだ/FIREした人が実践していた考え方」などの事例まとめ

## 除外するもの（is_valuable: false）
- 単なる商品・サービスの宣伝・セールス（実質的なコンテンツがない）
- 具体性のない「頑張ろう」系の応援ポスト
- 特定の情報商材・コンサルへの誘導が主目的（本質的なコンテンツがない）
- リポスト（RTで始まる）
- ニュースの引用のみで独自の見解・知見がない
- フォロワー数が少なく実績が不明な人による根拠のない主張

## 分析フィールド
各ポストについて：
- post_id: ポストのID（[ID: ...]の値）
- is_valuable: true/false
- summary: 投稿の核心を1行で（60文字以内、日本語）※ is_valuable=true のみ
- mind_theme: 主要なマインドテーマ（例：「どん底からの潜在意識書き換え」「朝活×副業習慣」）
- key_insights: この投稿から学べる重要な気づき（最大3つ、日本語の短文リスト）
- target_audience: 刺さる読者像（例：「副業を始めたい会社員」「SNSで伸び悩む人」）
- category: カテゴリ（{', '.join(CATEGORIES)} から1つ選ぶ）
- credibility: 投稿者の信頼性・実績（例：「月収150万達成の元看護師」「フォロワー84万人」）なければ空文字
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
                "response_json_schema": SNS_MIND_SCHEMA,
                "http_options": types.HttpOptions(timeout=300_000),
            },
        )
        result = json.loads(response.text)
        raw_posts = result.get("posts", [])

        min_followers = config.get("sns_success", {}).get("min_followers", 5000)
        id_to_item = {item["id"]: item for item in items}
        valuable_posts = []
        for post in raw_posts:
            if not post.get("is_valuable"):
                continue
            post_id = post.get("post_id", "")
            original = id_to_item.get(post_id, {})
            if not original:
                continue
            followers = original.get("author_followers") or 0
            if followers < min_followers:
                continue
            merged = {**original, **post}
            valuable_posts.append(merged)

        return valuable_posts

    except Exception as e:
        logger.error("SNS analysis batch failed: %s", e)
        return []


def save_sns_analysis(posts: list[dict], date_str: str, slot: str) -> str:
    """data/sns_success/YYYY-MM-DD_slot_analysis.json に保存"""
    from utils import data_dir

    sns_dir = data_dir("sns_success")
    os.makedirs(sns_dir, exist_ok=True)
    path = os.path.join(sns_dir, f"{date_str}_{slot}_analysis.json")

    output = {
        "date": date_str,
        "slot": slot,
        "total_posts": len(posts),
        "posts": posts,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info("SNS analysis saved → %s (%d posts)", path, len(posts))
    return path


def load_all_sns_analyses() -> list[dict]:
    """data/sns_success/ の全 _analysis.json を読み込んで投稿リストを返す"""
    from utils import data_dir

    sns_dir = data_dir("sns_success")
    if not os.path.isdir(sns_dir):
        return []

    all_posts: list[dict] = []
    seen_ids: set[str] = set()

    for fname in sorted(os.listdir(sns_dir), reverse=True):
        if not fname.endswith("_analysis.json"):
            continue
        path = os.path.join(sns_dir, fname)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for post in data.get("posts", []):
                post_id = post.get("id", "")
                if post_id and post_id in seen_ids:
                    continue
                if post_id:
                    seen_ids.add(post_id)
                all_posts.append(post)
        except Exception as e:
            logger.warning("Failed to load %s: %s", fname, e)

    logger.info("Loaded %d total sns posts", len(all_posts))
    return all_posts

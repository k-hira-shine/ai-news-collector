"""3段 Gemini パイプラインで AI ニュースを分析"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from glob import glob

from utils import data_dir, now_iso, parse_datetime, retry, time_slot, today_str

logger = logging.getLogger("ai-news.analyzer")

# ━━━━━━━━━━━━━━━━ JSON Schema (Stage 1 / Stage 2) ━━━━━━━━━━━━━━━━

STAGE1_SCHEMA = {
    "type": "object",
    "properties": {
        "scored_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "importance_score": {"type": "integer"},
                    "category": {"type": "string"},
                },
                "required": ["id", "importance_score", "category"],
            },
        },
    },
    "required": ["scored_items"],
}

STAGE2_SCHEMA = {
    "type": "object",
    "properties": {
        "trend_summary": {"type": "string"},
        "previous_day_comparison": {
            "type": "object",
            "properties": {
                "continuing": {"type": "array", "items": {"type": "string"}},
                "new_topics": {"type": "array", "items": {"type": "string"}},
                "fading": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["continuing", "new_topics", "fading"],
        },
        "top_articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "rank": {"type": "integer"},
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "summary": {"type": "string"},
                    "importance_reason": {"type": "string"},
                    "category": {"type": "string"},
                    "source_label": {"type": "string"},
                },
                "required": ["id", "rank", "title", "summary"],
            },
        },
        "category_summaries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "summary": {"type": "string"},
                    "count": {"type": "integer"},
                    "key_articles": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                                "summary": {"type": "string"},
                            },
                            "required": ["title", "url"],
                        },
                    },
                },
                "required": ["category", "summary"],
            },
        },
        "action_items": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["trend_summary", "top_articles", "category_summaries", "action_items"],
}


# ━━━━━━━━━━━━━━━━ Analyzer ━━━━━━━━━━━━━━━━


class NewsAnalyzer:
    def __init__(self, config: dict):
        self.config = config
        analysis_cfg = config.get("analysis", {})
        self.models = analysis_cfg.get("models", {})
        self.thinking = analysis_cfg.get("thinking_budget", {})
        self.categories = analysis_cfg.get("categories", [])
        self.top_n = analysis_cfg.get("top_n", 10)
        self.stage1_top_n = analysis_cfg.get("stage1_top_n", 100)
        self.scoring_cfg = config.get("scoring", {})
        self._init_client()

    def _init_client(self) -> None:
        from google import genai

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        self.client = genai.Client(api_key=api_key)

    # ── public ────────────────────────────────────────────────────────

    def analyze(self, items: list[dict]) -> dict:
        """収集データを分析し、構造化された結果を返す"""
        if not items:
            logger.warning("No items to analyze")
            return self._empty_result()

        items_by_id = {it["id"]: it for it in items}

        # Stage 1: フィルタ & スコアリング
        scored = self._stage1_filter(items)
        scored = self._apply_bonuses(scored, items_by_id)
        scored.sort(key=lambda x: x["final_score"], reverse=True)
        top_items = scored[: self.stage1_top_n]

        logger.info(
            "Stage 1 complete: %d → %d items (top score %.1f)",
            len(items),
            len(top_items),
            top_items[0]["final_score"] if top_items else 0,
        )

        if not top_items:
            logger.warning("Stage 1 returned 0 items — skipping Stage 2")
            return self._empty_result()

        # RPM 制限対策: Pro は 5 RPM → 最低 12 秒間隔
        time.sleep(15)

        # Stage 2: 深層分析
        previous = self._load_previous_analysis()
        analysis = self._stage2_analyze(top_items, items_by_id, previous)

        # メタデータ付与
        analysis["run_time"] = now_iso()
        analysis["slot"] = time_slot()
        analysis["item_count"] = len(items)

        self._save_analysis(analysis)
        return analysis

    # ── Stage 1 ───────────────────────────────────────────────────────

    def _stage1_filter(self, items: list[dict]) -> list[dict]:
        model = self.models.get("stage1_filter", "gemini-2.5-pro")
        budget = self.thinking.get("stage1", 128)

        items_text = self._compress_items_for_stage1(items)
        categories_str = ", ".join(self.categories)

        prompt = f"""あなたはAIニュースアナリストです。以下の収集ニュース一覧から、AI/ML/LLM に関連する重要な記事を最大{self.stage1_top_n}件選んでください。

各記事に対して:
1. importance_score (1-10):
   - 9-10: 主要AI企業の重大発表、画期的な研究成果
   - 7-8: 重要なプロダクト更新、大きな政策変更
   - 5-6: 注目すべき業界ニュース、興味深い研究
   - 3-4: 軽微なアップデート、周辺的なAIニュース
   - 1-2: ほぼ無関係またはノイズ
2. category (次のいずれか): {categories_str}

AI/ML と無関係な記事はスキップしてください。

===== 記事一覧 ({len(items)}件) =====
{items_text}
"""
        result = self._call_gemini(model, prompt, STAGE1_SCHEMA, budget)
        return result.get("scored_items", [])

    def _compress_items_for_stage1(self, items: list[dict]) -> str:
        lines: list[str] = []
        for it in items:
            eng = it.get("engagement", {})
            eng_str = ""
            if eng.get("likes") or eng.get("retweets"):
                eng_str = f" | ❤️{eng.get('likes', 0)} 🔁{eng.get('retweets', 0)}"

            pub = it.get("published_at", "")[:16]
            content_preview = it.get("content", "")[:200].replace("\n", " ")

            lines.append(
                f"[{it['id']}] {it.get('title', '')[:120]}\n"
                f"  src={it['source']}:{it.get('source_name', '')} | pub={pub}{eng_str}\n"
                f"  {content_preview}"
            )
        return "\n\n".join(lines)

    # ── Freshness / Official / Must-follow bonuses ────────────────────

    def _apply_bonuses(self, scored: list[dict], items_by_id: dict) -> list[dict]:
        now = datetime.now(timezone.utc)

        for s in scored:
            item = items_by_id.get(s["id"], {})
            bonus = 0.0

            pub_dt = parse_datetime(item.get("published_at", ""))
            if pub_dt:
                hours_ago = (now - pub_dt).total_seconds() / 3600
                for tier in self.scoring_cfg.get("freshness_bonus", []):
                    if hours_ago <= tier["hours"]:
                        bonus += tier["bonus"]
                        break

            if item.get("is_official"):
                bonus += self.scoring_cfg.get("official_source_bonus", 2.0)
            if item.get("is_must_follow"):
                bonus += self.scoring_cfg.get("must_follow_bonus", 1.5)

            s["bonus"] = bonus
            s["final_score"] = min(10.0, s.get("importance_score", 0) + bonus)

        return scored

    # ── Stage 2 ───────────────────────────────────────────────────────

    def _stage2_analyze(
        self, top_items: list[dict], items_by_id: dict, previous: dict | None
    ) -> dict:
        model = self.models.get("stage2_analysis", "gemini-2.5-pro")
        budget = self.thinking.get("stage2", 1024)

        items_text = self._format_items_for_stage2(top_items, items_by_id)
        prev_context = self._format_previous_context(previous)
        categories_str = ", ".join(self.categories)

        prompt = f"""あなたはシニアAI産業アナリストです。本日のAIニューストップ記事を包括的に分析してください。

===== 本日の注目記事 (スコア順、{len(top_items)}件) =====
{items_text}

{prev_context}

===== 出力要件 =====
すべて日本語で出力してください。

1. trend_summary: 今日のAI界の最重要動向を3〜5文で概説
2. previous_day_comparison:
   - continuing: 前日から継続している話題
   - new_topics: 今日新たに浮上した話題
   - fading: 沈静化した話題
   (前日データがない場合は空配列)
3. top_articles: 重要度上位{self.top_n}件。各記事に rank, id, title, url, summary (1〜2文), importance_reason, category, source_label を含める
4. category_summaries: カテゴリ({categories_str})別の要約と主要記事 (最大5件)
5. action_items: ビジネスへの示唆・アクションアイテムを3〜5件
"""
        result = self._call_gemini(model, prompt, STAGE2_SCHEMA, budget)

        # id→url / title のフォールバック補完
        for art in result.get("top_articles", []):
            item = items_by_id.get(art.get("id", ""), {})
            if not art.get("url"):
                art["url"] = item.get("url", "")
            if not art.get("title"):
                art["title"] = item.get("title", "")
            if not art.get("source_label"):
                src = item.get("source", "")
                art["source_label"] = f"{src}: {item.get('source_name', '')}"

        return result

    def _format_items_for_stage2(self, top_items: list[dict], items_by_id: dict) -> str:
        lines: list[str] = []
        for s in top_items:
            item = items_by_id.get(s["id"], {})
            official = " [公式]" if item.get("is_official") else ""
            must = " [必須]" if item.get("is_must_follow") else ""

            lines.append(
                f"[{s['id']}] Score: {s['final_score']:.1f} (LLM:{s.get('importance_score', 0)} +bonus:{s.get('bonus', 0):.1f}) | {s.get('category', '?')}{official}{must}\n"
                f"  Title: {item.get('title', '')}\n"
                f"  URL: {item.get('url', '')}\n"
                f"  Source: {item.get('source', '')}:{item.get('source_name', '')}\n"
                f"  {item.get('content', '')[:500]}"
            )
        return "\n\n".join(lines)

    def _format_previous_context(self, previous: dict | None) -> str:
        if not previous:
            return "===== 前日分析 =====\n前日のデータはありません（初回実行）。previous_day_comparison は空配列を返してください。"

        parts = ["===== 前日分析 ====="]
        if previous.get("trend_summary"):
            parts.append(f"前日のトレンド: {previous['trend_summary']}")
        tops = previous.get("top_articles", [])[:5]
        if tops:
            parts.append("前日のトップ5:")
            for a in tops:
                parts.append(f"  - {a.get('title', '')} ({a.get('category', '')})")
        return "\n".join(parts)

    # ── Gemini API 呼び出し ────────────────────────────────────────────

    @retry(max_retries=2, base_delay=5, max_delay=60)
    def _call_gemini(
        self, model: str, prompt: str, schema: dict | None = None, thinking_budget: int = 128
    ) -> dict:
        config_dict: dict = {
            "thinking_config": {"thinking_budget": thinking_budget},
        }
        if schema:
            config_dict["response_mime_type"] = "application/json"
            config_dict["response_json_schema"] = schema

        logger.info("Calling %s (thinking=%d)…", model, thinking_budget)
        t0 = time.time()

        response = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=config_dict,
        )

        elapsed = time.time() - t0
        logger.info("Gemini responded in %.1fs", elapsed)

        text = response.text
        if not text:
            raise ValueError("Empty response from Gemini")

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            logger.error("Failed to parse Gemini response: %s…", text[:500])
            raise

    # ── 前日分析の読み込み / 保存 ──────────────────────────────────────

    def _load_previous_analysis(self) -> dict | None:
        if not self.config.get("analysis", {}).get("enable_previous_day_context", True):
            return None

        analysis_dir = data_dir("analysis")
        if not os.path.isdir(analysis_dir):
            return None

        files = sorted(glob(os.path.join(analysis_dir, "*.json")), reverse=True)
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, OSError):
                continue
        return None

    def _save_analysis(self, result: dict) -> str:
        slot = result.get("slot", time_slot())
        filename = f"{today_str()}_{slot}.json"
        path = data_dir("analysis", filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

        logger.info("Analysis saved → %s", path)
        return path

    def _empty_result(self) -> dict:
        return {
            "run_time": now_iso(),
            "slot": time_slot(),
            "item_count": 0,
            "trend_summary": "収集データがありません。",
            "previous_day_comparison": {"continuing": [], "new_topics": [], "fading": []},
            "top_articles": [],
            "category_summaries": [],
            "action_items": [],
        }

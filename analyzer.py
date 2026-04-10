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
        "trend_evolution": {
            "type": "object",
            "properties": {
                "since_last": {"type": "string"},
                "tracked_topics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "status": {"type": "string"},
                            "streak_days": {"type": "integer"},
                            "evolution": {"type": "string"},
                        },
                        "required": ["topic", "status"],
                    },
                },
            },
            "required": ["since_last", "tracked_topics"],
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
        "x_trends": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "description": {"type": "string"},
                    "buzz_level": {"type": "string"},
                    "sentiment": {"type": "string"},
                    "representative_tweets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "author": {"type": "string"},
                                "text": {"type": "string"},
                                "url": {"type": "string"},
                                "likes": {"type": "integer"},
                                "retweets": {"type": "integer"},
                            },
                            "required": ["author", "text"],
                        },
                    },
                },
                "required": ["topic", "description", "buzz_level"],
            },
        },
    },
    "required": ["trend_summary", "trend_evolution", "top_articles", "category_summaries", "action_items", "x_trends"],
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
        recent_analyses = self._load_recent_analyses(count=5)
        analysis = self._stage2_analyze(top_items, items_by_id, recent_analyses)

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
        fallback = self.models.get("fallback", "gemini-2.5-flash")
        result = self._call_gemini(model, prompt, STAGE1_SCHEMA, budget, fallback_model=fallback)
        return result.get("scored_items", [])

    def _compress_items_for_stage1(self, items: list[dict]) -> str:
        lines: list[str] = []
        for it in items:
            eng = it.get("engagement", {})
            eng_str = ""
            if eng.get("likes") or eng.get("retweets"):
                eng_str = f" | ❤️{eng.get('likes', 0)} 🔁{eng.get('retweets', 0)}"
                if eng.get("views"):
                    eng_str += f" 👁{eng['views']}"

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

            if item.get("source") == "x":
                likes = item.get("engagement", {}).get("likes", 0)
                for tier in self.scoring_cfg.get("x_engagement_bonus", []):
                    if likes >= tier["likes"]:
                        bonus += tier["bonus"]
                        break

            s["bonus"] = bonus
            s["final_score"] = min(10.0, s.get("importance_score", 0) + bonus)

        return scored

    # ── Stage 2 ───────────────────────────────────────────────────────

    def _stage2_analyze(
        self, top_items: list[dict], items_by_id: dict, recent_analyses: list[dict]
    ) -> dict:
        model = self.models.get("stage2_analysis", "gemini-2.5-pro")
        budget = self.thinking.get("stage2", 1024)

        items_text = self._format_items_for_stage2(top_items, items_by_id)
        prev_context = self._format_previous_context(recent_analyses)
        categories_str = ", ".join(self.categories)

        prompt = f"""あなたはシニアAI産業アナリストです。本日のAIニューストップ記事を包括的に分析してください。

===== 本日の注目記事 (スコア順、{len(top_items)}件) =====
{items_text}

{prev_context}

===== 出力要件 =====
すべて日本語で出力してください。

1. trend_summary: 今日のAI界の最重要動向を3〜5文で概説
2. trend_evolution: 過去データと今回を照合し、トレンドの推移を分析してください。
   - since_last: 前回の配信から何が変わったかを1段落 (3〜4文) で簡潔にまとめる。新たに浮上した話題、勢いが増した話題、沈静化した話題を含める
   - tracked_topics: 主要トピック (5〜8件) ごとに以下を付与:
     - topic: トピック名（短く具体的に）
     - status: 以下のいずれか
       "NEW" (今回初登場) / "RISING" (前回より盛り上がり拡大) /
       "SUSTAINED" (安定して継続) / "FADING" (勢い低下) /
       "RESURFACED" (一度消えて再浮上)
     - streak_days: 何日連続で話題になっているか (初登場は1)
     - evolution: 時系列でどう変化したか (1文。例: "初報→米当局が動く→規制議論に発展")
   (過去データがない場合は since_last を "初回実行のため比較データなし" とし、全トピックを NEW にする)
3. top_articles: 重要度上位{self.top_n}件。各記事に rank, id, title, url, summary (1〜2文), importance_reason, category, source_label を含める
4. category_summaries: カテゴリ({categories_str})別の要約と主要記事 (最大5件)
5. action_items: ビジネスへの示唆・アクションアイテムを3〜5件
6. x_trends: X/Twitter で特に盛り上がっているトピックを5〜7件抽出。これは本レポートの重要セクションです。
   記事一覧の source=x のデータに着目し、以下の観点で分析してください:
   - エンゲージメント（いいね・RT・閲覧数）が突出して高い投稿
   - 複数のユーザーが同じテーマに言及しているもの
   - 公式アカウント発の情報に対するユーザーの反応

   各トピックに以下を含めてください:
   - topic: トピック名（短く具体的に）
   - description: なぜ盛り上がっているか・Xユーザーがどう反応しているか・議論の論点や対立軸があればそれも含めて（3〜4文で詳しく）
   - buzz_level: "high"（いいね5000+や複数バズ投稿） / "medium"（いいね1000+） / "low"
   - sentiment: "positive" / "negative" / "neutral" / "mixed"（賛否両論の場合）
   - representative_tweets: 代表的なツイート1〜3件（author, text, url, likes, retweets）。エンゲージメントが高い順に選定
"""
        fallback = self.models.get("fallback", "gemini-2.5-flash")
        result = self._call_gemini(model, prompt, STAGE2_SCHEMA, budget, fallback_model=fallback)

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

            eng = item.get("engagement", {})
            eng_parts = []
            if eng.get("likes"):
                eng_parts.append(f"❤️{eng['likes']}")
            if eng.get("retweets"):
                eng_parts.append(f"🔁{eng['retweets']}")
            if eng.get("views"):
                eng_parts.append(f"👁{eng['views']}")
            if eng.get("bookmarks"):
                eng_parts.append(f"🔖{eng['bookmarks']}")
            eng_str = f"  Engagement: {' '.join(eng_parts)}\n" if eng_parts else ""

            lines.append(
                f"[{s['id']}] Score: {s['final_score']:.1f} (LLM:{s.get('importance_score', 0)} +bonus:{s.get('bonus', 0):.1f}) | {s.get('category', '?')}{official}{must}\n"
                f"  Title: {item.get('title', '')}\n"
                f"  URL: {item.get('url', '')}\n"
                f"  Source: {item.get('source', '')}:{item.get('source_name', '')}\n"
                f"{eng_str}"
                f"  {item.get('content', '')[:500]}"
            )
        return "\n\n".join(lines)

    def _format_previous_context(self, recent: list[dict]) -> str:
        if not recent:
            return (
                "===== 過去の分析 =====\n"
                "過去データなし（初回実行）。trend_evolution.since_last は "
                "\"初回実行のため比較データなし\" とし、全トピックの status を \"NEW\" にしてください。"
            )

        parts = ["===== 過去の分析 (新しい順) ====="]

        for i, a in enumerate(recent):
            run_time = a.get("run_time", "?")[:16]
            slot = a.get("slot", "")
            label = f"[{i + 1}] {run_time} ({slot})"

            summary = a.get("trend_summary", "")[:200]
            parts.append(f"\n{label}")
            if summary:
                parts.append(f"  トレンド: {summary}")

            x_trends = a.get("x_trends", [])
            if x_trends:
                topics = [f"{t.get('topic', '')} ({t.get('buzz_level', '')})" for t in x_trends[:5]]
                parts.append(f"  X話題: {', '.join(topics)}")

            evo = a.get("trend_evolution", {})
            tracked = evo.get("tracked_topics", [])
            if tracked:
                evo_items = [f"{t.get('topic', '')}[{t.get('status', '')}]" for t in tracked[:5]]
                parts.append(f"  推移: {', '.join(evo_items)}")

            tops = a.get("top_articles", [])[:3]
            if tops:
                top_titles = [a.get("title", "")[:60] for a in tops]
                parts.append(f"  TOP3: {' / '.join(top_titles)}")

        return "\n".join(parts)

    # ── Gemini API 呼び出し ────────────────────────────────────────────

    def _call_gemini(
        self,
        model: str,
        prompt: str,
        schema: dict | None = None,
        thinking_budget: int = 128,
        fallback_model: str | None = None,
    ) -> dict:
        try:
            return self._call_gemini_single(model, prompt, schema, thinking_budget)
        except Exception as e:
            if fallback_model and self._is_server_error(e):
                logger.warning(
                    "Primary model %s exhausted retries, falling back to %s",
                    model, fallback_model,
                )
                return self._call_gemini_single(
                    fallback_model, prompt, schema, thinking_budget
                )
            raise

    @staticmethod
    def _is_server_error(exc: Exception) -> bool:
        for attr in ("status_code", "code"):
            try:
                code = int(getattr(exc, attr, 0) or 0)
                if code in (429, 500, 502, 503):
                    return True
            except (TypeError, ValueError):
                pass
        msg = str(exc).lower()
        return any(k in msg for k in ("503", "429", "unavailable", "overloaded", "quota", "resource_exhausted"))

    @retry(max_retries=4, base_delay=15, max_delay=120)
    def _call_gemini_single(
        self, model: str, prompt: str, schema: dict | None = None, thinking_budget: int = 128
    ) -> dict:
        from google.genai import types

        config_dict: dict = {
            "thinking_config": {"thinking_budget": thinking_budget},
            "http_options": types.HttpOptions(timeout=300_000),
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
        logger.info("Gemini responded in %.1fs (%s)", elapsed, model)

        text = response.text
        if not text:
            raise ValueError("Empty response from Gemini")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(1))
            else:
                logger.error("Failed to parse Gemini response: %s…", text[:500])
                raise

        if not isinstance(parsed, dict):
            raise ValueError(f"Expected dict from Gemini, got {type(parsed).__name__}")
        return parsed

    # ── 前日分析の読み込み / 保存 ──────────────────────────────────────

    def _load_recent_analyses(self, count: int = 5) -> list[dict]:
        """過去 count 回分の分析結果を新しい順で返す"""
        if not self.config.get("analysis", {}).get("enable_previous_day_context", True):
            return []

        analysis_dir = data_dir("analysis")
        if not os.path.isdir(analysis_dir):
            return []

        files = sorted(glob(os.path.join(analysis_dir, "*.json")), reverse=True)
        results: list[dict] = []
        for f in files[:count]:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    results.append(json.load(fh))
            except (json.JSONDecodeError, OSError):
                continue
        return results

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
            "trend_evolution": {"since_last": "", "tracked_topics": []},
            "top_articles": [],
            "category_summaries": [],
            "action_items": [],
            "x_trends": [],
        }

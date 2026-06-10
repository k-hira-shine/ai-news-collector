import unittest

from scripts.gemini_buzz_research import (
    DISCOVERY_QUERIES,
    USAGE_QUERIES,
    _accepted_posts,
    _dedupe,
    _query_with_dates,
    _queries_for_mode,
    classify_discovery,
    classify_relevance,
)


class GeminiBuzzResearchTests(unittest.TestCase):
    def test_accepts_usage_posts(self) -> None:
        result = classify_relevance(
            "Geminiで資料作成を効率化するプロンプトと手順をまとめました。"
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(result["filter_reason"], "usage")

    def test_rejects_promotional_posts(self) -> None:
        result = classify_relevance(
            "Geminiの使い方を無料配布。フォローしてリプするとDMします。"
        )

        self.assertFalse(result["accepted"])
        self.assertEqual(result["filter_reason"], "promotion")

    def test_marks_usage_announcement_for_review(self) -> None:
        result = classify_relevance(
            "Gemini新機能がリリース。使い方とworkflowを5ステップで解説します。"
        )

        self.assertTrue(result["accepted"])
        self.assertTrue(result["needs_review"])

    def test_marks_other_ai_mentions(self) -> None:
        result = classify_relevance(
            "GeminiとChatGPT、Claudeで同じプロンプトを比較しました。"
        )

        self.assertTrue(result["mentions_other_ai"])

    def test_marks_posts_requiring_external_details(self) -> None:
        result = classify_relevance(
            "Geminiの使い方をまとめました。詳しい手順はリプ欄に続きます。"
        )

        self.assertTrue(result["needs_external_detail"])

    def test_accepts_surprised_new_capability_post(self) -> None:
        result = classify_discovery(
            "oh my, Gemini 3 can generate an interactive 3D app from one text prompt. "
            "This is crazy."
        )

        self.assertTrue(result["is_discovery"])
        self.assertEqual(result["discovery_kind"], "surprise")

    def test_accepts_concrete_new_feature_without_hype(self) -> None:
        result = classify_discovery(
            "Gemini CLIの新しいSession Managementが登場。"
            "作業内容を自動保存し、前回の状態から再開できるようになりました。"
        )

        self.assertTrue(result["is_discovery"])
        self.assertEqual(result["discovery_kind"], "new_feature")

    def test_rejects_generic_prompt_hype(self) -> None:
        result = classify_discovery(
            "Geminiを使う人の9割が間違っている。神プロンプトをリプに置きます。"
        )

        self.assertFalse(result["is_discovery"])

    def test_rejects_incidental_gemini_workflow_mention(self) -> None:
        result = classify_discovery(
            "My workflow is Grok for research, Claude for tests, Gemini for checking, "
            "and Codex for debugging. Bookmark this."
        )

        self.assertFalse(result["is_discovery"])

    def test_query_has_bounded_dates(self) -> None:
        query = _query_with_dates("Gemini prompt", "2025-01-01", "2026-01-01")

        self.assertIn("since:2025-01-01", query)
        self.assertIn("until:2026-01-02", query)

    def test_discovery_mode_uses_dedicated_queries(self) -> None:
        queries = _queries_for_mode("discovery")

        self.assertEqual(queries, DISCOVERY_QUERIES)
        self.assertNotEqual(queries, USAGE_QUERIES)
        self.assertTrue(any("新機能" in query for query in queries))
        self.assertTrue(any("new feature" in query for query in queries))

    def test_discovery_mode_accepts_only_discovery_posts(self) -> None:
        posts = [
            {"is_discovery": True, "filter_reason": "news_only"},
            {"is_discovery": False, "accepted": True, "filter_reason": "usage"},
            {"is_discovery": True, "filter_reason": "promotion"},
        ]

        self.assertEqual(_accepted_posts(posts, "discovery"), [posts[0]])

    def test_dedupe_keeps_higher_engagement_snapshot(self) -> None:
        posts = [
            {"url": "https://x.com/a/status/1", "likes": 10},
            {"url": "https://x.com/a/status/1", "likes": 20},
        ]

        self.assertEqual(_dedupe(posts), [posts[1]])


if __name__ == "__main__":
    unittest.main()

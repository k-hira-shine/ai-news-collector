import unittest

from scripts.gemini_buzz_research import (
    _dedupe,
    _query_with_dates,
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

    def test_query_has_bounded_dates(self) -> None:
        query = _query_with_dates("Gemini prompt", "2025-01-01", "2026-01-01")

        self.assertIn("since:2025-01-01", query)
        self.assertIn("until:2026-01-02", query)

    def test_dedupe_keeps_higher_engagement_snapshot(self) -> None:
        posts = [
            {"url": "https://x.com/a/status/1", "likes": 10},
            {"url": "https://x.com/a/status/1", "likes": 20},
        ]

        self.assertEqual(_dedupe(posts), [posts[1]])


if __name__ == "__main__":
    unittest.main()

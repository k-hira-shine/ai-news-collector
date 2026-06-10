import unittest

from scripts.gemini_buzz_research import (
    DISCOVERY_QUERIES,
    FEATURE_EXPANSION_QUERIES,
    FEATURE_QUERIES,
    USAGE_QUERIES,
    _accepted_posts,
    _apply_discovery_reviews,
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

    def test_rejects_speculation_that_explicitly_denies_a_release(self) -> None:
        result = classify_discovery(
            "People are not ready for Gemini 3. Imagine what it can automate. "
            "Gemini 3 is not an app release; it is a phase transition."
        )

        self.assertFalse(result["is_discovery"])

    def test_rejects_incidental_gemini_workflow_mention(self) -> None:
        result = classify_discovery(
            "My workflow is Grok for research, Claude for tests, Gemini for checking, "
            "and Codex for debugging. Bookmark this."
        )

        self.assertFalse(result["is_discovery"])

    def test_rejects_other_product_release_that_only_mentions_gemini(self) -> None:
        result = classify_discovery(
            "We released Gemma 4, built from the same research as Gemini 3. "
            "Gemma can run on your own hardware."
        )

        self.assertFalse(result["is_discovery"])

    def test_rejects_notebooklm_feature_using_gemini_model(self) -> None:
        result = classify_discovery(
            "NotebookLMの新機能スライド資料がすごい。Gemini 3のデザイン力も発揮。"
        )

        self.assertFalse(result["is_discovery"])

    def test_rejects_other_google_product_powered_by_gemini(self) -> None:
        cases = [
            "NotebookLM gets Planning Mode powered by the released Gemini Omni.",
            "Introducing Prompt Expanders! This new Flow feature uses Gemini.",
            "Workspace Studio is now available in Japanese and integrates Gemini.",
            "Project Genie is a prototype powered by Genie 3 and Gemini.",
            "Use the Gemini image editor on FLORA to create a commercial video.",
        ]

        for text in cases:
            with self.subTest(text=text):
                self.assertFalse(classify_discovery(text)["is_discovery"])

    def test_rejects_engagement_bait(self) -> None:
        result = classify_relevance(
            "Geminiの新機能を解説します。いいねとリプ『作りたい』で教えて！"
        )

        self.assertEqual(result["filter_reason"], "promotion")

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

    def test_discovery_feature_profile_uses_feature_queries(self) -> None:
        queries = _queries_for_mode("discovery", "features")

        self.assertEqual(queries, FEATURE_QUERIES)
        self.assertTrue(any("Nano Banana" in query for query in queries))
        self.assertTrue(any("Deep Think" in query for query in queries))
        self.assertTrue(any("Gemini CLI" in query for query in queries))

    def test_usage_mode_rejects_feature_profile(self) -> None:
        with self.assertRaisesRegex(SystemExit, "require discovery"):
            _queries_for_mode("usage", "features")

    def test_discovery_expansion_profile_uses_additional_features(self) -> None:
        queries = _queries_for_mode("discovery", "feature-expansion")

        self.assertEqual(queries, FEATURE_EXPANSION_QUERIES)
        self.assertTrue(any("Robotics" in query for query in queries))
        self.assertTrue(any("Code Wiki" in query for query in queries))
        self.assertTrue(any("TTS" in query for query in queries))

    def test_discovery_mode_accepts_only_discovery_posts(self) -> None:
        posts = [
            {"is_discovery": True, "filter_reason": "news_only"},
            {"is_discovery": False, "accepted": True, "filter_reason": "usage"},
            {"is_discovery": True, "filter_reason": "promotion"},
        ]

        self.assertEqual(_accepted_posts(posts, "discovery"), [posts[0]])

    def test_ai_review_overrides_rule_label(self) -> None:
        post = {
            "url": "https://x.com/example/status/1",
            "text": "NotebookLM released a feature using Gemini.",
            "is_discovery": True,
            "discovery_kind": "new_feature",
            "discovery_score": 3,
        }
        from scripts.gemini_buzz_research import _text_hash

        reviews = {
            post["url"]: {
                "text_hash": _text_hash(post["text"]),
                "is_gemini_feature": False,
                "kind": "reject",
                "reason": "NotebookLM is the subject",
            }
        }

        result = _apply_discovery_reviews([post], reviews)[0]

        self.assertFalse(result["is_discovery"])
        self.assertTrue(result["discovery_reviewed"])

    def test_ai_review_cannot_revive_rule_rejection(self) -> None:
        post = {
            "url": "https://x.com/example/status/2",
            "text": "Gemma uses research related to Gemini.",
            "is_discovery": False,
            "discovery_kind": "",
        }
        from scripts.gemini_buzz_research import _text_hash

        reviews = {
            post["url"]: {
                "text_hash": _text_hash(post["text"]),
                "is_gemini_feature": True,
                "kind": "new_feature",
                "reason": "incorrect approval",
            }
        }

        result = _apply_discovery_reviews([post], reviews)[0]

        self.assertFalse(result["is_discovery"])

    def test_reject_kind_cannot_be_accepted(self) -> None:
        post = {
            "url": "https://x.com/example/status/3",
            "text": "Gemini released something.",
            "is_discovery": True,
            "discovery_kind": "new_feature",
        }
        from scripts.gemini_buzz_research import _text_hash

        reviews = {
            post["url"]: {
                "text_hash": _text_hash(post["text"]),
                "is_gemini_feature": True,
                "kind": "reject",
                "reason": "not a concrete feature",
            }
        }

        result = _apply_discovery_reviews([post], reviews)[0]

        self.assertFalse(result["is_discovery"])

    def test_dedupe_keeps_higher_engagement_snapshot(self) -> None:
        posts = [
            {"url": "https://x.com/a/status/1", "likes": 10},
            {"url": "https://x.com/a/status/1", "likes": 20},
        ]

        self.assertEqual(_dedupe(posts), [posts[1]])


if __name__ == "__main__":
    unittest.main()

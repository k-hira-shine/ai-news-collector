import unittest

from analyzer import NewsAnalyzer


class AnalyzerValidationTests(unittest.TestCase):
    def test_stage1_requires_scored_items_list(self) -> None:
        with self.assertRaisesRegex(ValueError, "scored_items"):
            NewsAnalyzer._validate_stage1_result({"scored_items": None})

    def test_stage2_requires_top_articles_list(self) -> None:
        payload = {
            "trend_summary": "summary",
            "trend_evolution": {"since_last": "delta", "tracked_topics": []},
            "top_articles": None,
            "category_summaries": [],
            "action_items": [],
            "x_trends": [],
        }
        with self.assertRaisesRegex(ValueError, "top_articles"):
            NewsAnalyzer._validate_stage2_result(payload)

    def test_stage2_accepts_valid_payload(self) -> None:
        payload = {
            "trend_summary": "summary",
            "trend_evolution": {"since_last": "delta", "tracked_topics": []},
            "top_articles": [],
            "category_summaries": [],
            "action_items": [],
            "x_trends": [],
        }
        self.assertIs(NewsAnalyzer._validate_stage2_result(payload), payload)


if __name__ == "__main__":
    unittest.main()

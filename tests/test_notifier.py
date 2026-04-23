import unittest

from notifier import DiscordNotifier


class StatsEmbedTests(unittest.TestCase):
    def setUp(self) -> None:
        # webhook 無しでもメソッドは動くので URL は空で OK
        self.n = DiscordNotifier(webhook_url="")

    def test_empty_stats_returns_none(self) -> None:
        self.assertIsNone(self.n._build_stats_embed({}))

    def test_apify_cost_zero_shows_measurement_lag(self) -> None:
        # apify_cost_usd=0 でも runs>0 なら行が出る（反映ラグ表示）
        embed = self.n._build_stats_embed({
            "total": 10, "x_count": 5, "rss_count": 3, "youtube_count": 2,
            "apify_runs": 2, "apify_cost_usd": 0,
        })
        self.assertIn("測定不可", embed["description"])
        self.assertIn("2回実行", embed["description"])

    def test_apify_cost_formatted(self) -> None:
        embed = self.n._build_stats_embed({
            "total": 10, "x_count": 5, "rss_count": 3, "youtube_count": 2,
            "apify_runs": 2, "apify_cost_usd": 0.0456,
        })
        self.assertIn("$0.0456", embed["description"])

    def test_budget_warning_line_appears_when_threshold_exceeded(self) -> None:
        embed = self.n._build_stats_embed({
            "total": 5, "apify_runs": 2, "apify_cost_usd": 0.05,
            "apify_cycle_total_usd": 25.0,
            "apify_monthly_budget_usd": 29.0,
            "apify_warning_threshold": 0.8,
        })
        self.assertIn("残高", embed["description"])

    def test_collection_breakdown_included(self) -> None:
        embed = self.n._build_stats_embed({
            "total": 10, "x_count": 5, "rss_count": 3, "youtube_count": 2,
        })
        self.assertIn("10件", embed["description"])
        self.assertIn("X: 5", embed["description"])


if __name__ == "__main__":
    unittest.main()

import unittest

from check_cost import build_tracking, summarize


class CheckCostTests(unittest.TestCase):
    def test_summarize_combines_workflow_runs_per_day(self) -> None:
        records = [
            {"date": "2026-06-10", "workflow": "collect", "apify_cost_usd": 0.1},
            {"date": "2026-06-10", "workflow": "collect", "apify_cost_usd": 0.2},
            {"date": "2026-06-10", "workflow": "buzz", "apify_cost_usd": 0.3},
        ]

        result = summarize(records)

        self.assertAlmostEqual(result["2026-06-10"]["collect"], 0.3)
        self.assertAlmostEqual(result["2026-06-10"]["buzz"], 0.3)

    def test_build_tracking_uses_calendar_days_and_target_range(self) -> None:
        records = [
            {"date": "2026-05-10", "workflow": "collect", "apify_cost_usd": 0.2},
            {"date": "2026-05-11", "workflow": "money", "apify_cost_usd": 0.4},
        ]
        plan = {
            "version": 1,
            "implementation_date": "2026-05-10",
            "baseline": {"daily_usd": 0.8},
            "projected_after": {
                "daily_usd": 0.3,
                "range_daily_usd": {"min": 0.2, "max": 0.4},
            },
            "measurement": {"rolling_average_days": 7},
        }

        tracking = build_tracking(records, plan)

        self.assertEqual(tracking["rolling"]["days"], 2)
        self.assertEqual(tracking["rolling"]["average_daily_usd"], 0.3)
        self.assertEqual(tracking["rolling"]["monthly_projection_usd"], 9.0)
        self.assertEqual(tracking["rolling"]["status"], "on_target")
        self.assertEqual(tracking["daily"][-1]["items_collected"]["money"], 0)

    def test_tracking_excludes_days_before_implementation(self) -> None:
        records = [
            {"date": "2026-05-09", "workflow": "collect", "apify_cost_usd": 1.0},
            {"date": "2026-05-10", "workflow": "collect", "apify_cost_usd": 0.2},
        ]
        plan = {
            "implementation_date": "2026-05-10",
            "baseline": {"daily_usd": 1.0},
            "projected_after": {
                "daily_usd": 0.3,
                "range_daily_usd": {"max": 0.4},
            },
            "measurement": {"rolling_average_days": 7},
        }

        tracking = build_tracking(records, plan)

        self.assertEqual(tracking["rolling"]["days"], 1)
        self.assertEqual(tracking["rolling"]["average_daily_usd"], 0.2)


if __name__ == "__main__":
    unittest.main()

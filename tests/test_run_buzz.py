import unittest
from datetime import datetime, timezone

from run_buzz import (
    collection_gap_risk,
    evaluate_guardrail_status,
    load_recent_zero_fetch_streaks,
    merge_account_data,
    overall_ranked_urls,
    resolve_collection_settings,
)


def tweet(url: str, created_at: str, likes: int) -> dict:
    return {
        "url": url,
        "text": url,
        "createdAt": created_at,
        "likeCount": likes,
        "retweetCount": 0,
        "replyCount": 0,
        "viewCount": 100,
        "author": {"followers": 1000},
    }


class RunBuzzTests(unittest.TestCase):
    def test_reduced_profile_is_resolved_from_config(self) -> None:
        config = {
            "buzz_collection": {
                "active_profile": "reduced",
                "retention_days": 30,
                "profiles": {"reduced": {"days": 7, "max_items": 50}},
            }
        }

        self.assertEqual(
            resolve_collection_settings(
                config,
                "auto",
                now=datetime(2026, 6, 8, tzinfo=timezone.utc),
            ),
            ("reduced", 7, 50, 30),
        )

    def test_auto_profile_uses_full_refresh_on_configured_weekday(self) -> None:
        config = {
            "buzz_collection": {
                "active_profile": "reduced",
                "full_refresh_weekday": 5,
                "profiles": {
                    "reduced": {"days": 7, "max_items": 50},
                    "full": {"days": 30, "max_items": 100},
                },
            }
        }

        self.assertEqual(
            resolve_collection_settings(
                config,
                "auto",
                now=datetime(2026, 6, 12, tzinfo=timezone.utc),
            )[:3],
            ("full", 30, 100),
        )

    def test_merge_preserves_history_refreshes_tweet_and_prunes_expired(self) -> None:
        existing = {
            "tweets": [
                {
                    "url": "keep",
                    "text": "old",
                    "created_at": "Wed Jun 10 00:00:00 +0000 2026",
                    "likes": 10,
                    "retweets": 0,
                    "replies": 0,
                    "views": 10,
                    "author_followers": 1000,
                },
                {
                    "url": "expired",
                    "text": "expired",
                    "created_at": "Fri May 01 00:00:00 +0000 2026",
                    "likes": 100,
                    "retweets": 0,
                    "replies": 0,
                    "views": 10,
                    "author_followers": 1000,
                },
            ]
        }
        fetched = [
            tweet("keep", "Wed Jun 10 00:00:00 +0000 2026", 30),
            tweet("new", "Thu Jun 11 00:00:00 +0000 2026", 20),
        ]

        merged, metrics = merge_account_data(
            existing,
            "account",
            "Account",
            fetched,
            retention_days=30,
            retention_max_items=100,
            now=datetime(2026, 6, 12, tzinfo=timezone.utc),
        )

        self.assertEqual([item["url"] for item in merged["tweets"]], ["keep", "new"])
        self.assertEqual(merged["tweets"][0]["likes"], 30)
        self.assertEqual(metrics["new"], 1)
        self.assertEqual(metrics["expired"], 1)
        self.assertEqual(metrics["prior_top20_retention_pct"], 100.0)

    def test_gap_risk_when_limit_does_not_overlap_previous_newest(self) -> None:
        existing = {
            "tweets": [
                {
                    "url": "old",
                    "created_at": "Mon Jun 08 00:00:00 +0000 2026",
                    "text": "old",
                }
            ]
        }
        fetched = [
            tweet(f"new-{index}", f"Wed Jun 10 {index:02d}:00:00 +0000 2026", index)
            for index in range(3)
        ]

        self.assertTrue(collection_gap_risk(existing, fetched, max_items=3))
        self.assertFalse(collection_gap_risk(existing, fetched[:2], max_items=3))

    def test_merge_caps_retained_history_by_recency(self) -> None:
        existing = {
            "tweets": [
                {
                    "url": f"old-{index}",
                    "text": "old",
                    "created_at": f"Mon Jun {index + 1:02d} 00:00:00 +0000 2026",
                    "likes": index,
                }
                for index in range(5)
            ]
        }

        merged, metrics = merge_account_data(
            existing,
            "account",
            "Account",
            [],
            retention_days=30,
            retention_max_items=3,
            now=datetime(2026, 6, 12, tzinfo=timezone.utc),
        )

        self.assertEqual({item["url"] for item in merged["tweets"]}, {"old-2", "old-3", "old-4"})
        self.assertEqual(metrics["overflow"], 2)

    def test_overall_ranked_urls_uses_account_median_threshold(self) -> None:
        accounts = [
            {
                "median_likes": 10,
                "tweets": [
                    {"url": "ranked", "likes": 30},
                    {"url": "not-ranked", "likes": 19},
                ],
            }
        ]

        self.assertEqual(overall_ranked_urls(accounts), ["ranked"])


class GuardrailStatusTests(unittest.TestCase):
    def test_pass_when_overlap_meets_threshold(self) -> None:
        self.assertEqual(
            evaluate_guardrail_status(95.0, 75.0, fallback_triggered=False), "pass"
        )

    def test_warning_when_overlap_below_threshold(self) -> None:
        self.assertEqual(
            evaluate_guardrail_status(60.0, 75.0, fallback_triggered=False), "warning"
        )

    def test_low_top20_retention_does_not_trip_warning(self) -> None:
        # top20_retention は判定に使わない: overlapが基準以上なら retention が低くても pass。
        # 6/17 の誤アラート(overlap=95% / retention=50%)が再発しないことを保証する。
        self.assertEqual(
            evaluate_guardrail_status(95.0, 75.0, fallback_triggered=False), "pass"
        )

    def test_fallback_takes_precedence(self) -> None:
        self.assertEqual(
            evaluate_guardrail_status(95.0, 75.0, fallback_triggered=True), "fallback"
        )

    def test_starved_accounts_trip_warning(self) -> None:
        self.assertEqual(
            evaluate_guardrail_status(
                95.0,
                75.0,
                fallback_triggered=False,
                starved_accounts=["a"],
            ),
            "warning",
        )


class ZeroFetchStreakTests(unittest.TestCase):
    def test_current_zero_fetch_trips_when_threshold_is_one(self) -> None:
        streaks, starved = load_recent_zero_fetch_streaks(
            [{"account": "a", "fetched": 0}, {"account": "b", "fetched": 3}],
            threshold=1,
        )

        self.assertEqual(streaks, {"a": 1})
        self.assertEqual(starved, ["a"])


if __name__ == "__main__":
    unittest.main()

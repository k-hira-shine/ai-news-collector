import unittest
from datetime import datetime, timedelta, timezone

from scripts.check_buzz_health import evaluate_health


class CheckBuzzHealthTests(unittest.TestCase):
    def test_recent_passing_metrics_are_healthy(self) -> None:
        now = datetime(2026, 6, 12, tzinfo=timezone.utc)
        metrics = {
            "checked_at": now.isoformat(),
            "profile": "reduced",
            "guardrail_status": "pass",
        }

        healthy, _ = evaluate_health(metrics, now)

        self.assertTrue(healthy)

    def test_stale_or_warning_metrics_fail(self) -> None:
        now = datetime(2026, 6, 12, tzinfo=timezone.utc)
        metrics = {
            "checked_at": (now - timedelta(days=5)).isoformat(),
            "profile": "reduced",
            "guardrail_status": "warning",
        }

        healthy, messages = evaluate_health(metrics, now)

        self.assertFalse(healthy)
        self.assertTrue(any("4日以上" in message for message in messages))

    def test_fresh_warning_fails_in_quality_mode(self) -> None:
        now = datetime(2026, 6, 12, tzinfo=timezone.utc)
        metrics = {
            "checked_at": now.isoformat(),
            "profile": "full",
            "guardrail_status": "warning",
        }

        healthy, messages = evaluate_health(metrics, now)

        self.assertFalse(healthy)
        self.assertTrue(any("ランキング" in message for message in messages))

    def test_warning_does_not_realarm_in_staleness_only_mode(self) -> None:
        # 直近収集(2日前)のwarning行を日次cronが再読みしても再アラートしない＝重複失敗メール抑制。
        now = datetime(2026, 6, 12, tzinfo=timezone.utc)
        metrics = {
            "checked_at": (now - timedelta(days=2)).isoformat(),
            "profile": "full",
            "guardrail_status": "warning",
        }

        healthy, messages = evaluate_health(metrics, now, quality_alarm=False)

        self.assertTrue(healthy)
        self.assertTrue(any("NOTICE" in message for message in messages))

    def test_staleness_only_still_fails_on_collection_gap(self) -> None:
        # 品質判定を切っても、収集が4日以上途絶していれば失敗させる。
        now = datetime(2026, 6, 12, tzinfo=timezone.utc)
        metrics = {
            "checked_at": (now - timedelta(days=5)).isoformat(),
            "profile": "full",
            "guardrail_status": "pass",
        }

        healthy, messages = evaluate_health(metrics, now, quality_alarm=False)

        self.assertFalse(healthy)
        self.assertTrue(any("4日以上" in message for message in messages))


if __name__ == "__main__":
    unittest.main()

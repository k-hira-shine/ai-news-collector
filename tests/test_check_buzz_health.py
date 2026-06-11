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


if __name__ == "__main__":
    unittest.main()

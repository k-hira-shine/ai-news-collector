import unittest
from unittest.mock import MagicMock, patch

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
            "total": 10, "x_count": 10,
            "apify_runs": 2, "apify_cost_usd": 0,
        })
        self.assertIn("測定不可", embed["description"])
        self.assertIn("2回実行", embed["description"])

    def test_apify_cost_formatted(self) -> None:
        embed = self.n._build_stats_embed({
            "total": 10, "x_count": 10,
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
            "total": 10, "x_count": 10,
        })
        self.assertIn("10件", embed["description"])
        self.assertIn("X: 10", embed["description"])


class SendPayloadRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.n = DiscordNotifier(webhook_url="https://discord.example/webhook")

    def _response(self, status_code: int, json_body: dict | None = None, text: str = ""):
        r = MagicMock()
        r.status_code = status_code
        r.json.return_value = json_body or {}
        r.text = text
        return r

    def test_200_is_success(self) -> None:
        with patch("notifier.requests.post", return_value=self._response(204)) as post:
            self.assertTrue(self.n._send_payload({"content": "x"}))
            self.assertEqual(post.call_count, 1)

    def test_5xx_is_retried_then_fails(self) -> None:
        # 3 retries + 1 attempt = 4 calls, all 503
        with patch("notifier.requests.post", return_value=self._response(503, text="unavailable")) as post, \
                patch("notifier.time.sleep"):  # skip backoff delays
            with self.assertRaises(Exception):
                self.n._send_payload({"content": "x"})
            self.assertEqual(post.call_count, 4)

    def test_5xx_then_200_succeeds(self) -> None:
        responses = [self._response(502), self._response(500), self._response(204)]
        with patch("notifier.requests.post", side_effect=responses), \
                patch("notifier.time.sleep"):
            self.assertTrue(self.n._send_payload({"content": "x"}))

    def test_400_is_not_retried(self) -> None:
        with patch("notifier.requests.post", return_value=self._response(400, text="bad request")) as post:
            self.assertFalse(self.n._send_payload({"content": "x"}))
            self.assertEqual(post.call_count, 1)

    def test_429_respects_retry_after(self) -> None:
        responses = [self._response(429, json_body={"retry_after": 0.01}), self._response(204)]
        with patch("notifier.requests.post", side_effect=responses), \
                patch("notifier.time.sleep") as sleep:
            self.assertTrue(self.n._send_payload({"content": "x"}))
            # retry_after に対応した sleep が呼ばれている
            sleep.assert_any_call(0.01)


if __name__ == "__main__":
    unittest.main()

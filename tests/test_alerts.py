import unittest

from alerts import build_alert_embed, detect_anomalies


def _stats(**overrides) -> dict:
    base = {
        "x_meta": {
            "has_apify": True,
            "has_cookies": True,
            "search_queries_configured": 3,
            "search_error_count": 0,
            "auth_error_count": 0,
            "search_total": 30,
            "must_follow_configured": 11,
            "must_follow_items": 20,
            "must_follow_error": False,
        },
        "rss_meta": {"feeds_configured": 10, "feed_error_count": 0, "raw_total": 100},
        "youtube_meta": {"keywords_configured": 5, "raw_total": 40},
        "analysis_meta": {
            "top_articles_count": 5,
            "fallback_used_stages": [],
            "save_ok": True,
            "save_path": "",
            "save_error": "",
        },
        "discord_meta": {"prev_run": {}},
        "apify_runs": 2,
        "youtube_count": 40,
        "apify_cycle_total_usd": 5.0,
        "apify_monthly_budget_usd": 29.0,
        "apify_warning_threshold": 0.8,
    }
    for k, v in overrides.items():
        if k in ("x_meta", "rss_meta", "youtube_meta", "analysis_meta", "discord_meta") and isinstance(v, dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


def _cfg(**overrides) -> dict:
    base = {
        "alerts": {
            "enabled": True,
            "rss_failure_rate_threshold": 0.3,
            "youtube_zero_results_alert": True,
            "analysis_json_save_alert": True,
            "discord_prev_run_alert": True,
        }
    }
    base["alerts"].update(overrides)
    return base


class DetectAnomaliesTests(unittest.TestCase):
    def test_healthy_run_no_alerts(self) -> None:
        self.assertEqual(detect_anomalies(_stats(), _cfg()), [])

    def test_all_search_queries_failed_is_critical(self) -> None:
        alerts = detect_anomalies(_stats(x_meta={"search_error_count": 3, "search_total": 0}), _cfg())
        titles = [a["title"] for a in alerts]
        self.assertTrue(any("全滅" in t for t in titles))
        self.assertEqual([a for a in alerts if "全滅" in a["title"]][0]["severity"], "critical")

    def test_partial_search_failure_is_warning(self) -> None:
        alerts = detect_anomalies(_stats(x_meta={"search_error_count": 1}), _cfg())
        matched = [a for a in alerts if "クエリが失敗" in a["title"]]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["severity"], "warning")

    def test_auth_error_is_critical(self) -> None:
        alerts = detect_anomalies(_stats(x_meta={"auth_error_count": 1}), _cfg())
        self.assertTrue(any("Cookie 認証エラー" in a["title"] for a in alerts))

    def test_must_follow_failure_is_critical(self) -> None:
        alerts = detect_anomalies(_stats(x_meta={"must_follow_error": True}), _cfg())
        self.assertTrue(any(a["severity"] == "critical" and "タイムライン" in a["title"] for a in alerts))

    def test_rss_high_failure_rate_is_critical(self) -> None:
        alerts = detect_anomalies(_stats(rss_meta={"feed_error_count": 6}), _cfg())  # 60%
        matched = [a for a in alerts if "RSS" in a["title"]]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["severity"], "critical")

    def test_rss_moderate_failure_rate_is_warning(self) -> None:
        alerts = detect_anomalies(_stats(rss_meta={"feed_error_count": 4}), _cfg())  # 40%
        matched = [a for a in alerts if "RSS" in a["title"]]
        self.assertEqual(matched[0]["severity"], "warning")

    def test_youtube_zero_raw_triggers_alert(self) -> None:
        alerts = detect_anomalies(
            _stats(youtube_meta={"raw_total": 0}, youtube_count=0), _cfg()
        )
        self.assertTrue(any("YouTube" in a["title"] for a in alerts))

    def test_youtube_zero_dedup_is_not_alert(self) -> None:
        # raw_total > 0 だけど重複排除で youtube_count=0 になったケース
        alerts = detect_anomalies(
            _stats(youtube_meta={"raw_total": 5}, youtube_count=0), _cfg()
        )
        self.assertFalse(any("YouTube" in a["title"] for a in alerts))

    def test_budget_80pct_is_warning(self) -> None:
        alerts = detect_anomalies(_stats(apify_cycle_total_usd=24.0), _cfg())
        self.assertTrue(any("予算" in a["title"] for a in alerts))

    def test_alerts_disabled_returns_empty(self) -> None:
        alerts = detect_anomalies(
            _stats(x_meta={"auth_error_count": 5}), _cfg(enabled=False)
        )
        self.assertEqual(alerts, [])

    def test_analysis_save_failure_is_critical(self) -> None:
        alerts = detect_anomalies(
            _stats(analysis_meta={"save_ok": False, "save_error": "disk full"}),
            _cfg(),
        )
        self.assertTrue(any("分析 JSON" in a["title"] for a in alerts))
        self.assertEqual(
            [a for a in alerts if "分析 JSON" in a["title"]][0]["severity"],
            "critical",
        )

    def test_discord_prev_run_failure_is_warning(self) -> None:
        alerts = detect_anomalies(
            _stats(
                discord_meta={
                    "prev_run": {
                        "ok": False,
                        "skipped": False,
                        "total": 2,
                        "failed_parts": ["msg0", "send_status"],
                    }
                }
            ),
            _cfg(),
        )
        self.assertTrue(any("前回の Discord" in a["title"] for a in alerts))

    def test_discord_prev_skipped_no_alert(self) -> None:
        alerts = detect_anomalies(
            _stats(
                discord_meta={"prev_run": {"ok": False, "skipped": True, "total": 0}}
            ),
            _cfg(),
        )
        self.assertFalse(any("前回の Discord" in a["title"] for a in alerts))

    def test_gemini_fallback_is_warning(self) -> None:
        alerts = detect_anomalies(
            _stats(analysis_meta={"fallback_used_stages": ["stage2"], "top_articles_count": 5}),
            _cfg(),
        )
        matched = [a for a in alerts if "Gemini" in a["title"]]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["severity"], "warning")
        self.assertIn("stage2", matched[0]["detail"])

    def test_no_fallback_no_alert(self) -> None:
        alerts = detect_anomalies(
            _stats(analysis_meta={"fallback_used_stages": [], "top_articles_count": 5}),
            _cfg(),
        )
        self.assertFalse(any("Gemini" in a["title"] for a in alerts))

    def test_diagram_png_failure_is_warning(self) -> None:
        alerts = detect_anomalies(
            _stats(diagram_meta={"attempted": True, "png_generated": False, "error": "Playwright timeout"}),
            _cfg(),
        )
        matched = [a for a in alerts if "図解" in a["title"]]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["severity"], "warning")
        self.assertIn("Playwright timeout", matched[0]["detail"])

    def test_diagram_not_attempted_no_alert(self) -> None:
        # top_articles が空で diagram ブロックをスキップしたケース
        alerts = detect_anomalies(
            _stats(diagram_meta={"attempted": False, "png_generated": False}),
            _cfg(),
        )
        self.assertFalse(any("図解" in a["title"] for a in alerts))

    def test_diagram_png_success_no_alert(self) -> None:
        alerts = detect_anomalies(
            _stats(diagram_meta={"attempted": True, "png_generated": True}),
            _cfg(),
        )
        self.assertFalse(any("図解" in a["title"] for a in alerts))

    def test_expected_runs_search_batched(self) -> None:
        # 検索バッチ化後は search+timeline=2 runs 期待
        alerts = detect_anomalies(_stats(apify_runs=1), _cfg())
        matched = [a for a in alerts if "起動回数" in a["title"]]
        self.assertEqual(len(matched), 1)
        self.assertIn("1/2", matched[0]["title"])


class BuildAlertEmbedTests(unittest.TestCase):
    def test_empty_returns_none(self) -> None:
        self.assertIsNone(build_alert_embed([]))

    def test_critical_color_and_icon(self) -> None:
        embed = build_alert_embed([{"severity": "critical", "title": "T", "detail": "D"}])
        self.assertEqual(embed["color"], 0xE74C3C)
        self.assertIn("🚨", embed["title"])

    def test_warning_only_color(self) -> None:
        embed = build_alert_embed([{"severity": "warning", "title": "T", "detail": "D"}])
        self.assertEqual(embed["color"], 0xF39C12)
        self.assertIn("⚠️", embed["title"])

    def test_description_truncated_to_4096(self) -> None:
        long_detail = "x" * 5000
        embed = build_alert_embed([{"severity": "warning", "title": "T", "detail": long_detail}])
        self.assertLessEqual(len(embed["description"]), 4096)


if __name__ == "__main__":
    unittest.main()

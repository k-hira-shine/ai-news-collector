import unittest

from daily_check import evaluate_run_status


class EvaluateRunStatusTests(unittest.TestCase):
    def test_missing_file_passes(self) -> None:
        ok, msg = evaluate_run_status(None)
        self.assertTrue(ok)
        self.assertIn("記録なし", msg)

    def test_all_success_passes(self) -> None:
        ok, _ = evaluate_run_status({
            "overall": "success",
            "workflows": {"collect": {"status": "success"}},
        })
        self.assertTrue(ok)

    def test_overall_error_fails(self) -> None:
        ok, msg = evaluate_run_status({
            "overall": "error",
            "workflows": {"collect": {"status": "error"}},
        })
        self.assertFalse(ok)
        self.assertIn("collect", msg)

    def test_critical_incident_fails_even_if_overall_warning(self) -> None:
        ok, msg = evaluate_run_status({
            "overall": "warning",
            "workflows": {"collect": {"status": "warning"}},
            "incident": {"active": "true", "severity": "critical", "title": "index.html 生成失敗"},
        })
        self.assertFalse(ok)
        self.assertIn("critical incident", msg)

    def test_warning_incident_is_advisory_not_failure(self) -> None:
        ok, msg = evaluate_run_status({
            "overall": "warning",
            "workflows": {"buzz": {"status": "warning"}},
            "incident": {"active": "true", "severity": "warning", "title": "starved"},
        })
        self.assertTrue(ok)
        self.assertIn("incident=warning", msg)


if __name__ == "__main__":
    unittest.main()

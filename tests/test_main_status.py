import unittest

from main import _status_for_anomalies


class MainStatusTests(unittest.TestCase):
    def test_no_anomalies_is_success(self) -> None:
        self.assertEqual(_status_for_anomalies([]), "success")

    def test_warning_anomaly_is_warning(self) -> None:
        self.assertEqual(
            _status_for_anomalies([{"severity": "warning", "title": "partial"}]),
            "warning",
        )

    def test_critical_anomaly_is_error(self) -> None:
        self.assertEqual(
            _status_for_anomalies([
                {"severity": "warning", "title": "partial"},
                {"severity": "critical", "title": "html failed"},
            ]),
            "error",
        )


if __name__ == "__main__":
    unittest.main()

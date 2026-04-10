import unittest

from collector import _default_x_runtime_meta, _should_warn_x_cookies


class CollectorCookieWarningTests(unittest.TestCase):
    def test_warns_only_for_clean_zero_result_searches(self) -> None:
        meta = _default_x_runtime_meta()
        meta.update(
            {
                "has_apify": True,
                "has_cookies": True,
                "search_queries_configured": 3,
                "search_total": 0,
                "search_error_count": 0,
            }
        )
        self.assertTrue(_should_warn_x_cookies(meta))

    def test_does_not_warn_when_search_queries_are_missing(self) -> None:
        meta = _default_x_runtime_meta()
        meta.update({"has_apify": True, "has_cookies": True})
        self.assertFalse(_should_warn_x_cookies(meta))

    def test_does_not_warn_when_search_failed(self) -> None:
        meta = _default_x_runtime_meta()
        meta.update(
            {
                "has_apify": True,
                "has_cookies": True,
                "search_queries_configured": 2,
                "search_total": 0,
                "search_error_count": 1,
            }
        )
        self.assertFalse(_should_warn_x_cookies(meta))


if __name__ == "__main__":
    unittest.main()

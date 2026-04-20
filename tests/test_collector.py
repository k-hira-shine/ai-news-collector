import unittest

from collector import (
    _AUTH_ERROR_PATTERN,
    _default_x_runtime_meta,
    _should_warn_x_cookies,
)


def _meta_with(**overrides) -> dict:
    meta = _default_x_runtime_meta()
    meta.update(
        {
            "has_apify": True,
            "has_cookies": True,
            "search_queries_configured": 3,
        }
    )
    meta.update(overrides)
    return meta


class CollectorCookieWarningTests(unittest.TestCase):
    def test_warns_when_auth_errors_detected_and_must_follow_empty(self) -> None:
        meta = _meta_with(
            search_total=0,
            auth_error_count=2,
            must_follow_configured=3,
            must_follow_items=0,
        )
        self.assertTrue(_should_warn_x_cookies(meta))

    def test_does_not_warn_on_plain_zero_results_without_auth_errors(self) -> None:
        """The old heuristic's false-positive case (Apify transient failure)."""
        meta = _meta_with(
            search_total=0,
            auth_error_count=0,
            must_follow_configured=3,
            must_follow_items=5,
        )
        self.assertFalse(_should_warn_x_cookies(meta))

    def test_does_not_warn_when_must_follow_succeeded(self) -> None:
        """If must-follow got items, the same cookies are clearly valid."""
        meta = _meta_with(
            search_total=0,
            auth_error_count=2,
            must_follow_configured=3,
            must_follow_items=4,
        )
        self.assertFalse(_should_warn_x_cookies(meta))

    def test_does_not_warn_without_cookies(self) -> None:
        meta = _meta_with(has_cookies=False, auth_error_count=1)
        self.assertFalse(_should_warn_x_cookies(meta))

    def test_does_not_warn_without_apify(self) -> None:
        meta = _meta_with(has_apify=False, auth_error_count=1)
        self.assertFalse(_should_warn_x_cookies(meta))

    def test_does_not_warn_when_search_queries_are_missing(self) -> None:
        meta = _meta_with(search_queries_configured=0, auth_error_count=1)
        self.assertFalse(_should_warn_x_cookies(meta))


class AuthErrorPatternTests(unittest.TestCase):
    def test_matches_common_auth_failure_phrases(self) -> None:
        samples = [
            "ERROR: login required",
            "WARN: Session expired, please re-authenticate",
            "401 Unauthorized",
            "403 Forbidden",
            "Authentication failed",
            "Invalid auth token",
            "cookies expired",
            "not logged in",
        ]
        for s in samples:
            with self.subTest(s=s):
                self.assertIsNotNone(_AUTH_ERROR_PATTERN.search(s))

    def test_ignores_unrelated_log_lines(self) -> None:
        samples = [
            "Fetched 40 tweets",
            "Timeout while scrolling feed",
            "Network error: ECONNRESET",
            "No tweets matched query",
        ]
        for s in samples:
            with self.subTest(s=s):
                self.assertIsNone(_AUTH_ERROR_PATTERN.search(s))


if __name__ == "__main__":
    unittest.main()

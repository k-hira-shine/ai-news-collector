import sys
import types
import unittest
from unittest import mock

import collector
from collector import (
    _AUTH_ERROR_PATTERN,
    _default_x_runtime_meta,
    _should_warn_x_cookies,
    _x_collection_settings,
    collect_x_twitter,
)


class _FakeDataset:
    def __init__(self, tweets):
        self._tweets = tweets

    def iterate_items(self):
        return iter(self._tweets)


class _FakeClient:
    """searchTerms[0] をキーに、そのクエリの返すツイートを引く擬似 Apify クライアント。"""

    def __init__(self, results_by_query):
        self._results_by_query = results_by_query
        self._datasets = {}

    def actor(self, actor_id):
        return ("actor", actor_id)

    def dataset(self, dataset_id):
        return _FakeDataset(self._datasets.get(dataset_id, []))


def _tweet(i):
    return {
        "url": f"https://x.com/u/status/{i}",
        "text": f"tweet body {i}",
        "author": {"userName": "u"},
    }


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


class XCollectionModeTests(unittest.TestCase):
    def test_light_mode_limits_accounts_and_items(self) -> None:
        config = {
            "runtime_mode": "light",
            "max_results_per_query": 150,
            "max_results_per_account": 30,
            "must_follow_accounts": [
                {"handle": "OpenAI"},
                {"handle": "AnthropicAI"},
                {"handle": "other"},
            ],
            "light_mode": {
                "max_results_per_query": 75,
                "max_results_per_account": 10,
                "must_follow_handles": ["OpenAI", "AnthropicAI"],
            },
        }

        max_query, max_account, accounts = _x_collection_settings(config)

        self.assertEqual(max_query, 75)
        self.assertEqual(max_account, 10)
        self.assertEqual([a["handle"] for a in accounts], ["OpenAI", "AnthropicAI"])

    def test_full_mode_keeps_all_accounts(self) -> None:
        accounts = [{"handle": "OpenAI"}, {"handle": "other"}]
        config = {
            "runtime_mode": "full",
            "max_results_per_query": 150,
            "max_results_per_account": 30,
            "must_follow_accounts": accounts,
        }

        self.assertEqual(_x_collection_settings(config), (150, 30, accounts))


class XSearchPerQueryTests(unittest.TestCase):
    """回帰防止: 検索クエリは1クエリ=1 actor run で呼ぶ。

    2026-06-21 に xquik/x-tweet-scraper の新ビルドで maxItems が
    「全searchTerms合算の上限」に変わり、7クエリを1 runにまとめていた旧実装で
    収集が約9割減した。各クエリを独立 run にすることで maxItems がクエリ毎に
    効くことを固定する。
    """

    def _run(self, results_by_query, *, max_per_query=150):
        queries = list(results_by_query.keys())
        config = {
            "x_twitter": {
                "search_queries": queries,
                "apify_actor": "xquik/x-tweet-scraper",
                "max_results_per_query": max_per_query,
                "must_follow_accounts": [],
            }
        }
        client = _FakeClient(results_by_query)
        run_inputs = []

        def fake_actor_call(actor, *, run_input, wait_seconds=300):
            run_inputs.append(run_input)
            term = run_input["searchTerms"][0]
            ds_id = f"ds::{term}"
            client._datasets[ds_id] = results_by_query.get(term, [])
            return {"status": "SUCCEEDED", "id": f"run::{term}", "defaultDatasetId": ds_id}

        def fake_run_get(run, key, default=None):
            return run.get(key, default)

        fake_apify_module = types.SimpleNamespace(ApifyClient=lambda token: client)
        meta = _default_x_runtime_meta()
        with mock.patch.dict(sys.modules, {"apify_client": fake_apify_module}), \
                mock.patch.dict("os.environ", {"APIFY_TOKEN": "x"}), \
                mock.patch.object(collector, "apify_actor_call", side_effect=fake_actor_call), \
                mock.patch.object(collector, "apify_run_get", side_effect=fake_run_get), \
                mock.patch.object(collector, "_get_apify_usage", return_value=None):
            items = collect_x_twitter(config, meta)
        return items, meta, run_inputs

    def test_calls_actor_once_per_query_with_single_term(self) -> None:
        results = {"q1": [_tweet(1), _tweet(2)], "q2": [_tweet(3)], "q3": []}
        items, meta, run_inputs = self._run(results)

        # クエリ数ぶん run が起き、各 run の searchTerms は必ず1語
        self.assertEqual(len(run_inputs), 3)
        for ri in run_inputs:
            self.assertEqual(len(ri["searchTerms"]), 1)
            self.assertEqual(ri["maxItems"], 150)
        self.assertEqual(meta["apify_runs"], 3)

    def test_collects_items_from_all_queries(self) -> None:
        results = {"q1": [_tweet(1), _tweet(2)], "q2": [_tweet(3)], "q3": []}
        items, meta, _ = self._run(results)

        # 全クエリ合算 = 3件（先頭クエリで枠を食い潰さない）
        self.assertEqual(len(items), 3)
        self.assertEqual(meta["search_total"], 3)


class XMustFollowPerAccountTests(unittest.TestCase):
    """回帰防止: 必須アカウントも1アカウント=1 actor run で呼ぶ。

    2026-06-23 に判明: 6/22 の障害対応では検索クエリだけ per-query 化し、
    must_follow は全アカウントを1 runにまとめたまま（searchTerms=[全handle]）
    残っていた。actor 新ビルドで maxItems が「合算上限」化したため
    must_follow が約1件/アカウントに飢餓した。各アカウントを独立 run にして
    maxItems がアカウント毎に効くことを固定する。
    """

    def _run(self, results_by_account, *, max_per_account=30):
        accounts = [{"handle": h, "priority": "normal"} for h in results_by_account]
        config = {
            "x_twitter": {
                "search_queries": [],
                "apify_actor": "xquik/x-tweet-scraper",
                "max_results_per_account": max_per_account,
                "must_follow_accounts": accounts,
            }
        }
        client = _FakeClient(results_by_account)
        run_inputs = []

        def fake_actor_call(actor, *, run_input, wait_seconds=300):
            run_inputs.append(run_input)
            term = run_input["searchTerms"][0]
            ds_id = f"ds::{term}"
            # term は "from:<handle> -filter:replies" 形式
            handle = term.split(":", 1)[1].split(" ", 1)[0]
            client._datasets[ds_id] = results_by_account.get(handle, [])
            return {"status": "SUCCEEDED", "id": f"run::{term}", "defaultDatasetId": ds_id}

        def fake_run_get(run, key, default=None):
            return run.get(key, default)

        fake_apify_module = types.SimpleNamespace(ApifyClient=lambda token: client)
        meta = _default_x_runtime_meta()
        with mock.patch.dict(sys.modules, {"apify_client": fake_apify_module}), \
                mock.patch.dict("os.environ", {"APIFY_TOKEN": "x"}), \
                mock.patch.object(collector, "apify_actor_call", side_effect=fake_actor_call), \
                mock.patch.object(collector, "apify_run_get", side_effect=fake_run_get), \
                mock.patch.object(collector, "_inspect_apify_run_log", return_value={}), \
                mock.patch.object(collector, "_get_apify_usage", return_value=None):
            items = collect_x_twitter(config, meta)
        return items, meta, run_inputs

    def test_calls_actor_once_per_account_with_single_term(self) -> None:
        results = {"a1": [_tweet(1)], "a2": [_tweet(2)], "a3": []}
        items, meta, run_inputs = self._run(results)

        # アカウント数ぶん run が起き、各 run の searchTerms は必ず1語
        self.assertEqual(len(run_inputs), 3)
        for ri in run_inputs:
            self.assertEqual(len(ri["searchTerms"]), 1)
            self.assertEqual(ri["maxItems"], 30)
        self.assertEqual(meta["apify_runs"], 3)

    def test_collects_items_from_all_accounts(self) -> None:
        results = {"a1": [_tweet(1), _tweet(2)], "a2": [_tweet(3)], "a3": []}
        items, meta, _ = self._run(results)

        # 全アカウント合算 = 3件（先頭アカウントで枠を食い潰さない）
        self.assertEqual(len(items), 3)
        self.assertEqual(meta["must_follow_items"], 3)

    def test_records_critical_zero_handles(self) -> None:
        # critical アカウントの個別沈黙（合計では隠れる）を meta に出すこと
        config = {
            "x_twitter": {
                "search_queries": [],
                "apify_actor": "xquik/x-tweet-scraper",
                "max_results_per_account": 30,
                "must_follow_accounts": [
                    {"handle": "OpenAI", "priority": "critical"},
                    {"handle": "xai", "priority": "critical"},
                    {"handle": "someblog", "priority": "normal"},
                ],
            }
        }
        # OpenAI は取得あり、xai(critical) は0件、normalの0は対象外
        results = {"OpenAI": [_tweet(1)], "xai": [], "someblog": []}
        client = _FakeClient(results)

        def fake_actor_call(actor, *, run_input, wait_seconds=300):
            term = run_input["searchTerms"][0]
            ds_id = f"ds::{term}"
            handle = term.split(":", 1)[1].split(" ", 1)[0]
            client._datasets[ds_id] = results.get(handle, [])
            return {"status": "SUCCEEDED", "id": f"run::{term}", "defaultDatasetId": ds_id}

        def fake_run_get(run, key, default=None):
            return run.get(key, default)

        fake_apify_module = types.SimpleNamespace(ApifyClient=lambda token: client)
        meta = _default_x_runtime_meta()
        with mock.patch.dict(sys.modules, {"apify_client": fake_apify_module}), \
                mock.patch.dict("os.environ", {"APIFY_TOKEN": "x"}), \
                mock.patch.object(collector, "apify_actor_call", side_effect=fake_actor_call), \
                mock.patch.object(collector, "apify_run_get", side_effect=fake_run_get), \
                mock.patch.object(collector, "_inspect_apify_run_log", return_value={}), \
                mock.patch.object(collector, "_fetch_apify_run_log", return_value=""), \
                mock.patch.object(collector, "_get_apify_usage", return_value=None):
            collect_x_twitter(config, meta)

        self.assertEqual(meta["must_follow_critical_total"], 2)
        self.assertEqual(meta["must_follow_critical_zero"], ["xai"])  # criticalで0のもののみ


class XSingleTermInvariantTests(unittest.TestCase):
    """回帰防止(横断): collect_x_twitter の *すべての* actor 呼び出しが searchTerms 1語であること。

    2026-06-22 の修正は検索経路だけ per-query 化し must_follow 経路をバッチのまま取りこぼした
    （2026-06-23 発覚）。経路別テストに加え「どの経路でも searchTerms は必ず1語」という不変条件を
    1本で固定し、将来3本目の経路がバッチで追加されても即落ちるようにする。
    """

    def test_every_actor_call_uses_single_search_term(self) -> None:
        config = {
            "x_twitter": {
                "search_queries": ["q1", "q2"],
                "apify_actor": "xquik/x-tweet-scraper",
                "max_results_per_query": 150,
                "max_results_per_account": 30,
                "must_follow_accounts": [
                    {"handle": "a1", "priority": "normal"},
                    {"handle": "a2", "priority": "critical"},
                    {"handle": "a3", "priority": "normal"},
                ],
            }
        }
        client = _FakeClient({})
        run_inputs = []

        def fake_actor_call(actor, *, run_input, wait_seconds=300):
            run_inputs.append(run_input)
            term = run_input["searchTerms"][0]
            ds_id = f"ds::{term}"
            client._datasets[ds_id] = []
            return {"status": "SUCCEEDED", "id": f"run::{term}", "defaultDatasetId": ds_id}

        def fake_run_get(run, key, default=None):
            return run.get(key, default)

        fake_apify_module = types.SimpleNamespace(ApifyClient=lambda token: client)
        meta = _default_x_runtime_meta()
        with mock.patch.dict(sys.modules, {"apify_client": fake_apify_module}), \
                mock.patch.dict("os.environ", {"APIFY_TOKEN": "x"}), \
                mock.patch.object(collector, "apify_actor_call", side_effect=fake_actor_call), \
                mock.patch.object(collector, "apify_run_get", side_effect=fake_run_get), \
                mock.patch.object(collector, "_inspect_apify_run_log", return_value={}), \
                mock.patch.object(collector, "_fetch_apify_run_log", return_value=""), \
                mock.patch.object(collector, "_get_apify_usage", return_value=None):
            collect_x_twitter(config, meta)

        # 検索2 + アカウント3 = 5 run、各 run の searchTerms は必ず1語
        self.assertEqual(len(run_inputs), 5)
        for ri in run_inputs:
            self.assertEqual(
                len(ri["searchTerms"]), 1,
                f"バッチ呼び出しが復活している: {ri['searchTerms']}",
            )


if __name__ == "__main__":
    unittest.main()

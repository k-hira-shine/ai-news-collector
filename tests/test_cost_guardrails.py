import unittest
from types import SimpleNamespace
from unittest.mock import patch

from utils import MAX_ITEMS_HARD_CAP, clamp_max_items


class ClampMaxItemsTests(unittest.TestCase):
    def test_passes_through_normal_values(self) -> None:
        self.assertEqual(clamp_max_items(100, "x"), 100)
        self.assertEqual(clamp_max_items(MAX_ITEMS_HARD_CAP, "x"), MAX_ITEMS_HARD_CAP)

    def test_clamps_typo_that_would_blow_up_cost(self) -> None:
        # config.yaml で 150 を誤って 15000 にした想定。
        self.assertEqual(clamp_max_items(15000, "x_twitter.max_results_per_query"), MAX_ITEMS_HARD_CAP)

    def test_negative_becomes_zero(self) -> None:
        self.assertEqual(clamp_max_items(-5, "x"), 0)

    def test_non_int_falls_back_to_cap(self) -> None:
        self.assertEqual(clamp_max_items(None, "x"), MAX_ITEMS_HARD_CAP)
        self.assertEqual(clamp_max_items("abc", "x"), MAX_ITEMS_HARD_CAP)

    def test_numeric_string_is_accepted(self) -> None:
        self.assertEqual(clamp_max_items("200", "x"), 200)

    def test_custom_cap_is_respected(self) -> None:
        self.assertEqual(clamp_max_items(300, "x", cap=250), 250)


class GeminiCollectionGuardrailTests(unittest.TestCase):
    def test_gemini_x_collection_clamps_apify_max_items(self) -> None:
        from gemini_collector import collect_x_accounts

        captured_run_input = {}

        class FakeDataset:
            def iterate_items(self):
                return iter(())

        class FakeClient:
            def __init__(self, token: str) -> None:
                self.token = token

            def actor(self, actor_id: str):
                return SimpleNamespace(actor_id=actor_id)

            def dataset(self, dataset_id: str):
                return FakeDataset()

        def fake_apify_actor_call(actor, *, run_input: dict, wait_seconds: int = 300):
            captured_run_input.update(run_input)
            return {"status": "SUCCEEDED", "usageTotalUsd": 0, "defaultDatasetId": "dataset"}

        fake_apify_client = SimpleNamespace(ApifyClient=FakeClient)
        config = {
            "gemini_collection": {
                "enabled": True,
                "max_items_per_account": 15000,
                "x_accounts": [{"handle": "GoogleDeepMind", "label": "DeepMind"}],
            }
        }

        with patch.dict("os.environ", {"APIFY_TOKEN": "token"}), \
             patch.dict("sys.modules", {"apify_client": fake_apify_client}), \
             patch("utils.apify_actor_call", fake_apify_actor_call):
            self.assertEqual(collect_x_accounts(config), [])

        self.assertEqual(captured_run_input["maxItems"], MAX_ITEMS_HARD_CAP)


if __name__ == "__main__":
    unittest.main()

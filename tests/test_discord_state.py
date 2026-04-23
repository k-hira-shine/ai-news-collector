import unittest

from discord_state import merge_delivery_results


class MergeDeliveryResultsTests(unittest.TestCase):
    def test_empty(self) -> None:
        m = merge_delivery_results()
        self.assertTrue(m.get("skipped"))

    def test_all_skipped(self) -> None:
        a = {"ok": False, "skipped": True, "total": 0, "succeeded": 0, "failed_parts": []}
        m = merge_delivery_results(a, a)
        self.assertTrue(m.get("skipped"))

    def test_merges_failed_parts(self) -> None:
        a = {"ok": False, "skipped": False, "total": 2, "succeeded": 1, "failed_parts": ["msg0"]}
        b = {"ok": True, "skipped": False, "total": 1, "succeeded": 1, "failed_parts": []}
        m = merge_delivery_results(a, b)
        self.assertFalse(m["ok"])
        self.assertEqual(m["total"], 3)
        self.assertEqual(m["succeeded"], 2)
        self.assertEqual(m["failed_parts"], ["msg0"])


if __name__ == "__main__":
    unittest.main()

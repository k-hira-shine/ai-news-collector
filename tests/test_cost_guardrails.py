import unittest

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


if __name__ == "__main__":
    unittest.main()

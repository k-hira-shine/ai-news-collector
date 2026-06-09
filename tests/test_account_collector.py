import unittest

from account_collector import _account_since_date, items_for_accounts


class AccountCollectorTests(unittest.TestCase):
    def test_existing_account_uses_overlap_window(self) -> None:
        self.assertEqual(_account_since_date("2026-06-10", 2, 365), "2026-06-08")

    def test_items_are_filtered_case_insensitively_and_copied(self) -> None:
        source = [
            {"id": "1", "author": "Fiction_Log"},
            {"id": "2", "author": "someone_else"},
        ]

        result = items_for_accounts(source, [{"handle": "fiction_log"}])
        result[0]["money_source"] = True

        self.assertEqual([item["id"] for item in result], ["1"])
        self.assertNotIn("money_source", source[0])


if __name__ == "__main__":
    unittest.main()

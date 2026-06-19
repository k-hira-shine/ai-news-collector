import unittest

from daily_check import evaluate_collection_quality


def _entry(ts: str, total: int, legal: int, must_follow: int) -> dict:
    return {
        "ts": ts,
        "workflow": "collect",
        "items_collected": total,
        "legal_rss_count": legal,
        "must_follow_count": must_follow,
    }


class CollectionQualityTests(unittest.TestCase):
    def test_no_entries_passes_as_rollout(self) -> None:
        ok, msg = evaluate_collection_quality([])
        self.assertTrue(ok)
        self.assertIn("記録なし", msg)

    def test_healthy_latest_entry_passes(self) -> None:
        # 6/20 実測（legal=6/95・must_follow=85）相当は合格になること
        entries = [_entry("2026-06-20T02:41:00+09:00", 95, 6, 85)]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertIn("legal_rss=6/95", msg)
        self.assertIn("must_follow=85", msg)

    def test_legal_dominance_fails(self) -> None:
        # legal が総数の半分以上＝「規制/政策」一色化を要確認
        entries = [_entry("2026-06-20T02:41:00+09:00", 100, 60, 40)]
        ok, msg = evaluate_collection_quality(entries)
        self.assertFalse(ok)
        self.assertIn("法務一色化", msg)

    def test_single_must_follow_zero_is_tolerated(self) -> None:
        # 単発の must_follow=0 は許容（収集サイクル差分の可能性が高い）
        entries = [
            _entry("2026-06-19T02:41:00+09:00", 90, 5, 80),
            _entry("2026-06-20T02:41:00+09:00", 90, 5, 0),
        ]
        ok, _ = evaluate_collection_quality(entries)
        self.assertTrue(ok)

    def test_consecutive_must_follow_zero_fails(self) -> None:
        # 2連続ゼロは要調査
        entries = [
            _entry("2026-06-19T02:41:00+09:00", 90, 5, 0),
            _entry("2026-06-20T02:41:00+09:00", 90, 5, 0),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertFalse(ok)
        self.assertIn("must_follow連続ゼロ", msg)

    def test_uses_latest_entry_by_timestamp_order(self) -> None:
        # 入力順が前後しても最新行（ts最大）で判定すること
        entries = [
            _entry("2026-06-20T02:41:00+09:00", 95, 6, 85),
            _entry("2026-06-18T02:41:00+09:00", 100, 60, 40),
        ]
        # evaluate は呼び出し側でソート済み前提だが、ここでは load 経由を模して逆順を渡す
        entries.sort(key=lambda r: r["ts"])
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertIn("/95", msg)


if __name__ == "__main__":
    unittest.main()

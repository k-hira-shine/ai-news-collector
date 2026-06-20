import unittest

from daily_check import evaluate_collection_quality


def _entry(
    ts: str,
    total: int,
    legal: int,
    must_follow: int,
    x_mode: str = "full",
    feeds_total: int | None = None,
    feeds_ok: int | None = None,
    feeds_failed: int = 0,
) -> dict:
    e = {
        "ts": ts,
        "workflow": "collect",
        "items_collected": total,
        "legal_rss_count": legal,
        "must_follow_count": must_follow,
        "x_mode": x_mode,
    }
    if feeds_total is not None:
        e["legal_feeds_total"] = feeds_total
        e["legal_feeds_ok"] = feeds_ok if feeds_ok is not None else feeds_total
        e["legal_feeds_failed"] = feeds_failed
    return e


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

    def test_must_follow_drop_fires_on_full_runs(self) -> None:
        # 朝便(full)が直近full中央値の2割未満まで急減＝要確認
        entries = [
            _entry("2026-06-18T02:41:00+09:00", 95, 5, 80),
            _entry("2026-06-19T02:41:00+09:00", 95, 5, 85),
            _entry("2026-06-20T02:41:00+09:00", 95, 5, 90),
            _entry("2026-06-21T02:41:00+09:00", 7, 0, 5),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertFalse(ok)
        self.assertIn("must_follow急減", msg)

    def test_must_follow_drop_silent_until_enough_history(self) -> None:
        # full便の履歴が閾値未満（3件）の間は急減判定をしない＝ロールアウト互換
        entries = [
            _entry("2026-06-19T02:41:00+09:00", 95, 5, 85),
            _entry("2026-06-20T02:41:00+09:00", 95, 5, 90),
            _entry("2026-06-21T02:41:00+09:00", 7, 0, 5),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertNotIn("急減", msg)

    def test_mild_dip_within_ratio_tolerated(self) -> None:
        # 中央値の2割以上残っていれば通常変動として許容
        entries = [
            _entry("2026-06-18T02:41:00+09:00", 95, 5, 80),
            _entry("2026-06-19T02:41:00+09:00", 95, 5, 85),
            _entry("2026-06-20T02:41:00+09:00", 95, 5, 90),
            _entry("2026-06-21T02:41:00+09:00", 90, 5, 30),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertNotIn("急減", msg)

    def test_light_zero_runs_excluded_from_drop(self) -> None:
        # 夕便(light)の must_follow=0 は対象アカウントを絞るため正常＝full比較に混ぜない
        entries = [
            _entry("2026-06-18T02:41:00+09:00", 95, 5, 80, x_mode="full"),
            _entry("2026-06-18T16:10:00+09:00", 3, 1, 0, x_mode="light"),
            _entry("2026-06-19T02:41:00+09:00", 95, 5, 85, x_mode="full"),
            _entry("2026-06-19T16:10:00+09:00", 3, 1, 0, x_mode="light"),
            _entry("2026-06-20T02:41:00+09:00", 95, 5, 90, x_mode="full"),
            _entry("2026-06-21T02:41:00+09:00", 95, 5, 82, x_mode="full"),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertNotIn("急減", msg)

    def test_legal_zero_with_healthy_feeds_is_no_news(self) -> None:
        # legal_rss=0 でも生entriesを返すフィードがあれば「窓に新着なし」＝合格
        entries = [
            _entry("2026-06-21T02:41:00+09:00", 7, 0, 5, feeds_total=8, feeds_ok=6),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertIn("feeds 6/8健全", msg)
        self.assertNotIn("取得失敗", msg)

    def test_legal_zero_all_feeds_blind_is_fetch_failure(self) -> None:
        # 全フィードが生0件（feeds_ok=0）＝取得失敗の疑いで要確認
        entries = [
            _entry("2026-06-21T02:41:00+09:00", 7, 0, 5, feeds_total=8, feeds_ok=0, feeds_failed=3),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertFalse(ok)
        self.assertIn("取得失敗の疑い", msg)
        self.assertIn("失敗3", msg)

    def test_legal_feed_health_absent_stays_silent(self) -> None:
        # 旧ログ（feed健全性フィールドなし）は判定せず合格＝ロールアウト互換
        entries = [_entry("2026-06-20T02:41:00+09:00", 7, 0, 5)]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertNotIn("feeds", msg)
        self.assertNotIn("取得失敗", msg)

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

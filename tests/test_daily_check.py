import unittest
from datetime import date, datetime, timedelta, timezone

from daily_check import (
    EXPECTED_WORKFLOWS,
    TODO_STALE_DAYS,
    evaluate_actions_freshness,
    evaluate_analysis_structure,
    evaluate_collection_quality,
    format_backlog,
)

_NOW = datetime(2026, 6, 21, 19, 20, tzinfo=timezone.utc)  # = 6/21 04:20 JST


def _run(name: str, age_h: float, conclusion: str = "success") -> dict:
    created = _NOW - timedelta(hours=age_h)
    return {
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "createdAt": created.isoformat().replace("+00:00", "Z"),
    }


def _entry(
    ts: str,
    total: int,
    legal: int,
    must_follow: int,
    x_mode: str = "full",
    feeds_total: int | None = None,
    feeds_ok: int | None = None,
    feeds_failed: int = 0,
    x_valid: int | None = None,
    critical_zero: list | None = None,
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
    if x_valid is not None:
        e["x_valid_count"] = x_valid
    if critical_zero is not None:
        e["must_follow_critical_zero"] = critical_zero
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

    def test_single_light_must_follow_zero_is_tolerated(self) -> None:
        # 夕便(light)の単発 must_follow=0 は正常（フロアはfull便のみ・streakも単発許容）。
        # 直近のfull便が健全ならフロアも通る。
        entries = [
            _entry("2026-06-19T02:41:00+09:00", 90, 5, 80, x_mode="full", x_valid=200),
            _entry("2026-06-19T17:30:00+09:00", 10, 1, 0, x_mode="light", x_valid=35),
        ]
        ok, _ = evaluate_collection_quality(entries)
        self.assertTrue(ok)

    def test_full_must_follow_zero_fails_via_floor(self) -> None:
        # full便の must_follow=0 はフロアで即異常（0<8 なので残バグmf=8を捕まえる以上、
        # 0 を許容するのは論理矛盾＝旧「単発ゼロ許容」の甘さを廃止）。
        entries = [
            _entry("2026-06-19T02:41:00+09:00", 90, 5, 80, x_valid=200),
            _entry("2026-06-20T02:41:00+09:00", 90, 5, 0, x_valid=200),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertFalse(ok)
        self.assertIn("must_followフロア割れ", msg)

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
        # full便の履歴が閾値未満（3件）の間は相対急減判定をしない＝ロールアウト互換。
        # フロアを割らない値（mf=30≥25・items=50≥40）で相対判定の沈黙だけを検証する。
        entries = [
            _entry("2026-06-19T02:41:00+09:00", 95, 5, 85),
            _entry("2026-06-20T02:41:00+09:00", 95, 5, 90),
            _entry("2026-06-21T02:41:00+09:00", 50, 5, 30),
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

    def test_volume_drop_advisory_fires_but_keeps_pass(self) -> None:
        # 総量が直近full中央値の半分未満まで急減＝⚠ advisory。must_follow は健全なので
        # 既存の判定には引っかからず、advisory は合否(exit code)を変えない＝ok=True のまま。
        # 2026-06-21 のApify仕様変更による9割減（must_follow一色化に非該当）を捕まえる型。
        # フロアは割らず（items=44≥40・mf=30≥25）、相対の半減だけで advisory を出す型。
        entries = [
            _entry("2026-06-18T02:41:00+09:00", 95, 5, 80),
            _entry("2026-06-19T02:41:00+09:00", 95, 5, 85),
            _entry("2026-06-20T02:41:00+09:00", 95, 5, 90),
            _entry("2026-06-21T02:41:00+09:00", 95, 5, 82),
            _entry("2026-06-22T02:41:00+09:00", 44, 1, 30),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)  # advisory は合否を変えない
        self.assertIn("収集量急減", msg)
        self.assertIn("⚠", msg)

    def test_volume_drop_silent_until_enough_history(self) -> None:
        # full便の履歴が閾値（4件）以下の間は収集量advisoryを出さない＝ロールアウト互換
        entries = [
            _entry("2026-06-19T02:41:00+09:00", 95, 5, 85),
            _entry("2026-06-20T02:41:00+09:00", 95, 5, 90),
            _entry("2026-06-21T02:41:00+09:00", 95, 5, 82),
            _entry("2026-06-22T02:41:00+09:00", 44, 1, 30),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertNotIn("収集量急減", msg)

    def test_volume_mild_dip_tolerated(self) -> None:
        # 中央値の半分以上残っていれば通常変動として advisory を出さない
        entries = [
            _entry("2026-06-18T02:41:00+09:00", 95, 5, 80),
            _entry("2026-06-19T02:41:00+09:00", 95, 5, 85),
            _entry("2026-06-20T02:41:00+09:00", 95, 5, 90),
            _entry("2026-06-21T02:41:00+09:00", 95, 5, 82),
            _entry("2026-06-22T02:41:00+09:00", 60, 4, 50),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertNotIn("収集量急減", msg)

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

    # --- 絶対フロア（経路別・履歴非依存）。2026-06-23 の取りこぼし再発防止の本丸。 ---
    def test_must_follow_floor_fails_on_first_full_run(self) -> None:
        # 相対判定はベースライン汚染で盲目になったが、フロアは履歴1件でも即異常を出す。
        # 2026-06-23 朝便の must_follow残バグ相当（items=27/mf=8/x_valid=80）を確実に捕まえる。
        entries = [_entry("2026-06-23T03:28:00+09:00", 27, 4, 8, x_valid=80)]
        ok, msg = evaluate_collection_quality(entries)
        self.assertFalse(ok)
        self.assertIn("must_followフロア割れ", msg)
        self.assertIn("収集量フロア割れ", msg)
        self.assertIn("X取得フロア割れ", msg)

    def test_must_follow_floor_isolated(self) -> None:
        # 検索は健全(x_valid/items高)でも must_follow 単独の崩落を経路別フロアで捕まえる
        entries = [_entry("2026-06-23T03:28:00+09:00", 90, 4, 8, x_valid=200)]
        ok, msg = evaluate_collection_quality(entries)
        self.assertFalse(ok)
        self.assertIn("must_followフロア割れ", msg)
        self.assertNotIn("収集量フロア割れ", msg)
        self.assertNotIn("X取得フロア割れ", msg)

    def test_x_valid_floor_isolated(self) -> None:
        entries = [_entry("2026-06-23T03:28:00+09:00", 90, 4, 80, x_valid=110)]
        ok, msg = evaluate_collection_quality(entries)
        self.assertFalse(ok)
        self.assertIn("X取得フロア割れ", msg)

    def test_floors_pass_on_healthy_recovered_data(self) -> None:
        # 2026-06-23 修正後の実測（items=91/mf=82/x_valid=211）は合格しなければならない
        entries = [_entry("2026-06-23T05:04:00+09:00", 91, 5, 82, x_valid=211)]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertIn("x_valid=211", msg)

    def test_x_valid_floor_silent_when_absent(self) -> None:
        # 旧ログ（x_valid_count なし）では X取得フロアは沈黙＝ロールアウト互換
        entries = [_entry("2026-06-20T02:41:00+09:00", 95, 6, 85)]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertNotIn("X取得フロア割れ", msg)

    def test_floors_skip_when_only_light_runs(self) -> None:
        # full便が無い（夕便lightのみ）ときフロアは評価しない＝lightの低値で誤検知しない
        entries = [_entry("2026-06-23T17:30:00+09:00", 10, 1, 0, x_mode="light", x_valid=35)]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertNotIn("フロア割れ", msg)

    def test_floors_evaluate_latest_full_even_when_light_is_last(self) -> None:
        # 最後が夕便lightでも、直近のfull便がフロアを割っていれば検知する
        entries = [
            _entry("2026-06-23T03:28:00+09:00", 27, 4, 8, x_mode="full", x_valid=80),
            _entry("2026-06-23T17:30:00+09:00", 10, 1, 0, x_mode="light", x_valid=35),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertFalse(ok)
        self.assertIn("フロア割れ", msg)

    # --- じわ減り（固定リファレンス比・連続）。フロアの上で続く慢性劣化を捕まえる。 ---
    def test_erosion_fires_on_sustained_above_floor_drop(self) -> None:
        # must_follow がフロア(25)の上だが健全比50%(40)未満で2連続＝じわ減りで要確認
        entries = [
            _entry("2026-06-22T02:41:00+09:00", 90, 5, 35, x_valid=200),
            _entry("2026-06-23T02:41:00+09:00", 90, 5, 30, x_valid=200),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertFalse(ok)
        self.assertIn("must_followじわ減り", msg)

    def test_erosion_silent_on_single_dip(self) -> None:
        # 単発の落ち込み（直近1便のみ痩せ）は許容＝連続を要求するので発火しない
        entries = [
            _entry("2026-06-22T02:41:00+09:00", 90, 5, 82, x_valid=200),
            _entry("2026-06-23T02:41:00+09:00", 90, 5, 35, x_valid=200),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertNotIn("じわ減り", msg)

    def test_erosion_silent_when_x_valid_absent(self) -> None:
        # 旧ログ（x_valid なし）では x_valid のじわ減り判定は沈黙＝ロールアウト互換
        entries = [
            _entry("2026-06-22T02:41:00+09:00", 90, 5, 82),
            _entry("2026-06-23T02:41:00+09:00", 90, 5, 82),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertNotIn("じわ減り", msg)

    # --- critical アカウントの個別沈黙（advisory・合否非影響） ---
    def test_critical_dark_advisory_fires_on_consecutive_zero(self) -> None:
        # あるcriticalアカウントが3連続ゼロ＝合計must_followは健全でも個別沈黙をadvisory表示
        entries = [
            _entry("2026-06-21T02:41:00+09:00", 95, 5, 82, x_valid=200, critical_zero=["OpenAI"]),
            _entry("2026-06-22T02:41:00+09:00", 95, 5, 82, x_valid=200, critical_zero=["OpenAI"]),
            _entry("2026-06-23T02:41:00+09:00", 95, 5, 82, x_valid=200, critical_zero=["OpenAI", "xai"]),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)  # advisory は合否を変えない
        self.assertIn("criticalアカウント沈黙", msg)
        self.assertIn("OpenAI", msg)
        self.assertNotIn("xai", msg)  # 全便で連続している handle のみ（xaiは最新便だけ）

    def test_critical_dark_silent_when_not_consecutive(self) -> None:
        entries = [
            _entry("2026-06-21T02:41:00+09:00", 95, 5, 82, x_valid=200, critical_zero=["OpenAI"]),
            _entry("2026-06-22T02:41:00+09:00", 95, 5, 82, x_valid=200, critical_zero=[]),
            _entry("2026-06-23T02:41:00+09:00", 95, 5, 82, x_valid=200, critical_zero=["OpenAI"]),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertNotIn("沈黙", msg)

    def test_critical_dark_silent_until_history(self) -> None:
        # 履歴が CRITICAL_DARK_STREAK 未満の間は判定しない＝ロールアウト互換
        entries = [
            _entry("2026-06-22T02:41:00+09:00", 95, 5, 82, x_valid=200, critical_zero=["OpenAI"]),
            _entry("2026-06-23T02:41:00+09:00", 95, 5, 82, x_valid=200, critical_zero=["OpenAI"]),
        ]
        ok, msg = evaluate_collection_quality(entries)
        self.assertTrue(ok)
        self.assertNotIn("沈黙", msg)

    def test_legal_zero_with_healthy_feeds_is_no_news(self) -> None:
        # legal_rss=0 でも生entriesを返すフィードがあれば「窓に新着なし」＝合格。
        # フィード判定を単独で検証するため収集量はフロア健全（95/85）にする。
        entries = [
            _entry("2026-06-21T02:41:00+09:00", 95, 0, 85, feeds_total=8, feeds_ok=6),
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
        # 旧ログ（feed健全性フィールドなし）は判定せず合格＝ロールアウト互換。
        # フィード判定の単独検証のため収集量はフロア健全（95/85）にする。
        entries = [_entry("2026-06-20T02:41:00+09:00", 95, 0, 85)]
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


class ActionsFreshnessTests(unittest.TestCase):
    def _all_fresh(self) -> dict:
        # 各期待workflowを「許容age内」で用意（buzz-collectは週末ギャップ想定の50h）
        return {
            "AI News Collector": _run("AI News Collector", 2),
            "AI Money Cases Collector": _run("AI Money Cases Collector", 2),
            "Buzz Daily Health Check": _run("Buzz Daily Health Check", 23),
            "Buzz Ranking Collector": _run("Buzz Ranking Collector", 50),
        }

    def test_all_within_cadence_passes(self) -> None:
        self.assertEqual(evaluate_actions_freshness(self._all_fresh(), _NOW), [])

    def test_missing_workflow_flagged(self) -> None:
        # 6/21(日)実測の再現: Buzz Ranking が窓から漏れ・個別取得もできず不在
        latest = self._all_fresh()
        del latest["Buzz Ranking Collector"]
        problems = evaluate_actions_freshness(latest, _NOW)
        self.assertEqual(problems, ["Buzz Ranking Collector=実行記録なし"])

    def test_stale_daily_workflow_flagged(self) -> None:
        # 毎日便が30h前＝26h上限超過でサイレント停止を検知
        latest = self._all_fresh()
        latest["AI News Collector"] = _run("AI News Collector", 30)
        problems = evaluate_actions_freshness(latest, _NOW)
        self.assertIn("AI News Collector=stale 30h(>26h)", problems)

    def test_weekend_gap_not_false_positive(self) -> None:
        # 月水金便がFri→Sunで最大72hでもfullの84h上限内＝誤検知しない
        latest = self._all_fresh()
        latest["Buzz Ranking Collector"] = _run("Buzz Ranking Collector", 71)
        self.assertEqual(evaluate_actions_freshness(latest, _NOW), [])

    def test_dead_buzz_collector_eventually_flagged(self) -> None:
        # 月水金便が84h超＝週末ギャップでは説明できない停止を検知
        latest = self._all_fresh()
        latest["Buzz Ranking Collector"] = _run("Buzz Ranking Collector", 90)
        problems = evaluate_actions_freshness(latest, _NOW)
        self.assertIn("Buzz Ranking Collector=stale 90h(>84h)", problems)

    def test_registry_covers_scheduled_workflows(self) -> None:
        names = {n for n, _f, _a in EXPECTED_WORKFLOWS}
        self.assertIn("Buzz Ranking Collector", names)
        self.assertEqual(len(EXPECTED_WORKFLOWS), 4)


class BacklogTests(unittest.TestCase):
    TODAY = date(2026, 6, 21)

    def test_empty_returns_no_footer(self) -> None:
        self.assertEqual(format_backlog([], self.TODAY), [])

    def test_orders_oldest_first(self) -> None:
        items = [
            {"title": "新しい宿題", "since": "2026-06-20"},
            {"title": "古い宿題", "since": "2026-05-01"},
        ]
        lines = format_backlog(items, self.TODAY)
        self.assertIn("未了TODO 2件", lines[0])
        self.assertIn("古い宿題", lines[1])  # 古い方が上
        self.assertIn("新しい宿題", lines[2])

    def test_age_and_stale_marker(self) -> None:
        # since から TODO_STALE_DAYS 以上経過で ⚠️ が付く
        old = (self.TODAY - timedelta(days=TODO_STALE_DAYS + 5)).isoformat()
        fresh = (self.TODAY - timedelta(days=3)).isoformat()
        lines = format_backlog(
            [{"title": "長期案件", "since": old}, {"title": "最近案件", "since": fresh}],
            self.TODAY,
        )
        stale_line = next(l for l in lines if "長期案件" in l)
        fresh_line = next(l for l in lines if "最近案件" in l)
        self.assertIn("⚠️", stale_line)
        self.assertIn(f"[{TODO_STALE_DAYS + 5}d]", stale_line)
        self.assertNotIn("⚠️", fresh_line)
        self.assertIn("[3d]", fresh_line)

    def test_missing_since_is_tolerated(self) -> None:
        lines = format_backlog([{"title": "日付なし宿題"}], self.TODAY)
        self.assertIn("[?]", lines[1])
        self.assertIn("日付なし宿題", lines[1])

    def test_note_is_appended(self) -> None:
        lines = format_backlog(
            [{"title": "宿題", "since": "2026-06-20", "note": "補足メモ"}], self.TODAY
        )
        self.assertIn("— 補足メモ", lines[1])


class AnalysisStructureTests(unittest.TestCase):
    def _analysis(self, top, cat, action, fallback=None, item_count=50, slot="morning") -> dict:
        return {
            "top_articles": [{}] * top,
            "category_summaries": [{}] * cat,
            "action_items": [""] * action,
            "fallback_used_stages": fallback or [],
            "item_count": item_count,
            "slot": slot,
        }

    def test_healthy_structure_passes(self) -> None:
        ok, msg = evaluate_analysis_structure(self._analysis(10, 5, 5))
        self.assertTrue(ok)
        self.assertIn("top=10/cat=5/action=5/fallback=0", msg)

    def test_low_volume_day_not_false_positive(self) -> None:
        # 6/21実測（item=7・top=2/cat=2/action=4）は低ニュース日で正常＝合格
        ok, _ = evaluate_analysis_structure(self._analysis(2, 2, 4, item_count=7))
        self.assertTrue(ok)

    def test_fallback_flagged(self) -> None:
        ok, msg = evaluate_analysis_structure(
            self._analysis(10, 5, 5, fallback=["stage2"])
        )
        self.assertFalse(ok)
        self.assertIn("fallback=stage2", msg)

    def test_zero_top_with_items_flagged(self) -> None:
        ok, msg = evaluate_analysis_structure(self._analysis(0, 0, 0, item_count=30))
        self.assertFalse(ok)
        self.assertIn("top_articles=0", msg)

    def test_zero_top_without_items_tolerated(self) -> None:
        # item=0（収集なし）なら top=0 は当然＝合格
        ok, _ = evaluate_analysis_structure(self._analysis(0, 0, 0, item_count=0))
        self.assertTrue(ok)

    def test_top_without_category_flagged(self) -> None:
        ok, msg = evaluate_analysis_structure(self._analysis(5, 0, 5, item_count=40))
        self.assertFalse(ok)
        self.assertIn("category_summaries=0", msg)

    def test_zero_action_with_items_flagged(self) -> None:
        ok, msg = evaluate_analysis_structure(self._analysis(5, 3, 0, item_count=40))
        self.assertFalse(ok)
        self.assertIn("action_items=0", msg)

    def test_no_record_passes(self) -> None:
        ok, msg = evaluate_analysis_structure({})
        self.assertTrue(ok)
        self.assertIn("記録なし", msg)


if __name__ == "__main__":
    unittest.main()

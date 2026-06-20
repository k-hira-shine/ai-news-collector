#!/usr/bin/env python3
"""日次運用チェックを1コマンドに集約する。

「今日のチェック」で見る4点を合否サマリで出す:
  1. GitHub Actions の直近成否＋期待スケジュールの不在/stale検知（gh CLI、未認証ならスキップ）
  2. Apify コスト（施策後フロア窓の月額換算。check_cost.py と同じ計測ロジック）
  3. Gemini コスト（直近数日の日額）
  4. Buzz メトリクス最終行の鮮度と guardrail
  5. 収集品質（法務一色化・must_follow連続ゼロ・must_follow急減。data/logs の collect 行から）
  6. 分析構造（top/cat/action/fallback の構造完全性。data/analysis の最新便から）

使い方:
  python3 daily_check.py            # サマリ表示
  python3 daily_check.py --days 5   # Gemini/表示日数を変更
終了コード: すべて合格なら 0、要確認があれば 1。
"""

import argparse
import json
import subprocess
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from check_cost import build_tracking, load_logs, load_plan
from scripts.check_buzz_health import evaluate_health, load_latest_metrics

BASE = Path(__file__).resolve().parent
GEMINI_USAGE_DIR = BASE / "data" / "gemini_usage"
LOGS_DIR = BASE / "data" / "logs"
ANALYSIS_DIR = BASE / "data" / "analysis"
BACKLOG_PATH = BASE / "ops_backlog.yaml"
_SLOT_ORDER = {"morning": 0, "evening": 1}  # 同日内の便の時系列
JST = timezone(timedelta(hours=9))
REPO = "k-hira-shine/ai-news-collector"
TODO_STALE_DAYS = 30  # これ以上未了なら ⚠️ を付けて軽く催促（合否には影響しない）

# 品質監視の閾値（[[daily-check-routine]] の「残監視2点」をコード化）
LEGAL_DOMINANCE_RATIO = 0.5   # legal_rss_count/total がこれ以上なら「規制/政策」一色化を疑う
MUST_FOLLOW_ZERO_STREAK = 2   # must_follow_count=0 がこの連続回数で要調査（単発は許容）
# must_follow 急減検知: 朝便(full)の must_follow が直近中央値のこの割合未満なら要確認。
# 夕便(light)は対象アカウントを絞るため0が正常 → full便のみで比較する。
MUST_FOLLOW_DROP_RATIO = 0.2
# full便の履歴がこの件数貯まるまで急減判定はしない（ロールアウト互換＝当面は沈黙）。
MUST_FOLLOW_DROP_MIN_PRIORS = 3

OK = "✅"
WARN = "⚠️"


def _line(label: str, ok: bool, detail: str) -> tuple[bool, str]:
    return ok, f"{OK if ok else WARN} {label}: {detail}"


# 期待するスケジュール済みワークフロー（表示名, ワークフローファイル, 最大許容age時間）。
# gh run list の窓に出ない＝サイレント停止を検知するため、cadence＋余裕でstaleを判定する。
EXPECTED_WORKFLOWS = [
    ("AI News Collector", "collect.yml", 26),            # 毎日2便（02:00/16:00 JST）
    ("AI Money Cases Collector", "money-collect.yml", 26),  # 毎日（02:20 JST）
    ("Buzz Daily Health Check", "buzz-health-check.yml", 26),  # 毎日（04:15 JST）
    ("Buzz Ranking Collector", "buzz-collect.yml", 84),  # 月水金（週末ギャップ最大72h＋余裕）
]


def _is_failure(r: dict) -> bool:
    return r.get("status") == "completed" and r.get("conclusion") not in ("success", "skipped", None)


def _gh_run_list(extra_args: list[str], limit: int) -> tuple[str, list[dict] | None]:
    """gh run list の薄いラッパ。("ok", runs) か ("skip", None) を返す。"""
    try:
        out = subprocess.run(
            ["gh", "run", "list", "--repo", REPO, "--limit", str(limit),
             "--json", "name,conclusion,status,createdAt", *extra_args],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "skip", None
    if out.returncode != 0:
        return "skip", None
    try:
        return "ok", json.loads(out.stdout or "[]")
    except json.JSONDecodeError:
        return "skip", None


def evaluate_actions_freshness(latest_by_name: dict[str, dict], now: datetime) -> list[str]:
    """期待ワークフローが cadence 内に走っているか判定する純関数。

    不在（実行記録なし）と stale（最終runが許容ageを超過）を要確認として返す。
    failure は呼び出し側の横断スキャンが持つのでここでは扱わない。
    """
    problems = []
    for name, _file, max_age in EXPECTED_WORKFLOWS:
        r = latest_by_name.get(name)
        if r is None:
            problems.append(f"{name}=実行記録なし")
            continue
        created = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
        age_h = (now - created).total_seconds() / 3600
        if age_h > max_age:
            problems.append(f"{name}=stale {age_h:.0f}h(>{max_age}h)")
    return problems


def check_actions(limit: int = 30) -> tuple[bool, str]:
    """横断failure検知＋期待スケジュールの不在/stale検知（サイレント停止を捕まえる）。"""
    status, runs = _gh_run_list([], limit)
    if status == "skip":
        return _line("GitHub Actions", True, "スキップ（gh利用不可/未認証）")

    latest: dict[str, dict] = {}
    for r in runs or []:
        latest.setdefault(r.get("name", "?"), r)  # runsは新しい順
    # 期待workflowが窓に出ていなければ個別取得（月水金等はlimit窓から漏れる）
    for name, wf_file, _max in EXPECTED_WORKFLOWS:
        if name not in latest:
            st, one = _gh_run_list(["--workflow", wf_file], 1)
            if st == "ok" and one:
                latest[name] = one[0]

    failures = sorted({name for name, r in latest.items() if _is_failure(r)})
    stale = evaluate_actions_freshness(latest, datetime.now(timezone.utc))

    problems = []
    if failures:
        problems.append("failure → " + ", ".join(failures))
    if stale:
        problems.append("鮮度 → " + "; ".join(stale))
    if problems:
        return _line("GitHub Actions", False, " / ".join(problems))
    return _line(
        "GitHub Actions", True,
        f"直近{len(latest)}種success・期待{len(EXPECTED_WORKFLOWS)}種cadence内",
    )


def check_apify() -> tuple[bool, str]:
    records = load_logs(None)
    if not records:
        return _line("Apify", True, "ログなし")
    plan = load_plan()
    tracking = build_tracking(records, plan)
    rolling = tracking["rolling"]
    monthly = rolling.get("monthly_projection_usd", 0) or 0
    ceiling = float(plan.get("projected_after", {})
                    .get("range_monthly_usd", {}).get("max", 12.0))
    ok = monthly <= ceiling
    return _line(
        "Apify", ok,
        f"月換算 ${monthly:.2f}（窓 {rolling.get('start_date')}〜{rolling.get('end_date')}・"
        f"上限 ${ceiling:.0f}・{rolling.get('status')}）",
    )


def check_gemini(days: int = 4) -> tuple[bool, str]:
    daily: dict[str, float] = defaultdict(float)
    if GEMINI_USAGE_DIR.exists():
        for path in sorted(GEMINI_USAGE_DIR.glob("*.jsonl"))[-days:]:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                daily[r["ts"][:10]] += r.get("est_usd") or 0.0
    if not daily:
        return _line("Gemini", True, "記録なし")
    recent = sorted(daily.items())[-days:]
    monthly = (sum(v for _, v in recent) / len(recent)) * 30
    latest_day, latest_usd = recent[-1]
    # 経験則: 月$8前後が合格。月$15超で要確認（Flash化前のproスパイク水準）。
    ok = monthly <= 15.0
    return _line(
        "Gemini", ok,
        f"{latest_day} ${latest_usd:.3f}/日・直近{len(recent)}日平均で月換算 ${monthly:.1f}",
    )


def check_buzz() -> tuple[bool, str]:
    metrics = load_latest_metrics()
    if metrics is None:
        return _line("Buzz", True, "メトリクス未記録")
    now = datetime.now(JST)
    # full判定（収集途絶＋品質guardrail）で総合確認する。
    healthy, messages = evaluate_health(metrics, now, quality_alarm=True)
    checked_at = datetime.fromisoformat(metrics["checked_at"])
    age_h = (now - checked_at).total_seconds() / 3600
    detail = (
        f"最終 {checked_at.date()}（{age_h:.0f}h前）・"
        f"status={metrics.get('guardrail_status')}・"
        f"overlap={metrics.get('ranking_top20_overlap_pct')}%"
    )
    if not healthy:
        detail += " → " + "; ".join(m for m in messages if m.startswith("ERROR"))
    return _line("Buzz", healthy, detail)


def load_collect_entries() -> list[dict]:
    """data/logs/*.jsonl から品質カウントを持つ collect 行を時系列で集める。"""
    entries: list[dict] = []
    if not LOGS_DIR.exists():
        return entries
    for path in sorted(LOGS_DIR.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("workflow") == "collect" and "must_follow_count" in r:
                entries.append(r)
    entries.sort(key=lambda r: r.get("ts", ""))
    return entries


def _median(values: list[float]) -> float:
    """空リストは0。外れ値に強い中央値（依存を増やさず自前実装）。"""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def evaluate_collection_quality(entries: list[dict]) -> tuple[bool, str]:
    """収集の品質監視を判定する純関数。

    - 法務一色化: legal_rss_count / total が LEGAL_DOMINANCE_RATIO 以上で要確認。
    - must_follow連続ゼロ: 末尾から MUST_FOLLOW_ZERO_STREAK 連続で0なら要確認（単発は許容）。
    - must_follow急減: 朝便(full)の最新値が直近full便の中央値の MUST_FOLLOW_DROP_RATIO 未満なら
      要確認。夕便(light)は対象アカウントを絞るため0が正常 → full便のみで比較。
      full便の履歴が MUST_FOLLOW_DROP_MIN_PRIORS 件貯まるまでは判定しない（ロールアウト互換）。
    - 法務RSS取得失敗: 全フィードが生entries0（legal_feeds_ok=0）なら「窓に新着なし」ではなく
      取得失敗の疑い。feedparser は404/空でも例外を投げないため legal_rss=0 だけでは区別できない。
    記録が無い間（旧コードのログのみ）は合格扱い＝次回収集から有効になる。
    """
    if not entries:
        return _line("収集品質", True, "記録なし（次回収集から有効）")
    latest = entries[-1]
    total = latest.get("items_collected") or latest.get("total") or 0
    legal = latest.get("legal_rss_count", 0)
    must_follow = latest.get("must_follow_count", 0)
    ratio = (legal / total) if total else 0.0

    zero_streak = 0
    for r in reversed(entries):
        if (r.get("must_follow_count", 0) or 0) == 0:
            zero_streak += 1
        else:
            break

    problems = []
    if ratio >= LEGAL_DOMINANCE_RATIO:
        problems.append(f"法務一色化 legal={legal}/{total}={ratio:.0%}")
    if zero_streak >= MUST_FOLLOW_ZERO_STREAK:
        problems.append(f"must_follow連続ゼロ{zero_streak}回")

    # 法務RSS取得失敗の検知: legal_rss=0 が「窓に新着なし」か「フィード取得失敗」か区別する。
    # 全フィードが生entries0（feeds_ok=0）なら取得失敗の疑い。新着なしなら古い生entriesが残る。
    feeds_total = latest.get("legal_feeds_total")
    feeds_ok = latest.get("legal_feeds_ok", 0)
    feeds_failed = latest.get("legal_feeds_failed", 0)
    feed_health = ""
    if feeds_total:  # 記録があるとき（旧ログはNone→沈黙＝ロールアウト互換）
        feed_health = f"・feeds {feeds_ok}/{feeds_total}健全"
        if feeds_failed:
            feed_health += f"（失敗{feeds_failed}）"
        if feeds_ok == 0:
            problems.append(f"法務RSS全{feeds_total}フィード生0件＝取得失敗の疑い")

    # must_follow 急減（full便のみで比較）
    full_entries = [r for r in entries if r.get("x_mode") == "full"]
    if len(full_entries) > MUST_FOLLOW_DROP_MIN_PRIORS:
        cur_full = full_entries[-1].get("must_follow_count", 0) or 0
        priors = [
            r.get("must_follow_count", 0) or 0
            for r in full_entries[-(MUST_FOLLOW_DROP_MIN_PRIORS + 1):-1]
        ]
        baseline = _median(priors)
        if baseline > 0 and cur_full < MUST_FOLLOW_DROP_RATIO * baseline:
            problems.append(
                f"must_follow急減 full={cur_full}（直近full中央値{baseline:.0f}比）"
            )

    detail = f"legal_rss={legal}/{total}（{ratio:.0%}）{feed_health}・must_follow={must_follow}"
    if problems:
        detail += " → " + "; ".join(problems)
    return _line("収集品質", not problems, detail)


def check_collection_quality() -> tuple[bool, str]:
    return evaluate_collection_quality(load_collect_entries())


def load_latest_analysis() -> dict:
    """data/analysis/ の最新便（日付→便順）のJSONを読む。読めなければ空。"""
    if not ANALYSIS_DIR.exists():
        return {}

    def key(p: Path) -> tuple:
        parts = p.stem.split("_")
        return (parts[0], _SLOT_ORDER.get(parts[1] if len(parts) > 1 else "", 9))

    files = sorted(ANALYSIS_DIR.glob("*.json"), key=key)
    if not files:
        return {}
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def evaluate_analysis_structure(analysis: dict) -> tuple[bool, str]:
    """分析JSONの構造完全性を判定する純関数（top/cat/action/fallback）。

    件数の多寡は見ない（低ニュース日は top/cat が少なくて正常）。ボリューム非依存の
    構造的失敗だけを要確認にする:
    - fallback_used_stages 非空 → primaryモデルが429/5xxでfallback＝分析品質低下の疑い
    - top_articles=0 かつ item>0 → 入力はあるのに掲載記事を出せず（図解も生成されない）
    - top>0 なのに category_summaries=0 → 構造の不整合
    - item>0 なのに action_items=0 → 出力崩れ（プロンプトは3〜5件を要求）
    記録が無い/item=0（収集なし）は合格扱い。
    """
    if not analysis:
        return _line("分析構造", True, "記録なし")
    top = len(analysis.get("top_articles") or [])
    cat = len(analysis.get("category_summaries") or [])
    action = len(analysis.get("action_items") or [])
    fallback = analysis.get("fallback_used_stages") or []
    item_count = analysis.get("item_count") or 0
    slot = analysis.get("slot", "?")

    problems = []
    if fallback:
        problems.append(f"fallback={'/'.join(fallback)}（モデル劣化の疑い）")
    if item_count > 0 and top == 0:
        problems.append("top_articles=0（掲載記事を出せず・図解も未生成）")
    if top > 0 and cat == 0:
        problems.append("category_summaries=0（構造不整合）")
    if item_count > 0 and action == 0:
        problems.append("action_items=0（出力崩れ）")

    detail = f"{slot} top={top}/cat={cat}/action={action}/fallback={len(fallback)}（item={item_count}）"
    if problems:
        detail += " → " + "; ".join(problems)
    return _line("分析構造", not problems, detail)


def check_analysis_structure() -> tuple[bool, str]:
    return evaluate_analysis_structure(load_latest_analysis())


def load_backlog() -> list[dict]:
    """ops_backlog.yaml の未了TODOを読む。読めなければ空（=表示しないだけ）。"""
    if not BACKLOG_PATH.exists():
        return []
    try:
        import yaml
        data = yaml.safe_load(BACKLOG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    items = data.get("items") or []
    return [i for i in items if isinstance(i, dict) and i.get("title")]


def format_backlog(items: list[dict], today: date) -> list[str]:
    """未了TODOを古い順（=塩漬けが上）に整形する純関数。合否には影響しない。

    各行に since からの経過日数を出し、TODO_STALE_DAYS 以上は ⚠️ で軽く催促する。
    空なら空リストを返す（フッタごと出さない）。
    """
    if not items:
        return []

    def age(i: dict) -> int:
        try:
            return (today - date.fromisoformat(str(i.get("since")))).days
        except (ValueError, TypeError):
            return -1

    ordered = sorted(items, key=lambda i: -age(i))
    lines = [f"📋 未了TODO {len(ordered)}件（塩漬け防止・合否には影響しない）"]
    for i in ordered:
        d = age(i)
        tag = f"{d}d" if d >= 0 else "?"
        mark = "⚠️ " if d >= TODO_STALE_DAYS else ""
        note = i.get("note")
        suffix = f"  — {note}" if note else ""
        lines.append(f"  • {mark}[{tag}] {i['title']}{suffix}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="日次運用チェック集約")
    parser.add_argument("--days", type=int, default=4, help="Gemini平均/表示の日数（既定4）")
    args = parser.parse_args(argv)

    print("=" * 64)
    print(f"日次チェック  {datetime.now(JST):%Y-%m-%d %H:%M JST}")
    print("-" * 64)

    results = [
        check_actions(),
        check_apify(),
        check_gemini(args.days),
        check_buzz(),
        check_collection_quality(),
        check_analysis_structure(),
    ]
    all_ok = True
    for ok, msg in results:
        all_ok = all_ok and ok
        print(msg)

    print("-" * 64)
    print(("✅ 全項目合格" if all_ok else "⚠️ 要確認あり（上の⚠️行を参照）"))

    backlog_lines = format_backlog(load_backlog(), datetime.now(JST).date())
    if backlog_lines:
        print("-" * 64)
        for ln in backlog_lines:
            print(ln)

    print("=" * 64)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

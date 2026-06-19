#!/usr/bin/env python3
"""日次運用チェックを1コマンドに集約する。

「今日のチェック」で見る4点を合否サマリで出す:
  1. GitHub Actions の直近成否（gh CLI、未認証ならスキップ）
  2. Apify コスト（施策後フロア窓の月額換算。check_cost.py と同じ計測ロジック）
  3. Gemini コスト（直近数日の日額）
  4. Buzz メトリクス最終行の鮮度と guardrail
  5. 収集品質2点（法務一色化・must_follow連続ゼロ。data/logs の collect 行から）

使い方:
  python3 daily_check.py            # サマリ表示
  python3 daily_check.py --days 5   # Gemini/表示日数を変更
終了コード: すべて合格なら 0、要確認があれば 1。
"""

import argparse
import json
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from check_cost import build_tracking, load_logs, load_plan
from scripts.check_buzz_health import evaluate_health, load_latest_metrics

BASE = Path(__file__).resolve().parent
GEMINI_USAGE_DIR = BASE / "data" / "gemini_usage"
LOGS_DIR = BASE / "data" / "logs"
JST = timezone(timedelta(hours=9))
REPO = "k-hira-shine/ai-news-collector"

# 品質監視2点の閾値（[[daily-check-routine]] の「残監視2点」をコード化）
LEGAL_DOMINANCE_RATIO = 0.5   # legal_rss_count/total がこれ以上なら「規制/政策」一色化を疑う
MUST_FOLLOW_ZERO_STREAK = 2   # must_follow_count=0 がこの連続回数で要調査（単発は許容）

OK = "✅"
WARN = "⚠️"


def _line(label: str, ok: bool, detail: str) -> tuple[bool, str]:
    return ok, f"{OK if ok else WARN} {label}: {detail}"


def check_actions(limit: int = 15) -> tuple[bool, str]:
    """ワークフロー別の直近runを1件ずつ拾い、failureがあれば要確認。"""
    try:
        out = subprocess.run(
            ["gh", "run", "list", "--repo", REPO, "--limit", str(limit),
             "--json", "name,conclusion,status,createdAt"],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return _line("GitHub Actions", True, f"スキップ（gh利用不可: {exc.__class__.__name__}）")
    if out.returncode != 0:
        return _line("GitHub Actions", True, "スキップ（gh未認証/エラー）")
    try:
        runs = json.loads(out.stdout or "[]")
    except json.JSONDecodeError:
        return _line("GitHub Actions", True, "スキップ（gh出力を解析できず）")

    latest: dict[str, dict] = {}
    for r in runs:
        latest.setdefault(r.get("name", "?"), r)  # runsは新しい順
    failures = [name for name, r in latest.items()
                if r.get("status") == "completed" and r.get("conclusion") not in ("success", "skipped", None)]
    if failures:
        return _line("GitHub Actions", False, "failure → " + ", ".join(failures))
    return _line("GitHub Actions", True, f"直近{len(latest)}種すべてsuccess")


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


def evaluate_collection_quality(entries: list[dict]) -> tuple[bool, str]:
    """収集の品質監視2点を判定する純関数。

    - 法務一色化: legal_rss_count / total が LEGAL_DOMINANCE_RATIO 以上で要確認。
    - must_follow連続ゼロ: 末尾から MUST_FOLLOW_ZERO_STREAK 連続で0なら要確認（単発は許容）。
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

    detail = f"legal_rss={legal}/{total}（{ratio:.0%}）・must_follow={must_follow}"
    if problems:
        detail += " → " + "; ".join(problems)
    return _line("収集品質", not problems, detail)


def check_collection_quality() -> tuple[bool, str]:
    return evaluate_collection_quality(load_collect_entries())


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
    ]
    all_ok = True
    for ok, msg in results:
        all_ok = all_ok and ok
        print(msg)

    print("-" * 64)
    print(("✅ 全項目合格" if all_ok else "⚠️ 要確認あり（上の⚠️行を参照）"))
    print("=" * 64)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

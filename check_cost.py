#!/usr/bin/env python3
"""Apifyコスト確認・日次追跡スクリプト

使い方:
  python3 check_cost.py          # 直近7日分を表示
  python3 check_cost.py --days 14  # 直近14日分を表示
  python3 check_cost.py --all      # 全期間を表示
  python3 check_cost.py --record   # data/cost_tracking.json を更新
"""

import argparse
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "data", "logs")
GEMINI_USAGE_DIR = os.path.join(BASE_DIR, "data", "gemini_usage")
CHANGES_PATH = os.path.join(BASE_DIR, "data", "cost_changes.jsonl")
PLAN_PATH = os.path.join(BASE_DIR, "data", "cost_reduction_plan.json")
TRACKING_PATH = os.path.join(BASE_DIR, "data", "cost_tracking.json")

WORKFLOW_LABELS = {
    "collect": "AI News  ",
    "money":   "Money/SNS",
    "buzz":    "Buzz     ",
}


def load_logs(days: int | None = 7) -> list[dict]:
    if not os.path.isdir(LOGS_DIR):
        return []
    files = sorted(f for f in os.listdir(LOGS_DIR) if f.endswith(".jsonl"))
    if days is not None:
        files = files[-days:]
    records = []
    for fname in files:
        with open(os.path.join(LOGS_DIR, fname), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return records


def load_gemini_daily() -> dict[str, float]:
    """data/gemini_usage/*.jsonl から日付→推定USDを集計する。

    Apifyコスト(data/logs)とは別ファイルに記録される Gemini API 費用を、
    check_cost.py の合算表示に取り込むための読み込み口。
    """
    daily: dict[str, float] = defaultdict(float)
    if not os.path.isdir(GEMINI_USAGE_DIR):
        return daily
    for fname in sorted(f for f in os.listdir(GEMINI_USAGE_DIR) if f.endswith(".jsonl")):
        with open(os.path.join(GEMINI_USAGE_DIR, fname), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = r.get("ts", "")
                if ts:
                    daily[ts[:10]] += r.get("est_usd") or 0.0
    return daily


def load_changes() -> dict[str, list[dict]]:
    """cost_changes.jsonl を日付→変更リストの辞書で返す"""
    changes: dict[str, list[dict]] = defaultdict(list)
    if not os.path.exists(CHANGES_PATH):
        return changes
    with open(CHANGES_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                    changes[r["date"]].append(r)
                except (json.JSONDecodeError, KeyError):
                    continue
    return changes


def summarize(records: list[dict]) -> dict[str, dict]:
    """日付×ワークフローごとにコストを集計"""
    by_date: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    for r in records:
        date = r.get("date", "")
        workflow = r.get("workflow", "other")
        cost = r.get("apify_cost_usd", 0) or 0
        by_date[date][workflow] += cost
    return by_date


def load_plan() -> dict:
    try:
        with open(PLAN_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _date_range(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start)
    last = date.fromisoformat(end)
    dates = []
    while current <= last:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def _workflow_costs(by_date: dict, target_date: str) -> dict[str, float]:
    costs = by_date.get(target_date, {})
    return {
        workflow: round(float(costs.get(workflow, 0)), 4)
        for workflow in ("collect", "money", "buzz")
    }


def _daily_items(records: list[dict]) -> dict[str, dict[str, int]]:
    items: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for record in records:
        target_date = record.get("date", "")
        workflow = record.get("workflow", "other")
        items[target_date][workflow] += int(record.get("items_collected", 0) or 0)
    return items


def build_tracking(records: list[dict], plan: dict, gemini_daily: dict[str, float] | None = None) -> dict:
    """固定基準と日次ログから、実装後の比較に使う追跡データを作る。

    total_usd / rolling.monthly_projection_usd は Apify 専用のまま維持し
    （daily_check.check_apify が plan 上限と比較するため）、Gemini 費用は
    gemini_usd / combined_* として別枠で追加する。
    """
    by_date = summarize(records)
    items_by_date = _daily_items(records)
    if gemini_daily is None:
        gemini_daily = load_gemini_daily()
    dates = sorted(d for d in by_date if d)
    daily = []
    for target_date in dates:
        workflows = _workflow_costs(by_date, target_date)
        apify_total = round(sum(workflows.values()), 4)
        gemini_usd = round(float(gemini_daily.get(target_date, 0)), 4)
        daily.append({
            "date": target_date,
            "workflows": workflows,
            "items_collected": {
                workflow: items_by_date[target_date].get(workflow, 0)
                for workflow in ("collect", "money", "buzz")
            },
            "total_usd": apify_total,
            "gemini_usd": gemini_usd,
            "combined_total_usd": round(apify_total + gemini_usd, 4),
        })

    measurement = plan.get("measurement", {})
    rolling_days = int(measurement.get("rolling_average_days", 7))
    today_jst = datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()
    implementation_date = plan.get("implementation_date")
    # 計測窓のフロア。施策前の汚染日を混ぜないため measurement.start_date を優先し、
    # 無ければ implementation_date にフォールバックする（[[cost-check-window-pitfall]]）。
    floor_date = measurement.get("start_date") or implementation_date
    completed_daily = [
        day for day in daily
        if day["date"] < today_jst
        and (not floor_date or day["date"] >= floor_date)
    ]
    recent = completed_daily[-rolling_days:]
    rolling_avg = (
        sum(day["total_usd"] for day in recent) / len(recent)
        if recent else 0
    )
    gemini_avg = (
        sum(day["gemini_usd"] for day in recent) / len(recent)
        if recent else 0
    )
    combined_avg = rolling_avg + gemini_avg
    projected = plan.get("projected_after", {})
    target_daily = float(projected.get("daily_usd", 0))
    baseline_daily = float(plan.get("baseline", {}).get("daily_usd", 0))
    reduction_pct = (
        (baseline_daily - rolling_avg) / baseline_daily * 100
        if baseline_daily else 0
    )
    if not recent:
        status = "no_data"
    elif rolling_avg <= float(projected.get("range_daily_usd", {}).get("max", target_daily)):
        status = "on_target"
    else:
        status = "above_target"

    return {
        "plan_version": plan.get("version", 1),
        "implementation_status": plan.get("implementation_status", "planned"),
        "implementation_date": implementation_date,
        "baseline": plan.get("baseline", {}),
        "projected_after": projected,
        "latest": daily[-1] if daily else None,
        "rolling": {
            "days": len(recent),
            "window": rolling_days,
            "start_date": recent[0]["date"] if recent else None,
            "end_date": recent[-1]["date"] if recent else None,
            "average_daily_usd": round(rolling_avg, 4),
            "monthly_projection_usd": round(rolling_avg * 30, 2),
            "gemini_average_daily_usd": round(gemini_avg, 4),
            "gemini_monthly_projection_usd": round(gemini_avg * 30, 2),
            "combined_average_daily_usd": round(combined_avg, 4),
            "combined_monthly_projection_usd": round(combined_avg * 30, 2),
            "reduction_vs_baseline_pct": round(reduction_pct, 1),
            "status": status,
        },
        "daily": daily[-30:],
    }


def write_tracking(records: list[dict], plan: dict) -> dict:
    tracking = build_tracking(records, plan)
    os.makedirs(os.path.dirname(TRACKING_PATH), exist_ok=True)
    tmp_path = TRACKING_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(tracking, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, TRACKING_PATH)
    return tracking


def main() -> None:
    parser = argparse.ArgumentParser(description="Apifyコスト確認")
    parser.add_argument("--days", type=int, default=7, help="表示する日数（デフォルト7）")
    parser.add_argument("--all", action="store_true", help="全期間を表示")
    parser.add_argument("--record", action="store_true", help="日次追跡JSONを更新")
    parser.add_argument("--quiet", action="store_true", help="追跡更新時の標準出力を抑制")
    args = parser.parse_args()

    days = None if args.all or args.record else args.days
    records = load_logs(days)

    if not records:
        print("ログが見つかりません。")
        return

    plan = load_plan()

    # 表示窓のフロア。--all 以外では施策前（measurement.start_date より前）を除外し、
    # 相対7日窓が境界をまたいで月額換算を誤膨張させるのを防ぐ（[[cost-check-window-pitfall]]）。
    floor_date = plan.get("measurement", {}).get("start_date")
    floored_window = bool(floor_date) and not args.all
    if floored_window:
        records = [r for r in records if r.get("date", "") >= floor_date]
        if not records:
            print(f"ログが見つかりません（計測窓フロア {floor_date}〜 適用後）。")
            return

    if args.record:
        tracking = write_tracking(records, plan)
        if not args.quiet:
            rolling = tracking["rolling"]
            print(
                f"Cost tracking updated: ${rolling['average_daily_usd']:.4f}/day, "
                f"${rolling['monthly_projection_usd']:.2f}/month "
                f"({rolling['status']})"
            )
        if args.quiet:
            return

    by_date = summarize(records)
    changes = load_changes()
    dates = sorted(by_date.keys())

    # 変更があった日付も含める（コストログがなくても表示）
    all_dates = sorted(set(dates) | set(changes.keys()))

    print()
    print("=" * 60)
    if floored_window:
        print(f"計測窓フロア: {floor_date}〜（施策前を自動除外。全期間は --all）")
    print(f"{'日付':<12} {'AI News':>8} {'Money/SNS':>10} {'Buzz':>7} {'合計':>8}")
    print("-" * 60)

    grand_total = 0.0
    cost_segments: list[tuple[str, float]] = []  # (label, avg_cost) for before/after comparison
    current_segment_start = all_dates[0] if all_dates else ""
    current_segment_costs: list[float] = []

    for date in all_dates:
        d = by_date.get(date, {})
        collect = d.get("collect", 0)
        money = d.get("money", 0)
        buzz = d.get("buzz", 0)
        total = collect + money + buzz
        grand_total += total
        if total > 0:
            current_segment_costs.append(total)

        print(f"{date:<12} ${collect:>6.4f}  ${money:>8.4f}  ${buzz:>5.4f}  ${total:>6.4f}")

        # その日に変更があれば表示
        if date in changes:
            for ch in changes[date]:
                tag = f"[{ch.get('type','変更')}]"
                summary = ch.get("summary", "")
                detail = ch.get("detail", "")
                print(f"  ↳ {tag} {summary}")
                # detailを60文字折り返しで表示
                words = detail
                while len(words) > 58:
                    print(f"      {words[:58]}")
                    words = words[58:]
                if words:
                    print(f"      {words}")
            # セグメント区切り
            if current_segment_costs:
                seg_avg = sum(current_segment_costs) / len(current_segment_costs)
                cost_segments.append((f"〜{date}", seg_avg))
                current_segment_costs = []
            print()

    if current_segment_costs:
        seg_avg = sum(current_segment_costs) / len(current_segment_costs)
        cost_segments.append((f"{current_segment_start}〜", seg_avg))

    print("-" * 60)
    avg = grand_total / len([d for d in all_dates if by_date.get(d)]) if all_dates else 0
    print(f"{'Apify合計':<12} {'':>8}  {'':>10}  {'':>7}  ${grand_total:>6.4f}")
    print(f"{'Apify平均/日':<12} {'':>8}  {'':>10}  {'':>7}  ${avg:>6.4f}")
    print(f"{'Apify月額':<12} {'':>8}  {'':>10}  {'':>7}  ${avg*30:>6.2f}")
    print("=" * 60)

    # Gemini API 費用（別ファイル data/gemini_usage/*.jsonl）を同じ窓で合算表示する。
    gemini_daily = load_gemini_daily()
    if floored_window:
        gemini_daily = {d: v for d, v in gemini_daily.items() if d >= floor_date}
    gemini_window = {d: gemini_daily.get(d, 0.0) for d in all_dates}
    gemini_total = sum(gemini_window.values())
    gemini_days = len([d for d in all_dates if gemini_window.get(d)])
    gemini_avg = gemini_total / gemini_days if gemini_days else 0
    combined_month = (avg + gemini_avg) * 30
    print()
    print("── Gemini API ──────────────────────────────────────────────")
    print(f"  合計 ${gemini_total:.4f}  平均 ${gemini_avg:.4f}/日  月額換算 ${gemini_avg*30:.2f}")
    print("── Apify + Gemini 合算 ─────────────────────────────────────")
    print(f"  月額換算 ${combined_month:.2f}")
    print("=" * 60)

    # 変更前後の比較
    if len(cost_segments) >= 2:
        print()
        print("── 変更効果 ──────────────────────────────────────────────")
        for i, (label, seg_avg) in enumerate(cost_segments):
            print(f"  {label:<16} 平均 ${seg_avg:.4f}/日  (月額換算 ${seg_avg*30:.2f})")
        before = cost_segments[0][1]
        after = cost_segments[-1][1]
        diff = before - after
        pct = (diff / before * 100) if before > 0 else 0
        arrow = "↓" if diff > 0 else "↑"
        print(f"  {'削減効果':<14} {arrow} ${diff:.4f}/日  ({pct:.0f}%{'削減' if diff > 0 else '増加'})")
        print("─" * 60)
    print()


if __name__ == "__main__":
    main()

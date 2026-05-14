#!/usr/bin/env python3
"""Apifyコスト確認スクリプト

使い方:
  python3 check_cost.py          # 直近7日分を表示
  python3 check_cost.py --days 14  # 直近14日分を表示
  python3 check_cost.py --all      # 全期間を表示
"""

import argparse
import json
import os
from collections import defaultdict

LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "logs")
CHANGES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cost_changes.jsonl")

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Apifyコスト確認")
    parser.add_argument("--days", type=int, default=7, help="表示する日数（デフォルト7）")
    parser.add_argument("--all", action="store_true", help="全期間を表示")
    args = parser.parse_args()

    days = None if args.all else args.days
    records = load_logs(days)

    if not records:
        print("ログが見つかりません。")
        return

    by_date = summarize(records)
    changes = load_changes()
    dates = sorted(by_date.keys())

    # 変更があった日付も含める（コストログがなくても表示）
    all_dates = sorted(set(dates) | set(changes.keys()))

    print()
    print("=" * 60)
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
    print(f"{'合計':<12} {'':>8}  {'':>10}  {'':>7}  ${grand_total:>6.4f}")
    print(f"{'平均/日':<12} {'':>8}  {'':>10}  {'':>7}  ${avg:>6.4f}")
    print(f"{'月額換算':<12} {'':>8}  {'':>10}  {'':>7}  ${avg*30:>6.2f}")
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

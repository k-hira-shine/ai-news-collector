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
    dates = sorted(by_date.keys())

    print()
    print("=" * 54)
    print(f"{'日付':<12} {'AI News':>8} {'Money/SNS':>10} {'Buzz':>7} {'合計':>8}")
    print("-" * 54)

    grand_total = 0.0
    for date in dates:
        d = by_date[date]
        collect = d.get("collect", 0)
        money = d.get("money", 0)
        buzz = d.get("buzz", 0)
        total = collect + money + buzz
        grand_total += total
        print(f"{date:<12} ${collect:>6.4f}  ${money:>8.4f}  ${buzz:>5.4f}  ${total:>6.4f}")

    print("-" * 54)
    avg = grand_total / len(dates) if dates else 0
    print(f"{'合計':<12} {'':>8}  {'':>10}  {'':>7}  ${grand_total:>6.4f}")
    print(f"{'平均/日':<12} {'':>8}  {'':>10}  {'':>7}  ${avg:>6.4f}")
    print(f"{'月額換算':<12} {'':>8}  {'':>10}  {'':>7}  ${avg*30:>6.2f}")
    print("=" * 54)
    print()


if __name__ == "__main__":
    main()

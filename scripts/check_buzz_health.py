#!/usr/bin/env python3
"""Validate the latest Buzz collection quality without calling paid APIs."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
METRICS_PATH = BASE / "data" / "buzz_collection_metrics.jsonl"
JST = timezone(timedelta(hours=9))


def load_latest_metrics(path: Path = METRICS_PATH) -> dict | None:
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]
    return json.loads(lines[-1]) if lines else None


def evaluate_health(
    metrics: dict | None,
    now: datetime | None = None,
    *,
    quality_alarm: bool = True,
) -> tuple[bool, list[str]]:
    """Buzzメトリクス最終行から健全性を判定する。

    quality_alarm=True（既定／buzz-collect の収集直後ステップ）:
        新鮮な収集行の品質guardrail(warning)も収集途絶(>4日)も hard-fail にする。
    quality_alarm=False（--staleness-only／日次cron）:
        収集途絶(>4日)のみ hard-fail。品質guardrailは収集ランが既に判定済みなので、
        同じ stale 行を毎日再アラートしない（重複失敗メールの抑制）。NOTICE で残す。
    """
    if metrics is None:
        return True, ["品質メトリクスは次回Buzz収集から記録されます"]

    now = now or datetime.now(JST)
    checked_at = datetime.fromisoformat(metrics["checked_at"])
    messages = [
        f"profile={metrics.get('profile')}",
        f"fetched={metrics.get('fetched_items', 0)}",
        f"new={metrics.get('new_items', 0)}",
        f"retained={metrics.get('retained_items', 0)}",
        f"top20_retention={metrics.get('prior_top20_retention_pct', 0)}%",
        f"ranking_overlap={metrics.get('ranking_top20_overlap_pct', 0)}%",
        f"cost=${metrics.get('apify_cost_usd', 0):.4f}",
    ]
    starved_accounts = metrics.get("starved_accounts") or []
    if starved_accounts:
        messages.append(
            "starved_accounts="
            + ",".join(f"@{account}" for account in starved_accounts)
        )
    healthy = True
    if now - checked_at > timedelta(days=4):
        healthy = False
        messages.append("ERROR: 最終Buzz収集から4日以上経過")
    if metrics.get("guardrail_status") == "warning":
        if quality_alarm:
            healthy = False
            if starved_accounts:
                messages.append("ERROR: Buzz取得0件が連続したアカウントがあります")
            else:
                messages.append("ERROR: ランキング保持率が基準未満")
        else:
            messages.append(
                "NOTICE: 直近収集のguardrail=warning（品質判定はbuzz-collectの収集直後に実施済み・"
                "日次では再アラートしない）"
            )
    if metrics.get("fallback_triggered"):
        messages.append("NOTICE: 欠落リスクを検知しフル収集へ自動復帰済み")
    return healthy, messages


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Buzz収集の健全性チェック")
    parser.add_argument(
        "--staleness-only",
        action="store_true",
        help="品質guardrail(warning)では失敗させず、収集途絶(>4日)のみ失敗とする（日次cron用）",
    )
    args = parser.parse_args(argv)

    healthy, messages = evaluate_health(
        load_latest_metrics(), quality_alarm=not args.staleness_only
    )
    mode = "staleness-only" if args.staleness_only else "full"
    print(f"Buzz daily health check ({mode})")
    for message in messages:
        print(f"- {message}")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())

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
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return json.loads(lines[-1]) if lines else None


def evaluate_health(metrics: dict | None, now: datetime | None = None) -> tuple[bool, list[str]]:
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
    healthy = True
    if now - checked_at > timedelta(days=4):
        healthy = False
        messages.append("ERROR: 最終Buzz収集から4日以上経過")
    if metrics.get("guardrail_status") == "warning":
        healthy = False
        messages.append("ERROR: ランキング保持率が基準未満")
    if metrics.get("fallback_triggered"):
        messages.append("NOTICE: 欠落リスクを検知しフル収集へ自動復帰済み")
    return healthy, messages


def main() -> int:
    healthy, messages = evaluate_health(load_latest_metrics())
    print("Buzz daily health check")
    for message in messages:
        print(f"- {message}")
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())

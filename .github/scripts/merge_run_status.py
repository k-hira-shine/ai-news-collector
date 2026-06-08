#!/usr/bin/env python3
"""Merge conflicted docs/run_status.json without losing newer workflow states."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo


def _parse_ts(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo("UTC"))
    except (TypeError, ValueError):
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M JST").replace(
                tzinfo=ZoneInfo("Asia/Tokyo")
            )
        except (TypeError, ValueError):
            return datetime.min.replace(tzinfo=ZoneInfo("UTC"))


def merge_statuses(left: dict, right: dict) -> tuple[dict, dict]:
    workflows: dict = {}
    selected: dict[str, str] = {}
    names = set(left.get("workflows") or {}) | set(right.get("workflows") or {})
    for name in sorted(names):
        left_state = (left.get("workflows") or {}).get(name)
        right_state = (right.get("workflows") or {}).get(name)
        candidates = [
            ("left", state)
            for state in (left_state,)
            if isinstance(state, dict)
        ] + [
            ("right", state)
            for state in (right_state,)
            if isinstance(state, dict)
        ]
        source, state = max(candidates, key=lambda item: _parse_ts(item[1].get("ts", "")))
        workflows[name] = state
        selected[name] = source

    statuses = [state.get("status") for state in workflows.values()]
    overall = "error" if "error" in statuses else "warning" if "warning" in statuses else "success"
    newest = max((left, right), key=lambda status: _parse_ts(status.get("updated_at", "")))
    newest_workflow_ts = max(
        (_parse_ts(state.get("ts", "")) for state in workflows.values()),
        default=_parse_ts(newest.get("updated_at", "")),
    )
    output = {
        "overall": overall,
        "updated_at": newest_workflow_ts.astimezone(
            ZoneInfo("Asia/Tokyo")
        ).strftime("%Y-%m-%d %H:%M JST"),
        "workflows": workflows,
    }
    if newest.get("incident"):
        output["incident"] = newest["incident"]
    return output, selected


def _stage_json(stage: int, path: str) -> dict:
    raw = subprocess.check_output(
        ["git", "show", f":{stage}:{path}"],
        text=True,
    )
    return json.loads(raw)


def _write_diagnostic(selected: dict[str, str], merged: dict) -> None:
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    log_dir = os.path.join("data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    record = {
        "ts": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M JST"),
        "workflow": "status_merge",
        "status": "success",
        "error": "",
        "selected_sources": selected,
        "workflow_timestamps": {
            name: state.get("ts", "")
            for name, state in merged.get("workflows", {}).items()
        },
    }
    path = os.path.join(log_dir, f"{now.strftime('%Y-%m-%d')}.jsonl")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "docs/run_status.json"
    left = _stage_json(2, path)
    right = _stage_json(3, path)
    merged, selected = merge_statuses(left, right)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    _write_diagnostic(selected, merged)
    print(
        "Merged run_status workflows: "
        + ", ".join(
            f"{name}={state.get('ts', '')}"
            for name, state in merged.get("workflows", {}).items()
        )
    )


if __name__ == "__main__":
    main()

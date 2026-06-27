#!/usr/bin/env python3
"""Pause/resume operational GitHub Actions without deleting secrets.

Examples:
  python scripts/ops_workflows.py status
  python scripts/ops_workflows.py pause
  python scripts/ops_workflows.py pause --cancel-running
  python scripts/ops_workflows.py resume
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


REPO = "k-hira-shine/ai-news-collector"

# Daily/recurring operational workflows. Verification and one-off rebuild jobs
# stay outside the default target so they are not disabled accidentally.
OPS_WORKFLOWS = [
    "collect.yml",
    "money-collect.yml",
    "buzz-collect.yml",
    "buzz-health-check.yml",
    "daily-ops-check.yml",
]


def _local_workflows() -> list[str]:
    workflows_dir = Path(".github/workflows")
    return sorted(path.name for path in workflows_dir.glob("*.yml"))


def _targets(all_workflows: bool) -> list[str]:
    return _local_workflows() if all_workflows else OPS_WORKFLOWS


def _run(args: list[str], *, dry_run: bool = False) -> subprocess.CompletedProcess[str]:
    cmd = ["gh", *args, "--repo", REPO]
    print("+ " + " ".join(cmd))
    if dry_run:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return subprocess.run(cmd, check=True, text=True, capture_output=True)


def _require_gh() -> None:
    if shutil.which("gh") is None:
        raise SystemExit("gh CLI is required.")


def _print_workflow_list() -> None:
    result = _run(["workflow", "list", "--all", "--limit", "100"])
    if result.stdout:
        print(result.stdout.rstrip())


def _in_progress_runs(workflows: list[str]) -> list[dict]:
    runs_by_id: dict[int, dict] = {}
    for workflow in workflows:
        result = _run([
            "run",
            "list",
            "--workflow",
            workflow,
            "--status",
            "in_progress",
            "--limit",
            "20",
            "--json",
            "databaseId,name,workflowName,status,createdAt",
        ])
        for run in json.loads(result.stdout or "[]"):
            runs_by_id[int(run["databaseId"])] = run
    return list(runs_by_id.values())


def _cancel_running(workflows: list[str], *, dry_run: bool) -> None:
    runs = _in_progress_runs(workflows)
    if not runs:
        print("No in-progress runs for selected workflows.")
        return
    for run in runs:
        run_id = str(run["databaseId"])
        name = run.get("workflowName") or run.get("name") or "unknown"
        print(f"Canceling run {run_id} ({name})")
        _run(["run", "cancel", run_id], dry_run=dry_run)


def pause(workflows: list[str], *, cancel_running: bool, dry_run: bool) -> None:
    if cancel_running:
        _cancel_running(workflows, dry_run=dry_run)
    for workflow in workflows:
        _run(["workflow", "disable", workflow], dry_run=dry_run)


def resume(workflows: list[str], *, dry_run: bool) -> None:
    for workflow in workflows:
        _run(["workflow", "enable", workflow], dry_run=dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "pause", "resume", "cancel-running"])
    parser.add_argument(
        "--all",
        action="store_true",
        help="Target every local .github/workflows/*.yml file, not only daily ops workflows.",
    )
    parser.add_argument(
        "--cancel-running",
        action="store_true",
        help="With pause, cancel currently in-progress runs for selected workflows.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without changing GitHub.")
    args = parser.parse_args()

    _require_gh()
    workflows = _targets(args.all)

    if args.command == "status":
        _print_workflow_list()
        return 0
    if args.command == "pause":
        pause(workflows, cancel_running=args.cancel_running, dry_run=args.dry_run)
        return 0
    if args.command == "resume":
        resume(workflows, dry_run=args.dry_run)
        return 0
    if args.command == "cancel-running":
        _cancel_running(workflows, dry_run=args.dry_run)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())

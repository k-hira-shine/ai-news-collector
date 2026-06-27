#!/usr/bin/env python3
"""Send daily_check.py output to Discord when the scheduled ops check fails."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return ""


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    output_path = Path(argv[0]) if argv else Path("daily_check.out")
    status = int(os.environ.get("DAILY_CHECK_STATUS", "1"))
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    if not webhook:
        print("DISCORD_WEBHOOK_URL not set; skipping Discord alert.")
        return 0
    if status == 0 and not _truthy(os.environ.get("DAILY_CHECK_NOTIFY_SUCCESS")):
        print("Daily check passed; skipping Discord alert.")
        return 0

    output = output_path.read_text(encoding="utf-8") if output_path.exists() else "(no output)"
    output = output.strip()
    if len(output) > 1600:
        output = "...(truncated)\n" + output[-1600:]

    title = "Daily ops check failed" if status else "Daily ops check passed"
    run_url = _run_url()
    suffix = f"\n\nActions: {run_url}" if run_url else ""
    content = f"**{title}**\n```text\n{output}\n```{suffix}"
    if len(content) > 2000:
        content = content[:1990] + "\n..."

    response = requests.post(webhook, json={"content": content}, timeout=30)
    if response.status_code >= 300:
        print(f"Discord alert failed: {response.status_code} {response.text[:300]}")
        return 1
    print("Discord alert sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

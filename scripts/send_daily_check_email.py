#!/usr/bin/env python3
"""Send daily_check.py output by SMTP."""

from __future__ import annotations

import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path


JST = timezone(timedelta(hours=9))


def _run_url() -> str:
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return ""


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    output_path = Path(argv[0]) if argv else Path("daily_check.out")
    status = int(os.environ.get("DAILY_CHECK_STATUS", "1"))

    host = _required_env("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = _required_env("SMTP_USER")
    password = _required_env("SMTP_PASSWORD")
    to_addr = _required_env("DAILY_CHECK_EMAIL_TO")

    output = output_path.read_text(encoding="utf-8") if output_path.exists() else "(no output)"
    now = datetime.now(JST)
    subject_icon = "OK" if status == 0 else "WARN"
    subject = f"[{subject_icon}] AI News Daily Check - {now:%Y-%m-%d}"

    run_url = _run_url()
    body = output.strip()
    if run_url:
        body += f"\n\nActions: {run_url}"

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)

    print("Daily check email sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

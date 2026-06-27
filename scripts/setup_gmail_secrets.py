#!/usr/bin/env python3
"""Interactively configure Gmail SMTP secrets for GitHub Actions."""

from __future__ import annotations

import getpass
from pathlib import Path
import subprocess
import sys


REPO = "k-hira-shine/ai-news-collector"
CONFIG_PATH = Path("gmail_secrets.txt")


def set_secret(name: str, value: str) -> None:
    subprocess.run(
        ["gh", "secret", "set", name, "--repo", REPO, "--body", value],
        check=True,
    )


def prompt(label: str, *, default: str = "", secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        if secret:
            value = getpass.getpass(f"{label}{suffix}: ").strip()
        else:
            value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        print("必須です。")


def main() -> int:
    print("Gmail SMTP secrets を GitHub Actions に登録します。")
    print("gmail_secrets.txt があれば、その内容を使います。")
    print()

    values = {}
    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

    smtp_user = values.get("SMTP_USER") or prompt("送信用Gmailアドレス")
    smtp_password = values.get("SMTP_PASSWORD") or prompt("Gmailアプリパスワード", secret=True)
    email_to = values.get("DAILY_CHECK_EMAIL_TO") or prompt("受信先メールアドレス", default=smtp_user)

    secrets = {
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USER": smtp_user,
        "SMTP_PASSWORD": smtp_password,
        "DAILY_CHECK_EMAIL_TO": email_to,
    }

    for name, value in secrets.items():
        print(f"setting {name} ...")
        set_secret(name, value)

    print()
    print("完了しました。次にメール送信workflowを追加できます。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print(f"gh secret set failed: {e}", file=sys.stderr)
        raise SystemExit(1)

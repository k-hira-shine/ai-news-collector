#!/usr/bin/env python3
"""Send daily_check.py output by SMTP."""

from __future__ import annotations

import os
import smtplib
import sys
import json
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path


JST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _clip(value: object, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _latest_analysis(base: Path) -> tuple[Path | None, dict]:
    analysis_dir = base / "data" / "analysis"
    if not analysis_dir.exists():
        return None, {}

    morning_files = sorted(analysis_dir.glob("*_morning.json"))
    files = morning_files or sorted(analysis_dir.glob("*.json"))
    if not files:
        return None, {}

    path = files[-1]
    return path, _read_json(path)


def _format_analysis_section(base: Path) -> str:
    path, analysis = _latest_analysis(base)
    if not analysis:
        return ""

    lines = [
        "",
        "=" * 64,
        "今日のAIニュース概要",
        "-" * 64,
        f"分析ファイル: {path.name if path else 'unknown'}",
    ]

    summary = _clip(analysis.get("trend_summary"), 900)
    if summary:
        lines.extend(["", summary])

    evolution = analysis.get("trend_evolution") or {}
    since_last = _clip(evolution.get("since_last"), 700)
    if since_last:
        lines.extend(["", "前回からの変化:", since_last])

    tracked_topics = evolution.get("tracked_topics") or []
    if tracked_topics:
        lines.extend(["", "注目トピック:"])
        for topic in tracked_topics[:6]:
            label = topic.get("topic", "unknown")
            status = topic.get("status", "-")
            streak = topic.get("streak_days", "-")
            detail = _clip(topic.get("evolution"), 180)
            lines.append(f"- {label} [{status}, {streak}日]: {detail}")

    top_articles = analysis.get("top_articles") or []
    if top_articles:
        lines.extend(["", "TOPニュース:"])
        for article in top_articles[:7]:
            rank = article.get("rank", "-")
            title = _clip(article.get("title"), 120)
            source = article.get("source_label") or article.get("category") or "-"
            summary = _clip(article.get("summary"), 220)
            url = article.get("url", "")
            lines.append(f"{rank}. {title} ({source})")
            if summary:
                lines.append(f"   {summary}")
            if url:
                lines.append(f"   {url}")

    categories = analysis.get("category_summaries") or []
    if categories:
        lines.extend(["", "カテゴリ別サマリー:"])
        for category in categories[:5]:
            name = category.get("category", "unknown")
            count = category.get("count", "-")
            summary = _clip(category.get("summary"), 260)
            lines.append(f"- {name} ({count}件): {summary}")

    action_items = analysis.get("action_items") or []
    if action_items:
        lines.extend(["", "見るべきポイント:"])
        for item in action_items[:4]:
            lines.append(f"- {_clip(item, 220)}")

    return "\n".join(lines)


def _format_operations_section(base: Path) -> str:
    lines = ["", "=" * 64, "収集状況・コスト", "-" * 64]
    added = False

    status = _read_json(base / "docs" / "run_status.json")
    workflows = status.get("workflows") or {}
    for key, label in [
        ("collect", "AIニュース収集"),
        ("money", "AIマネー収集"),
        ("buzz", "Buzz収集"),
    ]:
        workflow = workflows.get(key) or {}
        if not workflow:
            continue
        added = True
        parts = [f"{label}: {workflow.get('status', '-')}", f"time={workflow.get('time', '-')}"]
        for metric in [
            "items_collected",
            "top_articles",
            "money_collected",
            "sns_collected",
            "new_items",
            "items_retained",
            "guardrail_status",
        ]:
            if metric in workflow:
                parts.append(f"{metric}={workflow[metric]}")
        if workflow.get("error"):
            parts.append(f"error={_clip(workflow['error'], 160)}")
        lines.append("- " + ", ".join(parts))

    costs = _read_json(base / "data" / "cost_tracking.json")
    latest = costs.get("latest") or {}
    rolling = costs.get("rolling") or {}
    if latest or rolling:
        added = True
        lines.append("")
        if latest:
            workflows_cost = latest.get("workflows") or {}
            lines.append(
                "本日コスト: "
                f"${latest.get('total_usd', 0):.4f} "
                f"(collect=${workflows_cost.get('collect', 0):.4f}, "
                f"money=${workflows_cost.get('money', 0):.4f}, "
                f"buzz=${workflows_cost.get('buzz', 0):.4f})"
            )
        if rolling:
            lines.append(
                "7日平均: "
                f"${rolling.get('average_daily_usd', 0):.4f}/日, "
                f"月間見込み=${rolling.get('monthly_projection_usd', 0):.2f}, "
                f"status={rolling.get('status', '-')}"
            )

    return "\n".join(lines) if added else ""


def build_email_body(check_output: str, base: Path = REPO_ROOT) -> str:
    sections = [
        check_output.strip() or "(no output)",
        _format_analysis_section(base),
        _format_operations_section(base),
    ]
    return "\n".join(section for section in sections if section)


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
    body = build_email_body(output, REPO_ROOT)
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

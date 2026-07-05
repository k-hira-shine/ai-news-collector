#!/usr/bin/env python3
"""Send the latest AI news analysis by SMTP."""

from __future__ import annotations

import argparse
import os
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

try:
    from send_daily_check_email import _clip, _read_json, _required_env, _run_url
except ModuleNotFoundError:
    from scripts.send_daily_check_email import _clip, _read_json, _required_env, _run_url


JST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_BASE_URL = "https://k-hira-shine.github.io/ai-news-dashboard"
SLOT_LABELS = {"morning": "朝便", "evening": "夕便"}
SLOT_ORDER = {"morning": 0, "evening": 1}
ANALYSIS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(morning|evening)\.json$")


def _analysis_sort_key(path: Path) -> tuple[str, int, str]:
    match = ANALYSIS_RE.match(path.name)
    if not match:
        return ("0000-00-00", -1, path.name)
    date, slot = match.groups()
    return (date, SLOT_ORDER.get(slot, -1), path.name)


def latest_analysis(base: Path = REPO_ROOT) -> tuple[Path | None, dict]:
    analysis_dir = base / "data" / "analysis"
    if not analysis_dir.exists():
        return None, {}

    files = sorted(analysis_dir.glob("*.json"), key=_analysis_sort_key)
    if not files:
        return None, {}

    path = files[-1]
    return path, _read_json(path)


def _analysis_identity(path: Path | None, analysis: dict) -> tuple[str, str]:
    if path:
        match = ANALYSIS_RE.match(path.name)
        if match:
            return match.group(1), match.group(2)

    run_time = str(analysis.get("run_time") or "")
    date = run_time[:10] if len(run_time) >= 10 else datetime.now(JST).strftime("%Y-%m-%d")
    slot = str(analysis.get("slot") or "morning")
    return date, slot


def build_news_body(path: Path | None, analysis: dict, base: Path = REPO_ROOT) -> str:
    date, slot = _analysis_identity(path, analysis)
    slot_label = SLOT_LABELS.get(slot, slot)
    diagram_rel = f"diagrams/{date}-{slot}.html"
    diagram_path = base / "docs" / diagram_rel

    lines = [
        f"AIニュース {date} {slot_label}",
        "=" * 64,
        f"公開ページ: {PUBLIC_BASE_URL}/index.html",
    ]
    if diagram_path.exists():
        lines.append(f"図解版: {PUBLIC_BASE_URL}/{diagram_rel}")
    if path:
        lines.append(f"分析ファイル: {path.name}")

    summary = _clip(analysis.get("trend_summary"), 900)
    if summary:
        lines.extend(["", "概要", "-" * 64, summary])

    evolution = analysis.get("trend_evolution") or {}
    since_last = _clip(evolution.get("since_last"), 700)
    if since_last:
        lines.extend(["", "前回からの変化", "-" * 64, since_last])

    tracked_topics = evolution.get("tracked_topics") or []
    if tracked_topics:
        lines.extend(["", "注目トピック", "-" * 64])
        for topic in tracked_topics[:6]:
            label = topic.get("topic", "unknown")
            status = topic.get("status", "-")
            streak = topic.get("streak_days", "-")
            detail = _clip(topic.get("evolution"), 180)
            lines.append(f"- {label} [{status}, {streak}日]: {detail}")

    top_articles = analysis.get("top_articles") or []
    if top_articles:
        lines.extend(["", "TOPニュース", "-" * 64])
        for article in top_articles[:10]:
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
        lines.extend(["", "カテゴリ別サマリー", "-" * 64])
        for category in categories[:5]:
            name = category.get("category", "unknown")
            count = category.get("count", "-")
            summary = _clip(category.get("summary"), 260)
            lines.append(f"- {name} ({count}件): {summary}")

    actions = analysis.get("action_items") or []
    if actions:
        lines.extend(["", "見るべきポイント", "-" * 64])
        for item in actions[:4]:
            lines.append(f"- {_clip(item, 220)}")

    run_url = _run_url()
    if run_url:
        lines.extend(["", f"Actions: {run_url}"])

    return "\n".join(lines)


def _recipient() -> str:
    return os.environ.get("NEWS_EMAIL_TO", "").strip() or _required_env("DAILY_CHECK_EMAIL_TO")


def send_news_email(analysis_path: Path | None = None, base: Path = REPO_ROOT, *, dry_run: bool = False) -> None:
    if analysis_path:
        path = analysis_path
        analysis = _read_json(path)
    else:
        path, analysis = latest_analysis(base)
    if not analysis:
        raise RuntimeError("No analysis JSON found")

    date, slot = _analysis_identity(path, analysis)
    slot_label = SLOT_LABELS.get(slot, slot)
    top_title = (analysis.get("top_articles") or [{}])[0].get("title", "AIニュース")

    subject = f"[AI News] {date} {slot_label} - {_clip(top_title, 70)}"
    body = build_news_body(path, analysis, base)
    if dry_run:
        print(f"Subject: {subject}")
        print()
        print(body)
        return

    host = _required_env("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = _required_env("SMTP_USER")
    password = _required_env("SMTP_PASSWORD")
    to_addr = _recipient()

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)

    print(f"AI news email sent: {subject}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send latest AI news summary email")
    parser.add_argument("--analysis", type=Path, help="Analysis JSON to send")
    parser.add_argument("--dry-run", action="store_true", help="Print the email without sending")
    args = parser.parse_args(argv)
    send_news_email(args.analysis, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

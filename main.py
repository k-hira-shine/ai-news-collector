#!/usr/bin/env python3
"""AI News Collector — メインオーケストレータ"""

import argparse
import os
import time

import yaml

from utils import setup_logging, time_slot, today_str


def load_config(path: str = "config.yaml") -> dict:
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI News Collector")
    parser.add_argument("--dry-run", action="store_true", help="Collect only, skip analysis/notification")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=== AI News Collector started (%s %s) ===", today_str(), time_slot())
    t0 = time.time()

    config = load_config()

    # ── Step 1: Collect ───────────────────────────────────────────────
    from collector import collect_all

    items = collect_all(config)

    stats = {
        "total": len(items),
        "x_count": sum(1 for i in items if i["source"] == "x"),
        "rss_count": sum(1 for i in items if i["source"] == "rss"),
        "youtube_count": sum(1 for i in items if i["source"] == "youtube"),
        "official_count": sum(1 for i in items if i.get("is_official")),
        "must_follow_count": sum(1 for i in items if i.get("is_must_follow")),
    }
    logger.info("Collected: %s", stats)

    if args.dry_run:
        logger.info("Dry run — skipping analysis and notification")
        return

    # ── Step 2: Analyze ───────────────────────────────────────────────
    from analyzer import NewsAnalyzer

    analyzer = NewsAnalyzer(config)
    analysis = analyzer.analyze(items)

    # ── Step 3: Notify ────────────────────────────────────────────────
    from notifier import DiscordNotifier

    stats["elapsed_sec"] = time.time() - t0
    discord_cfg = config.get("discord", {})
    notifier = DiscordNotifier(
        delay=discord_cfg.get("message_delay_sec", 0.5),
        ranking_top=discord_cfg.get("ranking_top", 10),
        max_items_per_category=discord_cfg.get("max_items_per_category", 5),
    )

    if analysis.get("top_articles"):
        notifier.notify(analysis, stats)
    else:
        notifier.send_status("⚠️ 本日の AI ニュースは 0 件でした。")

    # ── Step 4: Dashboard ─────────────────────────────────────────────
    try:
        from dashboard import generate_dashboard

        output = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "index.html")
        generate_dashboard(output)
        logger.info("Dashboard generated → %s", output)
    except Exception as e:
        logger.error("Dashboard generation failed: %s", e)

    elapsed = time.time() - t0
    logger.info("=== Complete in %.1fs ===", elapsed)
    notifier.send_status(f"✅ AI News Collector 完了 ({elapsed:.0f}秒, {stats['total']}件収集)")


if __name__ == "__main__":
    main()

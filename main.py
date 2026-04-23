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
    parser.add_argument("--analyze-only", action="store_true", help="Skip collection, reuse latest daily JSONL")
    parser.add_argument("--skip-x", action="store_true", help="Skip X/Twitter collection (saves Apify credits)")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=== AI News Collector started (%s %s) ===", today_str(), time_slot())
    t0 = time.time()

    config = load_config()

    # ── Step 1: Collect ───────────────────────────────────────────────
    x_runtime: dict = {}
    runtime_meta: dict = {"x": {}, "rss": {}, "youtube": {}}
    if args.analyze_only:
        from collector import _load_latest_daily
        items = _load_latest_daily()
        logger.info("Analyze-only: loaded %d items from latest JSONL", len(items))
    else:
        from collector import _should_warn_x_cookies, collect_all
        skip_sources: set[str] = set()
        if args.skip_x:
            skip_sources.add("x")
        items, runtime_meta = collect_all(config, skip_sources=skip_sources)
        x_runtime = runtime_meta.get("x", {})

    x_items = [i for i in items if i["source"] == "x"]
    stats = {
        "total": len(items),
        "x_count": len(x_items),
        "rss_count": sum(1 for i in items if i["source"] == "rss"),
        "youtube_count": sum(1 for i in items if i["source"] == "youtube"),
        "official_count": sum(1 for i in items if i.get("is_official")),
        "must_follow_count": sum(1 for i in items if i.get("is_must_follow")),
        "apify_cost_usd": x_runtime.get("apify_cost_usd", 0),
        "apify_runs": x_runtime.get("apify_runs", 0),
        "apify_cycle_total_usd": x_runtime.get("apify_cycle_total_usd", 0),
        "apify_cycle_end": x_runtime.get("apify_cycle_end", ""),
        "apify_monthly_budget_usd": config.get("x_twitter", {}).get("apify_monthly_budget_usd", 29.0),
        "apify_warning_threshold": config.get("x_twitter", {}).get("apify_warning_threshold", 0.8),
        "x_meta": x_runtime,
        "rss_meta": runtime_meta.get("rss", {}),
        "youtube_meta": runtime_meta.get("youtube", {}),
    }
    logger.info("Collected: %s", {k: v for k, v in stats.items() if not k.endswith("_meta")})

    cookies_may_be_expired = False
    if not args.analyze_only and not args.skip_x:
        cookies_may_be_expired = _should_warn_x_cookies(x_runtime)
        if cookies_may_be_expired:
            logger.warning("⚠️ X_COOKIES may be expired — search returned 0 before filters/dedup")

    from alerts import detect_anomalies
    anomalies = detect_anomalies(stats, config)
    stats["anomalies"] = anomalies
    for a in anomalies:
        logger.warning("ALERT [%s] %s — %s", a["severity"], a["title"], a["detail"])

    if args.dry_run:
        logger.info("Dry run — skipping analysis and notification")
        return

    # ── Step 2: Analyze ───────────────────────────────────────────────
    from analyzer import NewsAnalyzer

    analyzer = NewsAnalyzer(config)
    analysis = analyzer.analyze(items)

    # ── Step 2.5: Diagram (HTML + PNG) ────────────────────────────────
    diagram_png: bytes | None = None
    diagram_cfg = config.get("diagram", {})
    if analysis.get("top_articles") and diagram_cfg.get("enabled", True):
        try:
            from diagram import DiagramBuilder

            slot = analysis.get("slot") or time_slot()
            date = today_str()
            diagram_filename = f"{date}-{slot}"

            builder = DiagramBuilder()
            html, diagram_png = builder.build(
                analysis,
                slot=slot,
                date=date,
                render_png=True,
            )

            diagrams_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "docs", "diagrams"
            )
            os.makedirs(diagrams_dir, exist_ok=True)
            html_path = os.path.join(diagrams_dir, f"{diagram_filename}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info("Diagram HTML saved → %s (png=%s bytes)", html_path, len(diagram_png) if diagram_png else 0)
        except Exception as e:
            logger.error("Diagram generation failed: %s", e)
            diagram_png = None

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
        notifier.notify(analysis, stats, diagram_png=diagram_png)
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
    status_icon = "⚠️" if anomalies else "✅"
    status_msg = f"{status_icon} AI News Collector 完了 ({elapsed:.0f}秒, {stats['total']}件収集)"
    if anomalies:
        status_msg += f"\n⚠️ 健全性アラート {len(anomalies)} 件（上の Embed を確認）"
    elif cookies_may_be_expired:
        status_msg += "\n⚠️ X_COOKIES が期限切れの可能性があります。検索結果が 0 件でした。GitHub Secrets を更新してください。"
    notifier.send_status(status_msg)


if __name__ == "__main__":
    main()

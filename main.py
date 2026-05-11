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
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=== AI News Collector started (%s %s) ===", today_str(), time_slot())
    t0 = time.time()

    config = load_config()

    # ── Step 1: Collect ───────────────────────────────────────────────
    x_meta: dict = {}
    if args.analyze_only:
        from collector import _load_latest_daily
        items = _load_latest_daily()
        logger.info("Analyze-only: loaded %d items from latest JSONL", len(items))
    else:
        from collector import _should_warn_x_cookies, collect_all
        items, x_meta = collect_all(config)

    stats = {
        "total": len(items),
        "x_count": len(items),
        "official_count": sum(1 for i in items if i.get("is_official")),
        "must_follow_count": sum(1 for i in items if i.get("is_must_follow")),
        "apify_cost_usd": x_meta.get("apify_cost_usd", 0),
        "apify_runs": x_meta.get("apify_runs", 0),
        "apify_cycle_total_usd": x_meta.get("apify_cycle_total_usd", 0),
        "apify_cycle_end": x_meta.get("apify_cycle_end", ""),
        "apify_monthly_budget_usd": config.get("x_twitter", {}).get("apify_monthly_budget_usd", 29.0),
        "apify_warning_threshold": config.get("x_twitter", {}).get("apify_warning_threshold", 0.8),
        "x_meta": x_meta,
    }
    logger.info("Collected: %s", {k: v for k, v in stats.items() if not k.endswith("_meta")})

    cookies_may_be_expired = False
    if not args.analyze_only:
        cookies_may_be_expired = _should_warn_x_cookies(x_meta)
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
    a_save = analysis.get("analysis_save") or {}
    stats["analysis_meta"] = {
        "top_articles_count": len(analysis.get("top_articles") or []),
        "fallback_used_stages": list(analysis.get("fallback_used_stages") or []),
        "save_ok": a_save.get("ok", True),
        "save_path": a_save.get("path", ""),
        "save_error": a_save.get("error", ""),
    }

    # ── Step 2.5: Diagram (HTML + PNG) ────────────────────────────────
    diagram_png: bytes | None = None
    diagram_cfg = config.get("diagram", {})
    diagram_meta = {
        "enabled": bool(diagram_cfg.get("enabled", True)),
        "attempted": False,
        "html_saved": False,
        "png_generated": False,
        "error": "",
    }
    if analysis.get("top_articles") and diagram_cfg.get("enabled", True):
        diagram_meta["attempted"] = True
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
            diagram_meta["html_saved"] = True
            diagram_meta["png_generated"] = diagram_png is not None
            logger.info("Diagram HTML saved → %s (png=%s bytes)", html_path, len(diagram_png) if diagram_png else 0)
        except Exception as e:
            logger.error("Diagram generation failed: %s", e)
            diagram_png = None
            diagram_meta["error"] = str(e)[:200]
    stats["diagram_meta"] = diagram_meta

    # diagram_meta が揃った後に再検知
    anomalies = detect_anomalies(stats, config)
    stats["anomalies"] = anomalies
    for a in anomalies:
        logger.warning("ALERT [%s] %s — %s", a["severity"], a["title"], a["detail"])

    # ── Step 3: Dashboard ─────────────────────────────────────────────
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
    logger.info("%s AI News Collector 完了 (%ds, %d件収集)", status_icon, int(elapsed), stats["total"])
    if anomalies:
        logger.warning("⚠️ 健全性アラート %d 件", len(anomalies))
    elif cookies_may_be_expired:
        logger.warning("⚠️ X_COOKIES が期限切れの可能性があります。検索結果が 0 件でした。GitHub Secrets を更新してください。")


if __name__ == "__main__":
    main()

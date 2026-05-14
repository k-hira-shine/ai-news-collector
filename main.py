#!/usr/bin/env python3
"""AI News Collector — メインオーケストレータ"""

import argparse
import os
import time

import yaml

from utils import log_run, setup_logging, time_slot, today_str, write_run_status


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

    # コスト情報を analysis に付与して再保存（analysis_save は analyzer 内で先に保存済み）
    analysis["cost"] = {
        "apify_usd": x_meta.get("apify_cost_usd", 0),
        "apify_runs": x_meta.get("apify_runs", 0),
        "apify_cycle_total_usd": x_meta.get("apify_cycle_total_usd", 0),
        "apify_cycle_end": x_meta.get("apify_cycle_end", ""),
        "apify_monthly_budget_usd": config.get("x_twitter", {}).get("apify_monthly_budget_usd", 29.0),
        "gemini_usd": 0,  # 無料枠内のため0
        "github_actions_usd": 0,  # パブリックリポジトリのため0
    }
    # コスト情報を含む形で上書き保存
    try:
        analyzer._try_save_analysis(analysis)
    except Exception as e:
        logger.warning("Cost re-save failed: %s", e)

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
            # PNG を保存
            if diagram_png:
                png_path = os.path.join(diagrams_dir, f"{diagram_filename}.png")
                with open(png_path, "wb") as f:
                    f.write(diagram_png)
                diagram_meta["png_path"] = f"diagrams/{diagram_filename}.png"
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

    # ── Step 3.5: Strategy Page ────────────────────────────────────────
    try:
        from dashboard import generate_strategy_page

        strategy_output = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "strategy.html")
        generate_strategy_page(strategy_output)
        logger.info("Strategy page generated → %s", strategy_output)
    except Exception as e:
        logger.error("Strategy page generation failed: %s", e)

    # ── Step 4: Tools Tracking ────────────────────────────────────────
    try:
        from tools_collector import (
            collect_reddit_posts,
            collect_rss_feeds,
            deduplicate_tools,
            extract_from_hn,
            extract_from_x,
            load_all_tools_items,
            save_tools_jsonl,
        )
        from tools_analyzer import analyze_tools_items, save_tools_analysis

        tools_cfg = config.get("tools_tracking", {})
        if tools_cfg.get("enabled", True):
            # RSS収集
            rss_items = collect_rss_feeds(config) if not args.analyze_only else []
            reddit_items = collect_reddit_posts(config) if not args.analyze_only else []

            # 既存X/HNデータからキーワード抽出
            x_tool_items = extract_from_x(items) if items else []
            from build_hn import load_all_dates as _load_hn
            hn_raw = []
            for date_items in _load_hn(days=2).values():
                hn_raw.extend(date_items)
            hn_tool_items = extract_from_hn(hn_raw)

            # マージ・重複排除・JSONL保存
            all_tool_candidates = deduplicate_tools(rss_items + reddit_items + x_tool_items + hn_tool_items)
            if all_tool_candidates:
                save_tools_jsonl(all_tool_candidates)
                # Gemini分析
                analyzed = analyze_tools_items(all_tool_candidates, config)
                if analyzed:
                    save_tools_analysis(analyzed)
                    logger.info("Tools: %d items analyzed", len(analyzed))

            # ページ生成
            from build_tools import build_tools_page
            tools_output = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "tools.html")
            build_tools_page(tools_output)
            logger.info("Tools page generated → %s", tools_output)
    except Exception as e:
        logger.error("Tools tracking failed: %s", e)


    elapsed = time.time() - t0
    logger.info("=== Complete in %.1fs ===", elapsed)
    status_icon = "⚠️" if anomalies else "✅"
    logger.info("%s AI News Collector 完了 (%ds, %d件収集)", status_icon, int(elapsed), stats["total"])

    log_status = "warning" if anomalies else "success"
    error_msg = "; ".join(a["title"] for a in anomalies) if anomalies else ""
    log_run(
        "collect",
        log_status,
        elapsed_sec=elapsed,
        items_collected=stats["total"],
        apify_cost_usd=stats["apify_cost_usd"],
        error=error_msg,
        extra={
            "mode": "analyze-only" if args.analyze_only else "full",
            "top_articles": stats.get("analysis_meta", {}).get("top_articles_count", 0),
            "diagram_png": diagram_meta.get("png_generated", False),
            "anomalies": len(anomalies),
        },
    )
    write_run_status("collect", log_status, error=error_msg,
                     extra={"items_collected": stats["total"],
                            "top_articles": stats.get("analysis_meta", {}).get("top_articles_count", 0)})

    if anomalies:
        logger.warning("⚠️ 健全性アラート %d 件", len(anomalies))
    elif cookies_may_be_expired:
        logger.warning("⚠️ X_COOKIES が期限切れの可能性があります。検索結果が 0 件でした。GitHub Secrets を更新してください。")


if __name__ == "__main__":
    main()

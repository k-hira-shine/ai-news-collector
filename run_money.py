#!/usr/bin/env python3
"""AIマネタイズ事例収集・分析・ページ生成スクリプト

使い方:
  python run_money.py              # 収集 → 分析 → ページ生成
  python run_money.py --page-only  # ページ生成のみ（データ変更なし）
  python run_money.py --analyze-only  # 収集済みデータの分析 → ページ生成
"""

import argparse
import logging
import os
import sys
import time

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_config(path: str = "config.yaml") -> dict:
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Money Cases Collector")
    parser.add_argument("--page-only", action="store_true", help="ページ生成のみ")
    parser.add_argument("--analyze-only", action="store_true", help="収集済みデータの分析のみ")
    parser.add_argument("--dry-run", action="store_true", help="収集のみ、分析しない")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("run_money")

    config = load_config()
    t0 = time.time()
    from utils import log_run, write_run_status

    # ── ページ生成のみ ─────────────────────────────────
    if args.page_only:
        logger.info("Page-only mode: generating money.html from existing data")
        _generate_page()
        elapsed = time.time() - t0
        log_run("money", "success", elapsed_sec=elapsed, extra={"mode": "page-only"})
        logger.info("Done in %.1fs", elapsed)
        return

    # ── 収集 ──────────────────────────────────────────
    new_items = []
    apify_cost = 0.0
    collected = 0
    try:
        if not args.analyze_only:
            from money_collector import collect_money_cases, deduplicate_money, save_money_jsonl

            logger.info("=== Step 1: Collecting money cases ===")
            items, meta = collect_money_cases(config)
            apify_cost = meta.get("apify_cost_usd", 0)
            logger.info("Fetched %d posts (cost=$%.4f)", len(items), apify_cost)

            if meta.get("error"):
                logger.error("Collection error: %s", meta["error"])
                if not items:
                    log_run("money", "error", elapsed_sec=time.time()-t0, error=str(meta["error"]), extra={"mode": "full"})
                    sys.exit(1)

            new_items = deduplicate_money(items)
            collected = len(new_items)
            logger.info("New (deduplicated) posts: %d", collected)

            if new_items:
                save_money_jsonl(new_items)

            if args.dry_run:
                elapsed = time.time() - t0
                log_run("money", "success", elapsed_sec=elapsed, items_collected=collected, apify_cost_usd=apify_cost, extra={"mode": "dry-run"})
                logger.info("Dry-run: skipping analysis. Done in %.1fs", elapsed)
                return

        # ── 分析 ──────────────────────────────────────────
        logger.info("=== Step 2: Analyzing money cases with Gemini ===")

        if args.analyze_only:
            from money_collector import load_all_money_items
            from money_analyzer import load_all_money_analyses
            all_items = load_all_money_items()
            analyzed_ids = {c["id"] for c in load_all_money_analyses()}
            new_items = [i for i in all_items if i.get("id") not in analyzed_ids]
            logger.info("Unanalyzed posts: %d", len(new_items))

        analyzed = 0
        if new_items:
            from money_analyzer import analyze_money_cases, save_money_analysis
            from utils import time_slot, today_str

            cases = analyze_money_cases(new_items, config)
            analyzed = len(cases)
            logger.info("Found %d money cases out of %d posts", analyzed, len(new_items))

            if cases:
                save_money_analysis(cases, today_str(), time_slot())
        else:
            logger.info("No new posts to analyze")

        # ── ページ生成 ────────────────────────────────────
        logger.info("=== Step 3: Generating money.html ===")
        _generate_page()

        elapsed = time.time() - t0
        mode = "analyze-only" if args.analyze_only else "full"
        log_run("money", "success", elapsed_sec=elapsed, items_collected=collected,
                items_analyzed=analyzed, apify_cost_usd=apify_cost, extra={"mode": mode})

        COST_ALERT_THRESHOLD = 1.0
        if apify_cost >= COST_ALERT_THRESHOLD:
            run_status = "warning"
            run_error = f"Apifyコストが異常値: ${apify_cost:.3f} (閾値 ${COST_ALERT_THRESHOLD:.2f})"
            logger.warning(run_error)
        else:
            run_status = "success"
            run_error = ""
        write_run_status("money", run_status, error=run_error,
                         extra={"items_collected": collected, "items_analyzed": analyzed,
                                "mode": mode, "cost_usd": round(apify_cost, 4)})
        logger.info("=== Complete in %.1fs ===", elapsed)

    except Exception as e:
        elapsed = time.time() - t0
        logger.exception("Unexpected error: %s", e)
        log_run("money", "error", elapsed_sec=elapsed, items_collected=collected,
                apify_cost_usd=apify_cost, error=str(e))
        write_run_status("money", "error", error=str(e)[:200])
        sys.exit(1)


def _generate_page() -> None:
    from money_dashboard import generate_money_page

    output = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "money.html")
    generate_money_page(output)


if __name__ == "__main__":
    main()

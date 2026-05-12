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

    # ── ページ生成のみ ─────────────────────────────────
    if args.page_only:
        logger.info("Page-only mode: generating money.html from existing data")
        _generate_page()
        logger.info("Done in %.1fs", time.time() - t0)
        return

    # ── 収集 ──────────────────────────────────────────
    new_items = []
    if not args.analyze_only:
        from money_collector import collect_money_cases, deduplicate_money, save_money_jsonl

        logger.info("=== Step 1: Collecting money cases ===")
        items, meta = collect_money_cases(config)
        logger.info("Fetched %d posts (cost=$%.4f)", len(items), meta.get("apify_cost_usd", 0))

        if meta.get("error"):
            logger.error("Collection error: %s", meta["error"])
            if not items:
                sys.exit(1)

        new_items = deduplicate_money(items)
        logger.info("New (deduplicated) posts: %d", len(new_items))

        if new_items:
            save_money_jsonl(new_items)

        if args.dry_run:
            logger.info("Dry-run: skipping analysis. Done in %.1fs", time.time() - t0)
            return

    # ── 分析 ──────────────────────────────────────────
    logger.info("=== Step 2: Analyzing money cases with Gemini ===")

    if args.analyze_only:
        # 未分析の全ポストを対象に
        from money_collector import load_all_money_items
        from money_analyzer import load_all_money_analyses
        all_items = load_all_money_items()
        analyzed_ids = {c["id"] for c in load_all_money_analyses()}
        new_items = [i for i in all_items if i.get("id") not in analyzed_ids]
        logger.info("Unanalyzed posts: %d", len(new_items))

    if new_items:
        from money_analyzer import analyze_money_cases, save_money_analysis
        from utils import time_slot, today_str

        cases = analyze_money_cases(new_items, config)
        logger.info("Found %d money cases out of %d posts", len(cases), len(new_items))

        if cases:
            save_money_analysis(cases, today_str(), time_slot())
    else:
        logger.info("No new posts to analyze")

    # ── ページ生成 ────────────────────────────────────
    logger.info("=== Step 3: Generating money.html ===")
    _generate_page()

    logger.info("=== Complete in %.1fs ===", time.time() - t0)


def _generate_page() -> None:
    from money_dashboard import generate_money_page

    output = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "money.html")
    generate_money_page(output)


if __name__ == "__main__":
    main()

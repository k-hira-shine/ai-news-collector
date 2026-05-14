#!/usr/bin/env python3
"""AIマネタイズ事例 + SNS成功者マインド収集・分析・ページ生成スクリプト

使い方:
  python run_money.py              # 収集 → 分析 → ページ生成（money + sns_success）
  python run_money.py --page-only  # ページ生成のみ（データ変更なし）
  python run_money.py --analyze-only  # 収集済みデータの分析 → ページ生成
  python run_money.py --money-only    # money収集のみ（sns_successをスキップ）
  python run_money.py --sns-only      # sns_success収集のみ（moneyをスキップ）
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
    parser = argparse.ArgumentParser(description="AI Money Cases + SNS Success Collector")
    parser.add_argument("--page-only", action="store_true", help="ページ生成のみ")
    parser.add_argument("--analyze-only", action="store_true", help="収集済みデータの分析のみ")
    parser.add_argument("--dry-run", action="store_true", help="収集のみ、分析しない")
    parser.add_argument("--money-only", action="store_true", help="money収集のみ（sns_successをスキップ）")
    parser.add_argument("--sns-only", action="store_true", help="sns_success収集のみ（moneyをスキップ）")
    parser.add_argument("--skip-post-gen", action="store_true", help="投稿ジェネレーター生成をスキップ")
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
        logger.info("Page-only mode: generating money.html + sns_success.html + post_generator.html from existing data")
        _generate_page()
        _generate_sns_page()
        _generate_post_generator_page(config)
        elapsed = time.time() - t0
        log_run("money", "success", elapsed_sec=elapsed, extra={"mode": "page-only"})
        logger.info("Done in %.1fs", elapsed)
        return

    # ── 収集 ──────────────────────────────────────────
    new_money_items = []
    new_sns_items = []
    apify_cost = 0.0
    collected_money = 0
    collected_sns = 0

    run_money = not args.sns_only
    run_sns = not args.money_only

    try:
        if not args.analyze_only:
            # money収集
            if run_money:
                from money_collector import collect_money_cases, deduplicate_money, save_money_jsonl

                logger.info("=== Step 1a: Collecting money cases ===")
                items, meta = collect_money_cases(config)
                apify_cost += meta.get("apify_cost_usd", 0)
                logger.info("Money fetched %d posts (cost=$%.4f)", len(items), meta.get("apify_cost_usd", 0))

                if meta.get("error") and not items:
                    logger.error("Money collection error: %s", meta["error"])
                else:
                    new_money_items = deduplicate_money(items)
                    collected_money = len(new_money_items)
                    logger.info("New money posts (deduplicated): %d", collected_money)
                    if new_money_items:
                        save_money_jsonl(new_money_items)

            # sns_success収集
            if run_sns:
                from sns_collector import collect_sns_success, deduplicate_sns, save_sns_jsonl

                logger.info("=== Step 1b: Collecting SNS success minds ===")
                sns_items, sns_meta = collect_sns_success(config)
                apify_cost += sns_meta.get("apify_cost_usd", 0)
                logger.info("SNS fetched %d posts (cost=$%.4f)", len(sns_items), sns_meta.get("apify_cost_usd", 0))

                if not sns_meta.get("error") or sns_items:
                    new_sns_items = deduplicate_sns(sns_items)
                    collected_sns = len(new_sns_items)
                    logger.info("New SNS posts (deduplicated): %d", collected_sns)
                    if new_sns_items:
                        save_sns_jsonl(new_sns_items)

            if args.dry_run:
                elapsed = time.time() - t0
                log_run("money", "success", elapsed_sec=elapsed,
                        items_collected=collected_money + collected_sns,
                        apify_cost_usd=apify_cost, extra={"mode": "dry-run"})
                logger.info("Dry-run: skipping analysis. Done in %.1fs", elapsed)
                return

        # ── 分析 ──────────────────────────────────────────
        from utils import time_slot, today_str

        analyzed_money = 0
        analyzed_sns = 0

        # money分析
        if run_money:
            logger.info("=== Step 2a: Analyzing money cases with Gemini ===")

            if args.analyze_only:
                from money_collector import load_all_money_items
                from money_analyzer import load_all_money_analyses
                all_items = load_all_money_items()
                analyzed_ids = {c["id"] for c in load_all_money_analyses()}
                new_money_items = [i for i in all_items if i.get("id") not in analyzed_ids]
                logger.info("Unanalyzed money posts: %d", len(new_money_items))

            if new_money_items:
                from money_analyzer import analyze_money_cases, save_money_analysis

                cases = analyze_money_cases(new_money_items, config)
                analyzed_money = len(cases)
                logger.info("Found %d money cases out of %d posts", analyzed_money, len(new_money_items))
                if cases:
                    save_money_analysis(cases, today_str(), time_slot())
            else:
                logger.info("No new money posts to analyze")

        # sns_success分析
        if run_sns:
            logger.info("=== Step 2b: Analyzing SNS success minds with Gemini ===")

            if args.analyze_only:
                from sns_collector import load_all_sns_items
                from sns_analyzer import load_all_sns_analyses
                all_sns = load_all_sns_items()
                analyzed_sns_ids = {p["id"] for p in load_all_sns_analyses()}
                new_sns_items = [i for i in all_sns if i.get("id") not in analyzed_sns_ids]
                logger.info("Unanalyzed SNS posts: %d", len(new_sns_items))

            # 通常実行時: 新規収集分 + 過去未分析から最大100件を追加処理
            if new_sns_items and not args.analyze_only:
                from sns_collector import load_all_sns_items
                from sns_analyzer import load_all_sns_analyses
                all_sns = load_all_sns_items()
                analyzed_sns_ids = {p["id"] for p in load_all_sns_analyses()}
                new_ids = {i["id"] for i in new_sns_items}
                backlog = [
                    i for i in all_sns
                    if i.get("id") not in analyzed_sns_ids and i.get("id") not in new_ids
                ]
                BACKLOG_LIMIT = 500
                if backlog:
                    logger.info("Backlog: %d unanalyzed posts, processing up to %d", len(backlog), BACKLOG_LIMIT)
                    new_sns_items = new_sns_items + backlog[:BACKLOG_LIMIT]

            if new_sns_items:
                from sns_analyzer import analyze_sns_posts, save_sns_analysis

                sns_posts = analyze_sns_posts(new_sns_items, config)
                analyzed_sns = len(sns_posts)
                logger.info("Found %d valuable SNS posts out of %d", analyzed_sns, len(new_sns_items))
                if sns_posts:
                    save_sns_analysis(sns_posts, today_str(), time_slot())
            else:
                logger.info("No new SNS posts to analyze")

        # ── ページ生成 ────────────────────────────────────
        logger.info("=== Step 3: Generating HTML pages ===")
        if run_money:
            _generate_page()
        if run_sns:
            _generate_sns_page()

        # ── 投稿ジェネレーター生成・更新 ──────────────────
        if run_sns and not args.skip_post_gen and not args.analyze_only:
            logger.info("=== Step 4: Generating post_generator.html ===")
            from post_generator import generate_posts
            generated = generate_posts(config)
            logger.info("Post generator: %d posts generated", len(generated))
        _generate_post_generator_page(config)

        elapsed = time.time() - t0
        total_collected = collected_money + collected_sns
        total_analyzed = analyzed_money + analyzed_sns
        mode = "analyze-only" if args.analyze_only else ("money-only" if args.money_only else ("sns-only" if args.sns_only else "full"))
        log_run("money", "success", elapsed_sec=elapsed, items_collected=total_collected,
                items_analyzed=total_analyzed, apify_cost_usd=apify_cost, extra={"mode": mode})

        COST_ALERT_THRESHOLD = 1.0
        if apify_cost >= COST_ALERT_THRESHOLD:
            run_status = "warning"
            run_error = f"Apifyコストが異常値: ${apify_cost:.3f} (閾値 ${COST_ALERT_THRESHOLD:.2f})"
            logger.warning(run_error)
        else:
            run_status = "success"
            run_error = ""
        write_run_status("money", run_status, error=run_error,
                         extra={"money_collected": collected_money, "sns_collected": collected_sns,
                                "money_analyzed": analyzed_money, "sns_analyzed": analyzed_sns,
                                "mode": mode, "cost_usd": round(apify_cost, 4)})
        logger.info("=== Complete in %.1fs ===", elapsed)

    except Exception as e:
        elapsed = time.time() - t0
        logger.exception("Unexpected error: %s", e)
        log_run("money", "error", elapsed_sec=elapsed, items_collected=collected_money + collected_sns,
                apify_cost_usd=apify_cost, error=str(e))
        write_run_status("money", "error", error=str(e)[:200])
        sys.exit(1)


def _generate_page() -> None:
    from money_dashboard import generate_money_page

    output = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "money.html")
    generate_money_page(output)


def _generate_sns_page() -> None:
    from sns_dashboard import generate_sns_page

    output = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "sns_success.html")
    generate_sns_page(output)


def _generate_post_generator_page(config: dict) -> None:
    from post_generator import generate_post_generator_page

    output = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "post_generator.html")
    generate_post_generator_page(output, config)


if __name__ == "__main__":
    main()

"""収集実行結果の健全性チェック（Silent Failure 検知）

GitHub Actions としては success で終わっても、内部で劣化しているケース
（Actor API 変更・Cookie 失効・RSS 大量失敗など）を拾って Discord へ
警告 Embed を送る。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ai-news.alerts")


SEVERITY_COLORS = {
    "critical": 0xE74C3C,
    "warning": 0xF39C12,
}


def detect_anomalies(stats: dict[str, Any], config: dict[str, Any]) -> list[dict[str, str]]:
    """stats と config から異常を検出してアラートリストを返す

    各アラート: {"severity": "critical"|"warning", "title": "...", "detail": "..."}
    """
    alerts_cfg = config.get("alerts", {})
    if not alerts_cfg.get("enabled", True):
        return []

    alerts: list[dict[str, str]] = []

    # ── X 関連 ────────────────────────────────────────────────────────
    x_meta = stats.get("x_meta") or {}
    search_configured = x_meta.get("search_queries_configured", 0)
    search_errors = x_meta.get("search_error_count", 0)
    auth_errors = x_meta.get("auth_error_count", 0)
    search_total = x_meta.get("search_total", 0)
    must_follow_items = x_meta.get("must_follow_items", 0)
    must_follow_configured = x_meta.get("must_follow_configured", 0)
    apify_runs = stats.get("apify_runs", 0)
    has_apify = x_meta.get("has_apify", False)
    has_cookies = x_meta.get("has_cookies", False)

    # 検索クエリが全滅 (Actor API 変更 / 入力バリデーション エラーの典型)
    if has_apify and search_configured > 0 and search_errors >= search_configured:
        alerts.append({
            "severity": "critical",
            "title": "X 検索クエリが全滅",
            "detail": (
                f"{search_errors}/{search_configured} クエリが失敗。"
                "Apify Actor の入力バリデーションエラー（scrapeMode 改名など）または "
                "Cookie 失効の可能性。\n"
                "→ `gh run view <RUN_ID> --log | grep 'X search'` で原因確認。"
            ),
        })
    elif has_apify and search_configured > 0 and search_errors > 0:
        alerts.append({
            "severity": "warning",
            "title": f"X 検索で {search_errors} クエリが失敗",
            "detail": f"{search_errors}/{search_configured} クエリがエラー。部分的劣化。",
        })

    # Cookie 認証エラー
    if auth_errors > 0:
        alerts.append({
            "severity": "critical",
            "title": "X Cookie 認証エラー検出 — 手動更新が必要",
            "detail": (
                f"{auth_errors} 件の Apify run ログに auth エラー（Cookie health check FAILED / ProxyAuthRequired 等）。"
                "X_COOKIES が失効しています。\n"
                "【更新手順】\n"
                "1. Chrome で x.com にログイン\n"
                "2. DevTools (F12) → Application → Cookies → https://x.com\n"
                "3. auth_token と ct0 の値をコピー\n"
                "4. gh secret set X_COOKIES --repo k-hira-shine/ai-news-collector\n"
                '   --body \'auth_token=<値>; ct0=<値>\''
            ),
        })

    # Apify 起動回数が想定を大きく下回る
    # 2026-04-23 以降: 検索もバッチ化したので 1 run
    expected_runs = 0
    if has_apify and has_cookies and search_configured > 0:
        expected_runs += 1  # search batch は 1 回
    if has_apify and must_follow_configured > 0:
        expected_runs += 1  # timeline batch は 1 回
    if expected_runs > 0 and apify_runs < expected_runs:
        diff = expected_runs - apify_runs
        alerts.append({
            "severity": "warning" if diff < expected_runs else "critical",
            "title": f"Apify 起動回数が想定未満 ({apify_runs}/{expected_runs})",
            "detail": (
                f"期待 {expected_runs} 回に対し実績 {apify_runs} 回。"
                "Actor 呼び出しが想定通りにスケジュールされていない可能性。"
            ),
        })

    # 必須アカウント収集が完全失敗
    if must_follow_configured > 0 and x_meta.get("must_follow_error"):
        alerts.append({
            "severity": "critical",
            "title": "必須アカウントのタイムライン取得が失敗",
            "detail": "timeline batch がエラー終了。Cookie か Actor 側の問題。",
        })

    # ── Analyzer 関連（Gemini フォールバック使用 = 品質劣化の可能性）────
    analysis_meta = stats.get("analysis_meta") or {}
    fallback_stages = analysis_meta.get("fallback_used_stages") or []
    if fallback_stages:
        alerts.append({
            "severity": "warning",
            "title": "Gemini モデルがフォールバック動作",
            "detail": (
                f"{'/'.join(fallback_stages)} で primary モデルがエラー（429/5xx）、"
                "fallback モデルに切替。分析品質が通常より低い可能性あり。"
            ),
        })
    if alerts_cfg.get("analysis_json_save_alert", True) and not analysis_meta.get("save_ok", True):
        err = (analysis_meta.get("save_error") or "")[:200]
        alerts.append({
            "severity": "critical",
            "title": "分析 JSON の保存に失敗",
            "detail": f"data/analysis/ への書き込み失敗。ディスク or パーミッションを確認。\n{err}",
        })

    # ── Diagram 生成関連 ─────────────────────────────────────────────
    diagram_meta = stats.get("diagram_meta") or {}
    if diagram_meta.get("attempted") and not diagram_meta.get("png_generated"):
        detail = "PNG 生成に失敗（テキストのみ配信）。Playwright/Chromium の状態を確認。"
        if diagram_meta.get("error"):
            detail += f"\nError: {diagram_meta['error']}"
        alerts.append({
            "severity": "warning",
            "title": "図解 PNG 生成失敗",
            "detail": detail,
        })

    # ── コスト関連（既存の budget 警告とは別に、急増を検知）────────────
    cycle_total = stats.get("apify_cycle_total_usd", 0)
    budget = stats.get("apify_monthly_budget_usd", 29.0)
    threshold = stats.get("apify_warning_threshold", 0.8)
    if cycle_total and cycle_total >= budget * threshold:
        alerts.append({
            "severity": "warning",
            "title": f"Apify 月間予算 {threshold * 100:.0f}% 到達",
            "detail": (
                f"通算 ${cycle_total:.2f} / ${budget:.0f}（残り "
                f"${max(0, budget - cycle_total):.2f}）"
            ),
        })

    return alerts


def build_alert_embed(alerts: list[dict[str, str]]) -> dict | None:
    """アラートリストから Discord Embed を構築（アラート 0 件なら None）"""
    if not alerts:
        return None

    has_critical = any(a["severity"] == "critical" for a in alerts)
    color = SEVERITY_COLORS["critical"] if has_critical else SEVERITY_COLORS["warning"]
    icon = "🚨" if has_critical else "⚠️"

    lines: list[str] = []
    for a in alerts:
        sev_icon = "🔴" if a["severity"] == "critical" else "🟡"
        lines.append(f"{sev_icon} **{a['title']}**\n{a['detail']}")

    return {
        "title": f"{icon} 健全性アラート",
        "description": "\n\n".join(lines)[:4096],
        "color": color,
    }

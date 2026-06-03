"""収集実行結果の健全性チェック（Silent Failure 検知）

GitHub Actions としては success で終わっても、内部で劣化しているケース
（Actor API 変更・Cookie 失効・Gemini フォールバックなど）を拾って
ログと健全性アラートに反映する。
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
    x_valid_count = x_meta.get("x_valid_count")
    must_follow_items = x_meta.get("must_follow_items", 0)
    must_follow_configured = x_meta.get("must_follow_configured", 0)
    apify_runs = stats.get("apify_runs", 0)
    has_apify = x_meta.get("has_apify", False)
    has_cookies = x_meta.get("has_cookies", False)
    search_failure_detail = (x_meta.get("search_failure_detail") or "").strip()
    must_follow_failure_detail = (x_meta.get("must_follow_failure_detail") or "").strip()
    apify_hints = x_meta.get("apify_failure_hints") or []
    invalid_stripped = x_meta.get("invalid_items_stripped", 0)

    def _append_search_alert(severity: str, title: str, base_detail: str) -> None:
        detail = base_detail
        if search_failure_detail:
            detail += f"\n原因: {search_failure_detail}"
        elif apify_hints:
            detail += f"\n検出: {', '.join(apify_hints)}"
        alerts.append({"severity": severity, "title": title, "detail": detail})

    # 検索クエリが全滅 (Actor API 変更 / 入力バリデーション / x_api_unavailable 等)
    if has_apify and search_configured > 0 and search_errors >= search_configured:
        _append_search_alert(
            "critical",
            "X 検索クエリが全滅",
            (
                f"{search_errors}/{search_configured} クエリが失敗。"
                "Apify Actor の入力バリデーション、Cookie 失効、上流 API 障害の可能性。\n"
                "→ `gh run view <RUN_ID> --log | grep -E 'X search|x_api_unavailable'`"
            ),
        )
    elif has_apify and search_configured > 0 and search_errors > 0:
        _append_search_alert(
            "warning",
            f"X 検索で {search_errors} クエリが失敗",
            f"{search_errors}/{search_configured} クエリがエラー。部分的劣化。",
        )
    # SUCCEEDED だが search_error_count が立たない旧経路: 0 件のみ
    elif (
        has_apify
        and search_configured > 0
        and search_total == 0
        and search_errors == 0
        and (search_failure_detail or apify_hints)
    ):
        _append_search_alert(
            "critical",
            "X 検索が 0 件（Actor は成功終了）",
            (
                f"設定 {search_configured} クエリに対し取得 0 件。"
                "ログに x_api_unavailable / 502 等があると上流障害の可能性。"
            ),
        )

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

    # 空レコードのみ・フィルタ後に実質 0 件
    if has_apify and apify_runs > 0 and x_valid_count is not None and x_valid_count == 0:
        detail = "Apify は起動したが有効ツイートが 0 件。図解・分析がスキップされます。"
        if invalid_stripped:
            detail += f"\n空/不正レコード {invalid_stripped} 件を除外済み。"
        if search_failure_detail or must_follow_failure_detail:
            detail += "\n" + " / ".join(
                d for d in (search_failure_detail, must_follow_failure_detail) if d
            )
        alerts.append({
            "severity": "critical",
            "title": "X 収集結果が実質 0 件",
            "detail": detail,
        })
    elif invalid_stripped > 0:
        alerts.append({
            "severity": "warning",
            "title": f"空/不正ツイート {invalid_stripped} 件を除外",
            "detail": "Apify が空レコードを返した可能性。上流 API 障害時に発生しやすい。",
        })

    # 必須アカウント収集が完全失敗
    if must_follow_configured > 0 and x_meta.get("must_follow_error"):
        detail = "timeline batch がエラー終了、または 0 件。Cookie か Actor 側の問題。"
        if must_follow_failure_detail:
            detail += f"\n原因: {must_follow_failure_detail}"
        alerts.append({
            "severity": "critical",
            "title": "必須アカウントのタイムライン取得が失敗",
            "detail": detail,
        })
    elif (
        has_apify
        and must_follow_configured > 0
        and must_follow_items == 0
        and must_follow_failure_detail
        and not x_meta.get("must_follow_error")
    ):
        alerts.append({
            "severity": "warning",
            "title": "必須アカウントのタイムラインが 0 件",
            "detail": must_follow_failure_detail,
        })

    # ── Analyzer 関連 ─────────────────────────────────────────────────
    analysis_meta = stats.get("analysis_meta") or {}
    top_count = analysis_meta.get("top_articles_count", 0)
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

    if top_count == 0 and has_apify and apify_runs > 0:
        alerts.append({
            "severity": "critical",
            "title": "分析の top_articles が 0 件",
            "detail": (
                "Gemini 分析後に掲載記事がなく、図解 HTML/PNG は生成されません。"
                "直前の X 収集失敗・空レコードを先に確認してください。"
            ),
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
    elif (
        diagram_meta.get("enabled", True)
        and not diagram_meta.get("attempted")
        and top_count == 0
        and has_apify
        and apify_runs > 0
    ):
        alerts.append({
            "severity": "critical",
            "title": "図解が生成されなかった（記事 0 件）",
            "detail": (
                "diagram は top_articles 必須のためスキップ。"
                "最新図解リンクが前回のまま残ります。"
            ),
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

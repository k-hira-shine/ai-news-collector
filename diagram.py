"""AI ニュース図解生成: analysis dict → HTML + PNG"""

import logging
import os
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger("ai-news.diagram")

# カテゴリ名 → テンプレート用クラス名のマッピング
CATEGORY_CLASS = {
    "モデル/ツール": "cat-model",
    "企業動向": "cat-biz",
    "規制/政策": "cat-reg",
    "研究論文": "cat-research",
    "資金調達": "cat-fund",
    "ユースケース": "cat-usecase",
}

STATUS_ICONS = {
    "NEW": "⚡",
    "RISING": "📈",
    "SUSTAINED": "➡️",
    "FADING": "📉",
    "RESURFACED": "🔄",
}

BUZZ_ICONS = {
    "high": "🔥🔥🔥",
    "medium": "🔥🔥",
    "low": "🔥",
}

SLOT_LABELS = {"morning": "朝便", "evening": "夕便"}


class DiagramBuilder:
    """analysis dict から図解 HTML を生成し、必要に応じて PNG へレンダリング"""

    def __init__(self, template_dir: str | None = None):
        base = os.path.dirname(os.path.abspath(__file__))
        self.template_dir = template_dir or os.path.join(base, "templates")
        self.env = Environment(
            loader=FileSystemLoader(self.template_dir),
            autoescape=select_autoescape(["html"]),
        )

    def build_html(
        self,
        analysis: dict,
        slot: str = "morning",
        date: str | None = None,
        dashboard_url: str = "",
    ) -> str:
        """HTML 文字列のみ生成（LLM 呼び出しなし、依存は Jinja2 のみ）"""
        template = self.env.get_template("diagram.html.j2")

        date_str = date or (analysis.get("run_time", "") or "")[:10] or _today_jst()
        slot_label = SLOT_LABELS.get(slot, slot)

        top_articles = [self._normalize_article(a) for a in analysis.get("top_articles", [])[:5]]
        tracked_topics = [self._normalize_topic(t) for t in analysis.get("trend_evolution", {}).get("tracked_topics", [])]
        category_summaries = [self._normalize_category(c) for c in analysis.get("category_summaries", [])]
        x_trends = [self._normalize_x_trend(x) for x in analysis.get("x_trends", [])]

        return template.render(
            date=date_str,
            slot_label=slot_label,
            trend_summary=(analysis.get("trend_summary", "") or "").strip(),
            top_articles=top_articles,
            tracked_topics=tracked_topics,
            category_summaries=category_summaries,
            x_trends=x_trends,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            dashboard_url=dashboard_url,
        )

    def build_png(self, html: str, width: int = 900) -> bytes | None:
        """HTML → PNG 変換。Playwright 未インストール or 失敗時は None を返す。"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("playwright not installed — skipping PNG generation")
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    args=[
                        "--no-sandbox",
                        "--font-render-hinting=none",
                        "--disable-font-subpixel-positioning",
                        "--lang=ja-JP",
                    ],
                )
                context = browser.new_context(
                    viewport={"width": width, "height": 1200},
                    device_scale_factor=2,
                    locale="ja-JP",
                )
                page = context.new_page()
                page.set_content(html, wait_until="networkidle")
                png = page.screenshot(full_page=True, type="png")
                browser.close()
                return png
        except Exception as e:
            logger.error("PNG generation failed: %s", e)
            return None

    def build(
        self,
        analysis: dict,
        slot: str = "morning",
        date: str | None = None,
        dashboard_url: str = "",
        render_png: bool = True,
    ) -> tuple[str, bytes | None]:
        """HTML と PNG を一括生成 (PNG は Playwright 依存なので失敗可)"""
        html = self.build_html(analysis, slot=slot, date=date, dashboard_url=dashboard_url)
        png = self.build_png(html, width=900) if render_png else None
        return html, png

    # ── 正規化ヘルパ ─────────────────────────────────────────────

    @staticmethod
    def _normalize_article(a: dict) -> dict:
        cat = a.get("category", "")
        return {
            "rank": a.get("rank", 0),
            "title": (a.get("title", "") or "").strip(),
            "summary": (a.get("summary", "") or "").strip(),
            "category": cat,
            "category_class": CATEGORY_CLASS.get(cat, ""),
            "source_label": a.get("source_label", ""),
            "url": a.get("url", ""),
        }

    @staticmethod
    def _normalize_topic(t: dict) -> dict:
        status = t.get("status", "")
        return {
            "topic": (t.get("topic", "") or "").strip(),
            "status": status,
            "status_icon": STATUS_ICONS.get(status, "•"),
            "streak_days": t.get("streak_days", 0),
        }

    @staticmethod
    def _normalize_category(c: dict) -> dict:
        cat = c.get("category", "")
        return {
            "category": cat,
            "category_class": CATEGORY_CLASS.get(cat, ""),
            "count": c.get("count", 0),
            "summary": (c.get("summary", "") or "").strip(),
        }

    @staticmethod
    def _normalize_x_trend(x: dict) -> dict:
        buzz = x.get("buzz_level", "")
        return {
            "topic": (x.get("topic", "") or "").strip(),
            "description": (x.get("description", "") or "").strip(),
            "buzz_icon": BUZZ_ICONS.get(buzz, "🔥"),
        }


def _clip(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def _today_jst() -> str:
    import zoneinfo
    return datetime.now(zoneinfo.ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")

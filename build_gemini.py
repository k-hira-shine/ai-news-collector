"""Gemini機能追跡ページ — docs/gemini.html 生成"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from glob import glob
from html import escape
from zoneinfo import ZoneInfo

import yaml

from site_nav import NAV_CSS, render_nav

try:
    from gemini_collector import apply_status_guardrails
except ImportError:
    def apply_status_guardrails(item: dict) -> None:  # noqa: ARG001
        pass

logger = logging.getLogger("ai-news.build_gemini")

GEMINI_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "gemini")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "gemini.html")

STATUS_LABELS = {
    "available_now": ("今すぐ使える", "#10b981"),
    "coming_soon":   ("もうすぐ公開", "#f59e0b"),
    "deprecation":   ("停止予定", "#ef4444"),
    "unknown":       ("未分類", "#64748b"),
}

SOURCE_TYPE = {
    "x": ("𝕏", "#1d9bf0"),
    "rss": ("Web", "#34d399"),
    "scrape": ("Web", "#34d399"),
}


def _parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    dt: datetime | None = None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        pass
    if not dt:
        try:
            dt = parsedate_to_datetime(raw)
        except Exception:
            pass
    if not dt and len(raw) >= 10:
        try:
            dt = datetime.strptime(raw[:10], "%Y-%m-%d")
        except ValueError:
            pass
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _to_jst_datetime(raw: str, source: str = "") -> str:
    if not raw:
        return "日付不明"
    dt = _parse_date(raw)
    if not dt:
        return raw[:10] if len(raw) >= 10 else "日付不明"
    jst = dt.astimezone(ZoneInfo("Asia/Tokyo"))
    date_part = f"{jst.year}/{jst.month}/{jst.day}"
    has_time = "T" in raw or bool(re.search(r"\d:\d{2}", raw))
    if source == "x" and has_time:
        return f"{date_part} {jst.hour}:{jst.minute:02d}"
    if not has_time or source in ("rss", "scrape"):
        return date_part
    return f"{date_part} {jst.hour}:{jst.minute:02d}"


def _sort_key(item: dict) -> datetime:
    raw = item.get("published_at") or ""
    dt = _parse_date(raw)
    if dt:
        return dt
    return datetime.min.replace(tzinfo=ZoneInfo("UTC"))


def _sort_newest(items: list[dict]) -> list[dict]:
    return sorted(items, key=_sort_key, reverse=True)


def _load_config() -> dict:
    path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _filter_recent(items: list[dict], max_age_days: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    now = datetime.now(timezone.utc)
    result: list[dict] = []
    for item in items:
        raw = item.get("published_at") or ""
        dt = _parse_date(raw)
        if not dt or dt >= cutoff:
            if dt and dt > now:
                continue
            result.append(item)
    return result


def load_gemini_items(days: int = 14) -> list[dict]:
    if not os.path.isdir(GEMINI_DATA_DIR):
        return []
    files = sorted(glob(os.path.join(GEMINI_DATA_DIR, "*.jsonl")), reverse=True)
    items: list[dict] = []
    for fpath in files[:days]:
        with open(fpath, encoding="utf-8") as f:
            for line in f.read().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
    return items


def _dedupe_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for item in _sort_newest(items):
        key = item.get("url") or item.get("id") or ""
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _format_scheduled_date(raw: str) -> str:
    dt = _parse_date(raw)
    if not dt:
        return raw[:10] if len(raw) >= 10 else raw
    jst = dt.astimezone(ZoneInfo("Asia/Tokyo"))
    return f"{jst.year}/{jst.month}/{jst.day}"


def _scheduled_badge(item: dict) -> str:
    sd = (item.get("scheduled_date") or "").strip()
    if not sd:
        return ""
    status = item.get("status") or ""
    formatted = _format_scheduled_date(sd)
    if status == "coming_soon":
        label = f"予定: {formatted}"
        color = "#f59e0b"
    elif status == "deprecation":
        label = f"停止予定: {formatted}"
        color = "#ef4444"
    else:
        return ""
    return f'<span class="scheduled-badge" style="color:{color};border-color:{color}">{escape(label)}</span>'


def _source_type_badge(item: dict) -> str:
    src = item.get("source") or ""
    type_label, color = SOURCE_TYPE.get(src, ("その他", "#64748b"))
    return f'<span class="source-type" style="background:{color}22;color:{color}">{type_label}</span>'


def _card(item: dict) -> str:
    apply_status_guardrails(item)
    status = item.get("status") or "unknown"
    label, color = STATUS_LABELS.get(status, STATUS_LABELS["unknown"])
    raw_summary = item.get("summary_ja") or ""
    display_title = escape(
        item.get("title_ja") or item.get("summary_ja") or item.get("title") or ""
    )
    summary = escape(raw_summary)
    source_label = escape(item.get("source_label") or "")
    url = escape(item.get("url") or "#")
    date = _to_jst_datetime(item.get("published_at") or "", item.get("source") or "")
    scheduled = _scheduled_badge(item)
    source_detail = f'<span class="source-detail">{source_label}</span>' if source_label else ""
    summary_html = (
        f'<p class="card-summary">{summary}</p>'
        if raw_summary and raw_summary != (item.get("title_ja") or item.get("title") or "")
        else (f'<p class="card-summary">{summary}</p>' if raw_summary else "")
    )

    return f"""<article class="gemini-card" data-status="{escape(status)}">
  <div class="card-meta">
    <span class="status-badge" style="border-color:{color};color:{color}">{label}</span>
    {_source_type_badge(item)}
    {source_detail}
    {scheduled}
    <span class="date-badge">{date}</span>
  </div>
  <h3 class="card-title"><a href="{url}" target="_blank" rel="noopener">{display_title}</a></h3>
  {summary_html}
</article>"""


def _section(title: str, subtitle: str, items: list[dict], empty_msg: str, *, open_default: bool = True) -> str:
    if not items:
        body = f'<div class="empty-state"><p>{escape(empty_msg)}</p></div>'
    else:
        cards = "\n".join(_card(i) for i in items)
        body = f'<div class="gemini-list">{cards}</div>'
    open_attr = " open" if open_default else ""
    return f"""<details class="gemini-section"{open_attr}>
  <summary class="section-toggle">
    <span class="section-head">
      <span class="section-title">{escape(title)}</span>
      <span class="section-desc">{escape(subtitle)}</span>
    </span>
    <span class="count">{len(items)}件</span>
  </summary>
  <div class="section-body">{body}</div>
</details>"""


def _sources_section(items: list[dict]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        label = item.get("source_label") or item.get("source") or "unknown"
        counts[label] = counts.get(label, 0) + 1
    rows = "".join(
        f"<li><strong>{escape(label)}</strong>: {count}件</li>"
        for label, count in sorted(counts.items(), key=lambda x: -x[1])
    )
    return f"""<section class="gemini-section sources-section">
  <h2>チェックした情報源</h2>
  <ul class="sources-list">{rows or '<li>データなし</li>'}</ul>
</section>"""


def build_gemini_page(output_path: str = OUTPUT_PATH) -> None:
    config = _load_config()
    max_age_days = int(config.get("gemini_collection", {}).get("max_age_days", 7))
    items = _filter_recent(_dedupe_items(load_gemini_items(days=14)), max_age_days)
    now_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M JST")

    available = _sort_newest([i for i in items if i.get("status") == "available_now"])
    coming = _sort_newest([i for i in items if i.get("status") == "coming_soon"])
    deprecation = _sort_newest([i for i in items if i.get("status") == "deprecation"])
    unknown = _sort_newest([i for i in items if i.get("status") == "unknown"])
    visible = len(available) + len(coming) + len(deprecation)

    nav_html = render_nav("gemini.html")

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gemini 機能トラッカー</title>
<style>
:root {{
  --bg: #0f1419; --card: #1a2236; --border: #2d3748;
  --text: #e2e8f0; --muted: #94a3b8; --accent: #4285f4;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; padding-top: 48px; }}
{NAV_CSS}
header {{ padding: 24px 20px 12px; border-bottom: 1px solid var(--border); }}
header h1 {{ font-size: 1.4rem; color: var(--text); }}
header .meta {{ color: var(--muted); font-size: 0.85rem; margin-top: 6px; }}
.container {{ max-width: 1100px; margin: 0 auto; padding: 20px 16px 40px; }}
.gemini-section {{ margin-bottom: 16px; border: 1px solid var(--border); border-radius: 10px; background: rgba(26,34,54,0.45); overflow: hidden; }}
.section-toggle {{ cursor: pointer; padding: 12px 16px; list-style: none; display: flex; align-items: center; gap: 12px; user-select: none; }}
.section-toggle::-webkit-details-marker {{ display: none; }}
.section-toggle::before {{ content: '▶'; font-size: 0.65rem; color: var(--muted); transition: transform 0.15s; flex-shrink: 0; margin-top: 2px; }}
.gemini-section[open] > .section-toggle::before {{ transform: rotate(90deg); }}
.section-head {{ display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; }}
.section-title {{ font-size: 1.05rem; font-weight: 600; color: var(--text); line-height: 1.35; }}
.section-desc {{ font-size: 0.78rem; color: var(--muted); font-weight: normal; line-height: 1.4; }}
.section-toggle .count {{ font-size: 0.85rem; color: var(--muted); font-weight: normal; flex-shrink: 0; white-space: nowrap; }}
.section-body {{ padding: 0 16px 16px; }}
.gemini-list {{ display: flex; flex-direction: column; gap: 10px; }}
.gemini-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 18px; }}
.card-meta {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 6px; font-size: 0.78rem; }}
.status-badge {{ font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 10px; border: 1px solid; flex-shrink: 0; }}
.source-type {{ font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 6px; flex-shrink: 0; }}
.source-detail {{ color: var(--muted); }}
.date-badge {{ color: var(--muted); margin-left: auto; flex-shrink: 0; }}
.scheduled-badge {{ font-size: 0.72rem; font-weight: 600; padding: 2px 8px; border-radius: 10px; border: 1px solid; flex-shrink: 0; }}
.card-title {{ font-size: 1rem; margin-bottom: 4px; line-height: 1.45; }}
.card-title a {{ color: var(--text); text-decoration: none; }}
.card-title a:hover {{ color: var(--accent); }}
.card-summary {{ font-size: 0.88rem; color: #cbd5e1; line-height: 1.6; }}
.empty-state {{ text-align: center; padding: 40px 20px; color: var(--muted); background: var(--card); border-radius: 10px; border: 1px dashed var(--border); }}
.sources-list {{ list-style: none; background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 20px; }}
.sources-list li {{ padding: 4px 0; font-size: 0.85rem; color: var(--muted); }}
footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 24px; border-top: 1px solid var(--border); }}
@media (max-width: 640px) {{
  .card-meta {{ gap: 6px; }}
  .date-badge {{ margin-left: 0; width: 100%; }}
}}
</style>
</head>
<body>
{nav_html}
<header>
  <h1>✨ Gemini 機能トラッカー</h1>
  <p class="meta">Last updated: {now_str} ｜ 収集 {len(items)}件（表示 {visible} / 未分類 {len(unknown)}）｜ 今すぐ {len(available)} / もうすぐ {len(coming)} / 停止予定 {len(deprecation)}</p>
</header>
<div class="container">
{_section("もうすぐ使えるようになる", "Googleが「近日公開」と告知した機能（予定日が分かればカードに表示）", coming, "直近1週間で「近日公開」と判定された情報はまだありません。")}
{_section("今すぐ使える", "すでに公開済みで、今試せる機能", available, "直近1週間で「利用可能」と判定された情報はまだありません。")}
{_section("廃止・停止予定", "モデル停止やDeprecationの告知", deprecation, "直近1週間で停止予定の告知はまだありません。")}
{_section("その他（未分類）", "自動分類できなかった情報", unknown, "未分類の情報はありません。", open_default=False)}
{_sources_section(items)}
</div>
<footer>Gemini公式RSS・Release Notes・API Changelog・公式Xアカウントを毎日自動チェック</footer>
</body>
</html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("Built Gemini page → %s (%d items)", output_path, len(items))


def build() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    build_gemini_page()


if __name__ == "__main__":
    build()

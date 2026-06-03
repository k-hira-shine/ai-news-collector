"""収集障害の状況・原因・影響を pages 用 HTML / run_status.json に載せる

組み込みルール（再発防止: .cursor/docs/incident-display-css-leak.md）:
- INCIDENT_CSS → 必ず既存の <style> ブロック内（<head>）
- INCIDENT_BODY_HTML → ナビ直後など body 内（マウント + JS のみ）
- STATUS_BANNER_HTML / INCIDENT_CLIENT_HTML → </body> 直前への一括挿入用（<style> 付き）
- INCIDENT_CSS を body 末尾や footer 後にそのまま連結しない
"""

from __future__ import annotations

import json
import os
import re
from html import escape
from typing import Any


def _run_status_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "run_status.json")


def latest_diagram_label() -> str:
    diagrams_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "diagrams")
    if not os.path.isdir(diagrams_dir):
        return ""
    names = [f for f in os.listdir(diagrams_dir) if f.endswith(".html")]
    if not names:
        return ""
    names.sort(reverse=True)
    return names[0].replace(".html", "")


def _active_incident(inc: dict | None) -> bool:
    return bool(inc) and inc.get("active") in (True, "true", "1", 1)


def build_collect_incident(stats: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, str] | None:
    """collect stats からインシデントを組み立て（異常検知 + サイレント失敗）"""
    cfg = config or stats.get("_config") or {}
    anomalies = stats.get("anomalies")
    if anomalies is None and cfg:
        from alerts import detect_anomalies

        anomalies = detect_anomalies(stats, cfg)
    anomalies = anomalies or []

    x_meta = stats.get("x_meta") or {}
    analysis_meta = stats.get("analysis_meta") or {}
    diagram_meta = stats.get("diagram_meta") or {}
    hints = x_meta.get("apify_failure_hints") or []
    search_detail = (x_meta.get("search_failure_detail") or "").strip()
    top_count = analysis_meta.get("top_articles_count")
    if top_count is None:
        top_count = stats.get("top_articles_count", 0)
    diagrams = stats.get("_diagram_latest_label") or latest_diagram_label()
    x_valid = x_meta.get("x_valid_count")
    collected = stats.get("total", 0)
    apify_runs = x_meta.get("apify_runs", 0) or stats.get("apify_runs", 0)

    silent_failure = (
        apify_runs > 0
        and (x_valid == 0 or (collected <= 1 and top_count == 0))
        and (hints or search_detail or top_count == 0)
    )

    if not anomalies and not silent_failure:
        return None

    critical_titles = [a["title"] for a in anomalies if a.get("severity") == "critical"]
    has_x_api = "x_api_unavailable" in hints or "x_api_unavailable" in search_detail

    if has_x_api or (x_valid == 0 and apify_runs > 0):
        title = "X 収集が停止中（上流 API 障害）"
        situation = (
            f"直近の収集で有効な X ツイートが {x_valid if x_valid is not None else 0} 件。"
            " Apify Actor は成功終了していますが、データは取得できていません。"
        )
        cause = (
            "Apify Actor（xquik/x-tweet-scraper）が利用する xquik の X 検索 API が "
            "502 / 503 x_api_unavailable を返しています。"
            " Cookie 失効や設定ミスではなく、データ源側の一時障害です。"
        )
        if search_detail:
            cause += f" 詳細: {search_detail[:200]}"
        impact = (
            "・分析の top_articles が 0 件のため、新しい図解 HTML/PNG は生成されません\n"
            "・サイトの「最新図解」リンクが前回便のまま残ります\n"
            "・ニュース一覧の内容も更新されません\n"
            "・復旧後: probe_x_upstream.py で OK → collect（full）再実行"
        )
        severity = "critical"
    elif (top_count == 0 and not diagram_meta.get("attempted")) or (
        top_count == 0 and apify_runs > 0 and collected <= 5
    ):
        title = "図解・掲載記事が更新されていません"
        situation = f"収集 {collected} 件のあと掲載記事 {top_count} 件。図解は生成されていません。"
        cause = " / ".join(critical_titles[:3]) or "分析で記事が選定されなかったか、収集データが空に近い状態です。"
        if hints:
            cause += f" 検出: {', '.join(hints)}"
        impact = (
            "・最新図解・ニュースタブが古いまま\n"
            "・GitHub Actions は success 表示のまま終わることがあります"
        )
        severity = "critical"
    elif anomalies:
        title = critical_titles[0] if critical_titles else "収集パイプラインに警告"
        situation = f"健全性アラート {len(anomalies)} 件。収集 {collected} 件 / top_articles {top_count} 件。"
        cause = "; ".join(a["title"] for a in anomalies[:5])
        detail_parts = [a.get("detail", "")[:120] for a in anomalies[:2] if a.get("detail")]
        if detail_parts:
            cause += " — " + " / ".join(detail_parts)
        impact = "一部の更新・品質が劣化している可能性があります。下記の状況・原因を確認してください。"
        severity = "warning" if not critical_titles else "critical"
    else:
        return None

    technical_parts = []
    if hints:
        technical_parts.append("hints=" + ", ".join(hints))
    if search_detail:
        technical_parts.append(search_detail[:180])
    if x_meta.get("must_follow_failure_detail"):
        technical_parts.append(str(x_meta["must_follow_failure_detail"])[:120])

    return {
        "active": "true",
        "severity": severity,
        "title": title,
        "situation": situation,
        "cause": cause,
        "impact": impact.strip(),
        "technical": " / ".join(technical_parts) or "; ".join(critical_titles),
        "diagram_latest": diagrams,
    }


def build_workflow_incident(
    workflow: str,
    *,
    status: str,
    error: str = "",
    extra: dict | None = None,
) -> dict[str, str] | None:
    if status == "success":
        return None
    extra = extra or {}
    title = error.strip() or f"{workflow} が {status} で終了"
    return {
        "active": "true",
        "severity": "critical" if status == "error" else "warning",
        "title": title[:120],
        "situation": f"ワークフロー「{workflow}」の直近実行が {status} です。",
        "cause": title,
        "impact": "該当ページのデータが更新されない、または内容が古いままになる可能性があります。",
        "technical": json.dumps({k: v for k, v in extra.items() if k in (
            "mode", "items_collected", "top_articles", "apify_hints", "search_failure"
        )}, ensure_ascii=False)[:300],
        "diagram_latest": latest_diagram_label(),
    }


def resolve_incident_for_write(
    workflow: str,
    status: str,
    *,
    error: str = "",
    extra: dict | None = None,
    stats: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    explicit: dict[str, str] | None = None,
    existing: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """write_run_status 用: 明示 incident > collect 自動検知 > 汎用 > 既存維持"""
    if explicit:
        return explicit

    if workflow == "collect" and stats is not None:
        inc = build_collect_incident(stats, config)
        if inc:
            return inc

    if status != "success":
        generic = build_workflow_incident(workflow, status=status, error=error, extra=extra)
        if generic:
            if existing and existing.get("severity") == "critical" and generic.get("severity") != "critical":
                return existing
            return generic

    if _active_incident(existing):
        return existing

    return None


def load_active_incident() -> dict[str, str] | None:
    path = _run_status_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    inc = data.get("incident")
    if not _active_incident(inc):
        return None
    return inc


def merge_incident_into_run_status(
    existing: dict,
    *,
    incident: dict[str, str] | None,
    clear_on_success: bool,
    workflow: str,
    status: str,
) -> dict:
    if incident:
        existing["incident"] = {
            **incident,
            "workflow": incident.get("workflow") or workflow,
        }
    elif clear_on_success and workflow == "collect" and status == "success":
        existing.pop("incident", None)
    return existing


def render_incident_section_html(incident: dict[str, str] | None) -> str:
    if not incident:
        return ""
    return _incident_card_html(incident)


def _incident_card_html(incident: dict[str, str]) -> str:
    sev = incident.get("severity", "warning")
    border = "#f87171" if sev == "critical" else "#fbbf24"
    bg = "rgba(248,113,113,0.12)" if sev == "critical" else "rgba(251,191,36,0.12)"
    icon = "🚨" if sev == "critical" else "⚠️"
    title = escape(incident.get("title", "障害情報"))
    situation = escape(incident.get("situation", ""))
    cause = escape(incident.get("cause", ""))
    impact = escape(incident.get("impact", "")).replace("\n", "<br>")
    technical = escape(incident.get("technical", ""))
    updated = escape(incident.get("updated_at", ""))
    diagram = escape(incident.get("diagram_latest", ""))
    diagram_line = ""
    if diagram:
        diagram_line = (
            f'<p class="incident-meta">表示中の最新図解: <strong>{diagram}</strong>'
            "（障害中は更新されない場合があります）</p>"
        )
    return f"""
<div class="incident-card" role="alert" style="--inc-border:{border};--inc-bg:{bg}">
  <div class="incident-head">
    <span class="incident-icon">{icon}</span>
    <h2 class="incident-title">{title}</h2>
  </div>
  <dl class="incident-dl">
    <dt>状況</dt><dd>{situation}</dd>
    <dt>原因</dt><dd>{cause}</dd>
    <dt>影響</dt><dd>{impact}</dd>
  </dl>
  {diagram_line}
  <p class="incident-tech"><span>技術メモ:</span> {technical}</p>
  <p class="incident-meta">記録: {updated}</p>
</div>
"""


INCIDENT_CSS = """
.incident-mount-wrap { max-width: 960px; margin: 52px auto 0; padding: 0 1rem; width: 100%; box-sizing: border-box; }
.incident-card { background: var(--inc-bg, rgba(248,113,113,0.12)); border: 1px solid var(--inc-border, #f87171); border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 1rem; }
.incident-head { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; }
.incident-icon { font-size: 1.25rem; }
.incident-title { font-size: 1.05rem; color: var(--inc-border, #f87171); margin: 0; }
.incident-dl { margin: 0; font-size: 0.9rem; }
.incident-dl dt { font-weight: 700; color: var(--text, #e2e8f0); margin-top: 0.65rem; }
.incident-dl dt:first-of-type { margin-top: 0; }
.incident-dl dd { margin: 0.2rem 0 0 0; color: var(--muted, #94a3b8); line-height: 1.55; }
.incident-tech { font-size: 0.78rem; color: var(--muted, #94a3b8); margin: 0.75rem 0 0; word-break: break-word; }
.incident-tech span { font-weight: 600; color: var(--text, #e2e8f0); }
.incident-meta { font-size: 0.75rem; color: var(--muted, #94a3b8); margin: 0.35rem 0 0; }
"""

INCIDENT_BODY_HTML = """
<div id="incidentMount" class="incident-mount-wrap" style="display:none" aria-live="polite"></div>
<script>
(function() {
  function esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function cardHtml(inc) {
    var sev = inc.severity === 'critical';
    var border = sev ? '#f87171' : '#fbbf24';
    var bg = sev ? 'rgba(248,113,113,0.12)' : 'rgba(251,191,36,0.12)';
    var icon = sev ? '🚨' : '⚠️';
    var impact = esc(inc.impact).replace(/\\n/g, '<br>');
    var diagram = inc.diagram_latest
      ? '<p class="incident-meta">表示中の最新図解: <strong>' + esc(inc.diagram_latest) + '</strong></p>' : '';
    return '<div class="incident-card" role="alert" style="--inc-border:' + border + ';--inc-bg:' + bg + '">'
      + '<div class="incident-head"><span class="incident-icon">' + icon + '</span>'
      + '<h2 class="incident-title">' + esc(inc.title) + '</h2></div>'
      + '<dl class="incident-dl"><dt>状況</dt><dd>' + esc(inc.situation) + '</dd>'
      + '<dt>原因</dt><dd>' + esc(inc.cause) + '</dd>'
      + '<dt>影響</dt><dd>' + impact + '</dd></dl>' + diagram
      + '<p class="incident-tech"><span>技術メモ:</span> ' + esc(inc.technical) + '</p>'
      + '<p class="incident-meta">記録: ' + esc(inc.updated_at) + '</p></div>';
  }
  function fallbackIncident(data) {
    var bad = Object.entries(data.workflows || {}).filter(function(e) { return e[1].status !== 'success'; });
    if (!bad.length) return null;
    var lines = bad.map(function(e) { return e[0] + ': ' + (e[1].error || e[1].status); });
    return {
      active: true, severity: data.overall === 'error' ? 'critical' : 'warning',
      title: lines[0].slice(0, 120),
      situation: '直近の自動実行で warning / error が記録されています。',
      cause: lines.join(' / '),
      impact: '該当機能の更新が止まっている可能性があります。詳細はログを確認してください。',
      technical: '', updated_at: data.updated_at || ''
    };
  }
  fetch('run_status.json?_=' + Date.now())
    .then(function(r) { return r.ok ? r.json() : null; })
    .catch(function() { return null; })
    .then(function(data) {
      if (!data) return;
      var mount = document.getElementById('incidentMount');
      var inc = data.incident;
      if (!inc || !inc.active) {
        if (data.overall !== 'success') inc = fallbackIncident(data);
      }
      if (inc && (inc.active === true || inc.active === 'true' || inc.active === 1)) {
        if (mount) {
          mount.innerHTML = cardHtml(inc);
          mount.style.display = 'block';
        }
      }
    });
})();
</script>
"""

INCIDENT_CLIENT_HTML = (
    "<style>\n" + INCIDENT_CSS.strip() + "\n</style>\n" + INCIDENT_BODY_HTML.strip() + "\n"
)

# utils 互換
STATUS_BANNER_HTML = INCIDENT_CLIENT_HTML

_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
_INCIDENT_CSS_MARKER = ".incident-mount-wrap {"
_LEAKED_CSS_BLOCK_RE = re.compile(
    r"\n\.incident-mount-wrap \{.*?(?=\n<div id=\"incidentMount\")",
    re.DOTALL,
)
_RUN_STATUS_BANNER_HTML_RE = re.compile(
    r'<div id="runStatusBanner"[^>]*>\s*<div id="runStatusInner"[^>]*>.*?</div>\s*</div>\s*',
    re.DOTALL,
)
_RUN_STATUS_BANNER_JS_RE = re.compile(
    r"\s*(?:var|const) banner = document\.getElementById\('runStatusBanner'\);"
    r".*?banner\.style\.display = 'block';\n",
    re.DOTALL,
)


def _html_without_style_blocks(content: str) -> str:
    return _STYLE_BLOCK_RE.sub("", content)


def _incident_css_outside_style(content: str) -> bool:
    return _INCIDENT_CSS_MARKER in _html_without_style_blocks(content)


def find_leaked_incident_css_files(docs_dir: str | None = None) -> list[str]:
    """<style> 外に漏れた incident CSS がある HTML のファイル名一覧"""
    docs_dir = docs_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
    leaked: list[str] = []
    for fname in os.listdir(docs_dir):
        if not fname.endswith(".html"):
            continue
        path = os.path.join(docs_dir, fname)
        with open(path, encoding="utf-8") as f:
            if _incident_css_outside_style(f.read()):
                leaked.append(fname)
    return leaked


def remove_run_status_banner_from_docs(docs_dir: str | None = None) -> int:
    """右下固定トースト runStatusBanner を docs/*.html から除去"""
    docs_dir = docs_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
    fixed = 0
    for fname in os.listdir(docs_dir):
        if not fname.endswith(".html"):
            continue
        path = os.path.join(docs_dir, fname)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if 'id="runStatusBanner"' not in content:
            continue
        new_content, n1 = _RUN_STATUS_BANNER_HTML_RE.subn("", content)
        new_content, n2 = _RUN_STATUS_BANNER_JS_RE.subn("", new_content)
        if n1 or n2:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            fixed += 1
    return fixed


def repair_leaked_incident_css_in_docs(docs_dir: str | None = None) -> int:
    """<style> 外に漏れた incident 用 CSS テキストを除去"""
    docs_dir = docs_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
    fixed = 0
    for fname in os.listdir(docs_dir):
        if not fname.endswith(".html"):
            continue
        path = os.path.join(docs_dir, fname)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if not _incident_css_outside_style(content):
            continue
        new_content, n = _LEAKED_CSS_BLOCK_RE.subn("\n", content)
        if n:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            fixed += 1
    return fixed


def sync_status_scripts_in_docs(docs_dir: str | None = None) -> int:
    """docs/*.html に incident クライアントを未挿入なら </body> 直前に追加"""
    docs_dir = docs_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
    repair_leaked_incident_css_in_docs(docs_dir)
    remove_run_status_banner_from_docs(docs_dir)
    marker = 'id="incidentMount"'
    updated_count = 0
    for fname in os.listdir(docs_dir):
        if not fname.endswith(".html"):
            continue
        path = os.path.join(docs_dir, fname)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if marker in content:
            continue
        if "</body>" not in content:
            continue
        content = content.replace("</body>", INCIDENT_CLIENT_HTML + "\n</body>", 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        updated_count += 1
    return updated_count

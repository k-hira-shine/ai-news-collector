#!/usr/bin/env python3
"""run_status.json に障害情報を載せ、index / home を再生成する（収集なし）"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from incident_status import _run_status_path, latest_diagram_label

JST = zoneinfo.ZoneInfo("Asia/Tokyo")


def main() -> int:
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    diagram = latest_diagram_label()

    incident = {
        "active": True,
        "severity": "critical",
        "workflow": "collect",
        "title": "X 収集が停止中（上流 API 障害）",
        "situation": (
            "2026-06-04 朝便の収集で X ツイートが実質 0 件。"
            " 直近の能動プローブ（from:OpenAI・3件）も 0 件でした。"
        ),
        "cause": (
            "xquik の X 検索 API が 502 → 503 x_api_unavailable を返しています。"
            " Apify Actor は SUCCEEDED ですがデータは取れません。Cookie/設定の問題ではありません。"
        ),
        "impact": (
            "・新しい図解 HTML/PNG は生成されません\n"
            "・「最新図解」リンクが前回便のまま残ります\n"
            "・ニュース分析の更新が止まります\n"
            "・復旧後: probe_x_upstream.py で OK 確認 → collect full 再実行"
        ),
        "technical": "x_api_unavailable, http_502, zero-output-run",
        "diagram_latest": diagram,
        "updated_at": now,
    }

    path = _run_status_path()
    data: dict = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

    data["overall"] = "warning"
    data["updated_at"] = now
    data["incident"] = incident
    collect_wf = data.setdefault("workflows", {}).setdefault("collect", {})
    collect_wf["status"] = "warning"
    collect_wf["error"] = incident["title"]
    collect_wf["time"] = now

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    from build_home import build_home_page
    from dashboard import generate_dashboard
    from incident_status import sync_status_scripts_in_docs

    docs = os.path.join(ROOT, "docs")
    generate_dashboard(os.path.join(docs, "index.html"))
    build_home_page(os.path.join(docs, "home.html"))
    sync_status_scripts_in_docs(docs)
    print(f"Published incident → {path}")
    print(f"Regenerated index.html, home.html (diagram_latest={diagram})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

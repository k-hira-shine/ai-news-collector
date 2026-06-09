"""Stage1フィルタを Pro と Flash の両方で実行し、判定一致率を比較する。

G3（1次フィルタの Pro→Flash 化）の事前検証。直近の保存済み収集データ
（data/hn の HN/arxiv 記事）を共通入力として両モデルに与え、
選別結果・重要度スコア・カテゴリの一致を測る。

実行には GEMINI_API_KEY が必要（CI: verify-stage1-flash.yml から実行）。
結果は data/stage1_flash_verification.json へ保存。
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from analyzer import NewsAnalyzer  # noqa: E402

OUTPUT = BASE / "data" / "stage1_flash_verification.json"
MAX_ITEMS = 120
JST = timezone(timedelta(hours=9))


def load_items() -> list[dict]:
    files = sorted((BASE / "data" / "hn").glob("*.jsonl"))[-3:]
    seen: set[str] = set()
    items: list[dict] = []
    for path in reversed(files):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            item_id = item.get("id")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            items.append(item)
    return items[:MAX_ITEMS]


def run_stage1(items: list[dict], model: str) -> list[dict]:
    config = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    analyzer = NewsAnalyzer(config)
    analyzer.models = dict(analyzer.models)
    analyzer.models["stage1_filter"] = model
    # 比較を汚さないよう、別モデルへのフォールバックを無効化
    analyzer.models["fallback"] = model
    return analyzer._stage1_filter(items)


def compare(pro: list[dict], flash: list[dict]) -> dict:
    pro_by_id = {r["id"]: r for r in pro if r.get("id")}
    flash_by_id = {r["id"]: r for r in flash if r.get("id")}
    pro_ids, flash_ids = set(pro_by_id), set(flash_by_id)
    common = pro_ids & flash_ids
    union = pro_ids | flash_ids

    score_diffs = []
    category_match = 0
    for item_id in common:
        p, f = pro_by_id[item_id], flash_by_id[item_id]
        score_diffs.append(
            abs(float(p.get("importance_score") or 0) - float(f.get("importance_score") or 0))
        )
        if (p.get("category") or "") == (f.get("category") or ""):
            category_match += 1

    def top_ids(rows: list[dict], n: int = 30) -> set[str]:
        ranked = sorted(rows, key=lambda r: float(r.get("importance_score") or 0), reverse=True)
        return {r["id"] for r in ranked[:n] if r.get("id")}

    top_pro, top_flash = top_ids(pro), top_ids(flash)
    return {
        "pro_selected": len(pro_ids),
        "flash_selected": len(flash_ids),
        "selection_jaccard": round(len(common) / len(union), 3) if union else 0.0,
        "common_count": len(common),
        "avg_importance_diff": round(sum(score_diffs) / len(score_diffs), 2) if score_diffs else None,
        "category_agreement": round(category_match / len(common), 3) if common else None,
        "top30_overlap": round(
            len(top_pro & top_flash) / max(len(top_pro | top_flash), 1), 3
        ),
    }


def main() -> None:
    items = load_items()
    if len(items) < 30:
        print(f"検証に十分なデータがありません（{len(items)}件）")
        sys.exit(1)
    print(f"入力: {len(items)}件（data/hn 直近3日分）")

    print("Pro で Stage1 実行中…")
    pro = run_stage1(items, "gemini-2.5-pro")
    time.sleep(15)
    print("Flash で Stage1 実行中…")
    flash = run_stage1(items, "gemini-2.5-flash")

    metrics = compare(pro, flash)
    result = {
        "verified_at": datetime.now(JST).isoformat(timespec="seconds"),
        "input_items": len(items),
        "metrics": metrics,
        "note": "selection_jaccard/top30_overlap が 0.8 以上、category_agreement 0.85 以上なら Flash 化を可とする目安",
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

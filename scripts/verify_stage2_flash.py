"""Stage2/3 を Pro と Flash の両方で実行し、出力一致率を比較する。

stage2/3（深層分析・施策提案）の Pro→Flash 化の事前検証。
直近の収集データに本番同様の stage1（Flash）を一度だけ適用し、
その同一の top_items を両モデルの stage2 に与えて比較する。
stage3 は同一の stage2 結果（MODEL_A 側）を入力に両モデルで実行し、
定量比較が難しいため出力を併記保存して目視判断する。

実行には GEMINI_API_KEY が必要（CI: verify-stage2-flash.yml から実行）。
結果は data/stage2_verification_{A}_vs_{B}.json へ保存。
"""

import copy
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from analyzer import NewsAnalyzer  # noqa: E402

# MODEL_A/MODEL_B を同一にすれば「同一モデルの実行揺らぎ」の基準が取れる
MODEL_A = os.environ.get("MODEL_A", "gemini-2.5-pro")
MODEL_B = os.environ.get("MODEL_B", "gemini-2.5-flash")
OUTPUT = BASE / "data" / f"stage2_verification_{MODEL_A}_vs_{MODEL_B}.json"
JST = timezone(timedelta(hours=9))


def load_items() -> list[dict]:
    files = sorted((BASE / "data" / "daily").glob("*.jsonl"))[-2:]
    seen: set[str] = set()
    items: list[dict] = []
    for path in reversed(files):
        for line in path.read_text(encoding="utf-8").split("\n"):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            item_id = item.get("id")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            items.append(item)
    return items


def make_analyzer(stage2_model: str | None = None) -> NewsAnalyzer:
    config = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    analyzer = NewsAnalyzer(config)
    analyzer.models = dict(analyzer.models)
    if stage2_model:
        analyzer.models["stage2_analysis"] = stage2_model
        # 比較を汚さないよう、別モデルへのフォールバックを無効化
        analyzer.models["fallback"] = stage2_model
    return analyzer


def rank_correlation(a_arts: list[dict], b_arts: list[dict]) -> float | None:
    """共通記事の rank に対する Spearman 相関"""
    a_rank = {x.get("id"): i for i, x in enumerate(a_arts) if x.get("id")}
    b_rank = {x.get("id"): i for i, x in enumerate(b_arts) if x.get("id")}
    common = sorted(set(a_rank) & set(b_rank))
    n = len(common)
    if n < 3:
        return None
    d2 = sum((a_rank[c] - b_rank[c]) ** 2 for c in common)
    return round(1 - (6 * d2) / (n * (n**2 - 1)), 3)


def compare(result_a: dict, result_b: dict) -> dict:
    a_arts = result_a.get("top_articles", [])
    b_arts = result_b.get("top_articles", [])
    a_ids = {x.get("id") for x in a_arts if x.get("id")}
    b_ids = {x.get("id") for x in b_arts if x.get("id")}
    common = a_ids & b_ids
    union = a_ids | b_ids

    a_by_id = {x.get("id"): x for x in a_arts}
    b_by_id = {x.get("id"): x for x in b_arts}
    category_match = sum(
        1 for c in common
        if (a_by_id[c].get("category") or "") == (b_by_id[c].get("category") or "")
    )

    return {
        "a_top_articles": len(a_arts),
        "b_top_articles": len(b_arts),
        "selection_jaccard": round(len(common) / len(union), 3) if union else 0.0,
        "common_count": len(common),
        "category_agreement": round(category_match / len(common), 3) if common else None,
        "rank_correlation": rank_correlation(a_arts, b_arts),
        "a_x_trends": len(result_a.get("x_trends", [])),
        "b_x_trends": len(result_b.get("x_trends", [])),
        "a_tracked_topics": [t.get("topic") for t in (result_a.get("trend_evolution") or {}).get("tracked_topics", [])],
        "b_tracked_topics": [t.get("topic") for t in (result_b.get("trend_evolution") or {}).get("tracked_topics", [])],
    }


def main() -> None:
    items = load_items()
    if len(items) < 30:
        print(f"検証に十分なデータがありません（{len(items)}件）")
        sys.exit(1)
    print(f"入力: {len(items)}件（data/daily 直近2日分）")

    # 本番同様の stage1（共通入力をつくるため一度だけ実行）
    base = make_analyzer()
    items_by_id = {it["id"]: it for it in items}
    scored = base._stage1_filter(items)
    scored = base._apply_bonuses(scored, items_by_id)
    scored.sort(key=lambda x: x["final_score"], reverse=True)
    top_items = scored[: base.stage1_top_n]
    recent = base._load_recent_analyses(count=5)
    print(f"Stage1 完了: {len(items)} → {len(top_items)}件")

    time.sleep(15)
    print(f"{MODEL_A} で Stage2 実行中…")
    analyzer_a = make_analyzer(MODEL_A)
    result_a = analyzer_a._stage2_analyze(
        copy.deepcopy(top_items), items_by_id, copy.deepcopy(recent)
    )
    time.sleep(15)
    print(f"{MODEL_B} で Stage2 実行中…")
    analyzer_b = make_analyzer(MODEL_B)
    result_b = analyzer_b._stage2_analyze(
        copy.deepcopy(top_items), items_by_id, copy.deepcopy(recent)
    )

    metrics = compare(result_a, result_b)

    # Stage3 は同一入力（MODEL_A の stage2 結果）で両モデル実行し目視比較する
    time.sleep(15)
    print(f"{MODEL_A} で Stage3 実行中…")
    strategy_a = analyzer_a._stage3_strategy(copy.deepcopy(result_a))
    time.sleep(15)
    print(f"{MODEL_B} で Stage3 実行中…")
    strategy_b = analyzer_b._stage3_strategy(copy.deepcopy(result_a))

    result = {
        "verified_at": datetime.now(JST).isoformat(timespec="seconds"),
        "model_a": MODEL_A,
        "model_b": MODEL_B,
        "input_items": len(items),
        "stage1_top_items": len(top_items),
        "metrics": metrics,
        "note": (
            "selection_jaccard >= 0.8、category_agreement >= 0.85、"
            "rank_correlation >= 0.7 なら Flash 化を可とする目安。"
            "trend_summary/x_trends/stage3 は raw_outputs を目視比較する。"
            "同一モデル同士の実行で揺らぎの基準値が取れる"
        ),
        "raw_outputs": {
            "a_trend_summary": result_a.get("trend_summary"),
            "b_trend_summary": result_b.get("trend_summary"),
            "a_x_trends": result_a.get("x_trends"),
            "b_x_trends": result_b.get("x_trends"),
            "a_strategy": strategy_a,
            "b_strategy": strategy_b,
        },
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "raw_outputs"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

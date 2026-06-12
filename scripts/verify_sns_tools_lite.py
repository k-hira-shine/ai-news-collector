"""SNS/Tools分析を Flash と Flash-Lite の両方で実行し、判定一致率を比較する。

sns_analyzer / tools_analyzer（価値判定・選別タスク）の Flash→Flash-Lite 化の
事前検証。直近の保存済み生データを共通入力として両モデルに与え、
選別結果とカテゴリの一致を測る。

実行には GEMINI_API_KEY が必要（CI: verify-sns-tools-lite.yml から実行）。
結果は data/sns_tools_verification_{A}_vs_{B}.json へ保存。
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

from sns_analyzer import analyze_sns_posts  # noqa: E402
from tools_analyzer import analyze_tools_items  # noqa: E402

# MODEL_A/MODEL_B を同一にすれば「同一モデルの実行揺らぎ」の基準が取れる
MODEL_A = os.environ.get("MODEL_A", "gemini-2.5-flash")
MODEL_B = os.environ.get("MODEL_B", "gemini-2.5-flash-lite")
OUTPUT = BASE / "data" / f"sns_tools_verification_{MODEL_A}_vs_{MODEL_B}.json"
MAX_SNS = 120
MAX_TOOLS = 90
JST = timezone(timedelta(hours=9))


def load_jsonl_dir(dirname: str, n_files: int = 2, max_items: int = 120) -> list[dict]:
    files = sorted((BASE / "data" / dirname).glob("*.jsonl"))[-n_files:]
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
    return items[:max_items]


def config_with(model_key: str, model: str) -> dict:
    config = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    config = copy.deepcopy(config)
    config.setdefault("analysis", {}).setdefault("models", {})[model_key] = model
    if "lite" in model:
        # Flash-Lite は thinking_budget 128 を受け付けない（0=無効 または 512以上）。
        # Lite 本来のデフォルト（thinking なし）で測る
        budgets = config["analysis"].setdefault("thinking_budget", {})
        budgets["stage1"] = 0
        budgets["tools"] = 0
    return config


def compare(result_a: list[dict], result_b: list[dict]) -> dict:
    a_by_id = {r["id"]: r for r in result_a if r.get("id")}
    b_by_id = {r["id"]: r for r in result_b if r.get("id")}
    a_ids, b_ids = set(a_by_id), set(b_by_id)
    common = a_ids & b_ids
    union = a_ids | b_ids

    category_match = sum(
        1 for c in common
        if (a_by_id[c].get("category") or "") == (b_by_id[c].get("category") or "")
    )
    return {
        "a_selected": len(a_ids),
        "b_selected": len(b_ids),
        "selection_jaccard": round(len(common) / len(union), 3) if union else 0.0,
        "common_count": len(common),
        "category_agreement": round(category_match / len(common), 3) if common else None,
        "a_only_sample": [a_by_id[i].get("title") or a_by_id[i].get("text", "")[:60] for i in list(a_ids - b_ids)[:5]],
        "b_only_sample": [b_by_id[i].get("title") or b_by_id[i].get("text", "")[:60] for i in list(b_ids - a_ids)[:5]],
    }


def main() -> None:
    sns_items = load_jsonl_dir("sns_success", max_items=MAX_SNS)
    tools_items = load_jsonl_dir("tools", max_items=MAX_TOOLS)
    if len(sns_items) < 30 or len(tools_items) < 20:
        print(f"検証に十分なデータがありません（sns {len(sns_items)}件 / tools {len(tools_items)}件）")
        sys.exit(1)
    print(f"入力: sns {len(sns_items)}件 / tools {len(tools_items)}件")

    # sns_analyzer は stage1_filter キー、tools_analyzer は fallback キーを参照する
    print(f"SNS: {MODEL_A} で実行中…")
    sns_a = analyze_sns_posts(copy.deepcopy(sns_items), config_with("stage1_filter", MODEL_A))
    time.sleep(10)
    print(f"SNS: {MODEL_B} で実行中…")
    sns_b = analyze_sns_posts(copy.deepcopy(sns_items), config_with("stage1_filter", MODEL_B))
    time.sleep(10)
    print(f"Tools: {MODEL_A} で実行中…")
    tools_a = analyze_tools_items(copy.deepcopy(tools_items), config_with("fallback", MODEL_A))
    time.sleep(10)
    print(f"Tools: {MODEL_B} で実行中…")
    tools_b = analyze_tools_items(copy.deepcopy(tools_items), config_with("fallback", MODEL_B))

    result = {
        "verified_at": datetime.now(JST).isoformat(timespec="seconds"),
        "model_a": MODEL_A,
        "model_b": MODEL_B,
        "sns_input": len(sns_items),
        "tools_input": len(tools_items),
        "sns_metrics": compare(sns_a, sns_b),
        "tools_metrics": compare(tools_a, tools_b),
        "note": (
            "selection_jaccard >= 0.8、category_agreement >= 0.85 なら Lite 化を可とする目安。"
            "境界なら MODEL_A=MODEL_B で揺らぎ基準を取って比較する"
        ),
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

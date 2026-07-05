"""Gemini API のトークン使用量記録と日次コスト集計。

各 generate_content 呼び出しの usage_metadata を data/gemini_usage/YYYY-MM-DD.jsonl
に追記する。記録失敗は本処理を妨げない。

集計表示: python gemini_usage.py [--days N]
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).parent
USAGE_DIR = BASE / "data" / "gemini_usage"

JST = timezone(timedelta(hours=9))

# 公式料金 USD/1Mトークン（2026-06 ai.google.dev/gemini-api/docs/pricing）
# 出力単価は thinking トークン込みで課金される
PRICING = {
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
}


def log_usage(component: str, model: str, response) -> None:
    """generate_content の response からトークン数を記録する。"""
    try:
        meta = getattr(response, "usage_metadata", None)
        if meta is None:
            return
        prompt_t = int(getattr(meta, "prompt_token_count", 0) or 0)
        out_t = int(getattr(meta, "candidates_token_count", 0) or 0)
        think_t = int(getattr(meta, "thoughts_token_count", 0) or 0)
        total_t = int(getattr(meta, "total_token_count", 0) or 0)
        model_key = model.split("/")[-1]
        price = PRICING.get(model_key)
        est = (
            (prompt_t * price["input"] + (out_t + think_t) * price["output"]) / 1e6
            if price
            else None
        )
        now = datetime.now(JST)
        rec = {
            "ts": now.isoformat(timespec="seconds"),
            "component": component,
            "model": model_key,
            "prompt_tokens": prompt_t,
            "output_tokens": out_t,
            "thinking_tokens": think_t,
            "total_tokens": total_t,
            "est_usd": round(est, 6) if est is not None else None,
        }
        USAGE_DIR.mkdir(parents=True, exist_ok=True)
        path = USAGE_DIR / f"{now:%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        # 計測の失敗で収集・分析を止めない
        pass


def summarize(days: int = 14) -> None:
    """日次×コンポーネント別の推定コストを表示する。"""
    rows = []
    if USAGE_DIR.exists():
        for path in sorted(USAGE_DIR.glob("*.jsonl"))[-days:]:
            for line in path.read_text(encoding="utf-8").split("\n"):
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    if not rows:
        print("記録なし（次回の収集実行から記録されます）")
        return

    daily = defaultdict(lambda: defaultdict(float))
    comp = defaultdict(lambda: {"calls": 0, "tokens": 0, "usd": 0.0})
    for r in rows:
        date = r["ts"][:10]
        daily[date][r["model"]] += r.get("est_usd") or 0.0
        c = comp[f"{r['component']} ({r['model']})"]
        c["calls"] += 1
        c["tokens"] += r.get("total_tokens") or 0
        c["usd"] += r.get("est_usd") or 0.0

    print("=" * 64)
    print("日別推定コスト (USD)")
    for date in sorted(daily):
        models = "  ".join(f"{m}: ${v:.4f}" for m, v in sorted(daily[date].items()))
        total = sum(daily[date].values())
        print(f"{date}  合計 ${total:.4f}  ({models})")
    print("-" * 64)
    print("コンポーネント別（期間合計）")
    for name, c in sorted(comp.items(), key=lambda kv: -kv[1]["usd"]):
        print(f"{name:42s} {c['calls']:4d}回 {c['tokens']:>10,}tok ${c['usd']:.4f}")
    print("=" * 64)


if __name__ == "__main__":
    n = 14
    if "--days" in sys.argv:
        n = int(sys.argv[sys.argv.index("--days") + 1])
    summarize(n)

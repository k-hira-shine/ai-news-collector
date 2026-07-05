#!/usr/bin/env python3
"""翻訳用途で Gemini Flash と Flash-Lite の品質・費用を比較する。"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google import genai
from google.genai import types

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

MODEL_A = os.environ.get("MODEL_A", "gemini-2.5-flash")
MODEL_B = os.environ.get("MODEL_B", "gemini-2.5-flash-lite")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gemini-2.5-pro")
OUTPUT = BASE / "data" / "translation_model_verification.json"
JST = timezone(timedelta(hours=9))

PRICING = {
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
}

TRANSLATION_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text_ja": {"type": "string"},
                },
                "required": ["id", "text_ja"],
            },
        }
    },
    "required": ["items"],
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "a_accuracy": {"type": "integer"},
                    "a_naturalness": {"type": "integer"},
                    "a_preservation": {"type": "integer"},
                    "a_instruction": {"type": "integer"},
                    "b_accuracy": {"type": "integer"},
                    "b_naturalness": {"type": "integer"},
                    "b_preservation": {"type": "integer"},
                    "b_instruction": {"type": "integer"},
                    "winner": {"type": "string", "enum": ["A", "B", "tie"]},
                    "reason": {"type": "string"},
                },
                "required": [
                    "id",
                    "a_accuracy",
                    "a_naturalness",
                    "a_preservation",
                    "a_instruction",
                    "b_accuracy",
                    "b_naturalness",
                    "b_preservation",
                    "b_instruction",
                    "winner",
                    "reason",
                ],
            },
        }
    },
    "required": ["items"],
}


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def load_samples() -> list[dict]:
    hn_rows = _read_jsonl(BASE / "data" / "hn" / "2026-06-10.jsonl")
    hn = [row for row in hn_rows if row.get("source_name") == "HackerNews"][:5]
    arxiv = [
        row
        for row in reversed(hn_rows)
        if str(row.get("source_name") or "").startswith("arxiv")
    ][:5]
    if len(arxiv) < 5:
        older = _read_jsonl(BASE / "data" / "hn" / "2026-06-09.jsonl")
        arxiv.extend(
            row
            for row in reversed(older)
            if str(row.get("source_name") or "").startswith("arxiv")
        )
        arxiv = arxiv[:5]

    gemini_rows = _read_jsonl(BASE / "data" / "gemini" / "2026-06-10.jsonl")[:5]
    buzz_data = json.loads(
        (BASE / "data" / "gemini_buzz" / "ranking.json").read_text(encoding="utf-8")
    )
    buzz = [row for row in buzz_data.get("posts", []) if row.get("is_discovery")][:5]

    samples = []
    for index, row in enumerate(hn):
        samples.append(
            {
                "id": f"hn-{index}",
                "category": "hn_title",
                "instruction": "記事タイトルを自然な日本語へ翻訳する。要約しない。",
                "source": row.get("title") or "",
            }
        )
    for index, row in enumerate(arxiv):
        samples.append(
            {
                "id": f"arxiv-{index}",
                "category": "arxiv",
                "instruction": "論文タイトルと要旨を日本語へ翻訳する。内容を省略しない。",
                "source": (
                    f"TITLE: {row.get('title') or ''}\n"
                    f"SUMMARY: {row.get('arxiv_summary') or ''}"
                ),
            }
        )
    for index, row in enumerate(gemini_rows):
        samples.append(
            {
                "id": f"gemini-{index}",
                "category": "gemini_summary",
                "instruction": (
                    "内容を日本語で80字以内に要約する。製品名、機能、何ができるかを具体的に残す。"
                ),
                "source": row.get("content") or row.get("title") or "",
            }
        )
    for index, row in enumerate(buzz):
        samples.append(
            {
                "id": f"buzz-{index}",
                "category": "x_post",
                "instruction": "X投稿を熱量や煽り表現も含めて自然な日本語へ全文翻訳する。",
                "source": row.get("text") or "",
            }
        )
    if len(samples) != 20:
        raise RuntimeError(f"Expected 20 samples, got {len(samples)}")
    return samples


def _usage(response, model: str) -> dict:
    meta = response.usage_metadata
    prompt = int(getattr(meta, "prompt_token_count", 0) or 0)
    output = int(getattr(meta, "candidates_token_count", 0) or 0)
    thinking = int(getattr(meta, "thoughts_token_count", 0) or 0)
    price = PRICING[model]
    cost = (prompt * price["input"] + (output + thinking) * price["output"]) / 1_000_000
    return {
        "prompt_tokens": prompt,
        "output_tokens": output,
        "thinking_tokens": thinking,
        "estimated_usd": round(cost, 6),
    }


def translate(client, model: str, samples: list[dict]) -> tuple[dict[str, str], dict]:
    blocks = "\n\n".join(
        f"[ID: {sample['id']}]\n指示: {sample['instruction']}\n原文:\n{sample['source']}"
        for sample in samples
    )
    response = client.models.generate_content(
        model=model,
        contents=(
            "各項目の指示に従って日本語化してください。余計な説明は不要です。\n\n"
            + blocks
        ),
        config={
            "response_mime_type": "application/json",
            "response_json_schema": TRANSLATION_SCHEMA,
            "thinking_config": {"thinking_budget": 0},
            "max_output_tokens": 20000,
        },
    )
    parsed = json.loads(response.text or "{}")
    outputs = {
        item["id"]: item["text_ja"]
        for item in parsed.get("items", [])
        if item.get("id") and item.get("text_ja")
    }
    return outputs, _usage(response, model)


def judge(
    client,
    samples: list[dict],
    output_a: dict[str, str],
    output_b: dict[str, str],
) -> tuple[list[dict], dict]:
    blocks = "\n\n".join(
        f"""[ID: {sample['id']}]
指示: {sample['instruction']}
原文:
{sample['source']}

候補A:
{output_a.get(sample['id'], '')}

候補B:
{output_b.get(sample['id'], '')}"""
        for sample in samples
    )
    response = client.models.generate_content(
        model=JUDGE_MODEL,
        contents=f"""翻訳・日本語化の候補A/Bをブラインド評価してください。

各項目を1〜5点で採点:
- accuracy: 原文の意味を正確に保持
- naturalness: 日本語として自然
- preservation: 固有名詞、数字、重要な詳細を保持
- instruction: 全文翻訳や80字要約など個別指示を順守

同等ならwinnerはtie。モデル名を推測せず、出力だけで評価してください。

{blocks}""",
        config={
            "response_mime_type": "application/json",
            "response_json_schema": JUDGE_SCHEMA,
            "thinking_config": {"thinking_budget": 512},
            "max_output_tokens": 12000,
        },
    )
    parsed = json.loads(response.text or "{}")
    return parsed.get("items", []), _usage(response, JUDGE_MODEL)


def summarize(judgments: list[dict], samples: list[dict]) -> dict:
    category_by_id = {sample["id"]: sample["category"] for sample in samples}
    metrics = {}
    for category in ["all", "hn_title", "arxiv", "gemini_summary", "x_post"]:
        rows = [
            row
            for row in judgments
            if category == "all" or category_by_id.get(row["id"]) == category
        ]
        scores = {}
        for side in ("a", "b"):
            values = [
                row[f"{side}_{metric}"]
                for row in rows
                for metric in ("accuracy", "naturalness", "preservation", "instruction")
            ]
            scores[f"{side}_average"] = round(sum(values) / len(values), 3) if values else 0
        scores["a_wins"] = sum(row["winner"] == "A" for row in rows)
        scores["b_wins"] = sum(row["winner"] == "B" for row in rows)
        scores["ties"] = sum(row["winner"] == "tie" for row in rows)
        metrics[category] = scores
    return metrics


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY missing")
    client = genai.Client(api_key=api_key)
    samples = load_samples()
    output_a, usage_a = translate(client, MODEL_A, samples)
    output_b, usage_b = translate(client, MODEL_B, samples)
    judgments, judge_usage = judge(client, samples, output_a, output_b)
    result = {
        "verified_at": datetime.now(JST).isoformat(timespec="seconds"),
        "model_a": MODEL_A,
        "model_b": MODEL_B,
        "judge_model": JUDGE_MODEL,
        "sample_count": len(samples),
        "usage": {
            "model_a": usage_a,
            "model_b": usage_b,
            "judge": judge_usage,
        },
        "metrics": summarize(judgments, samples),
        "samples": [
            {
                **sample,
                "output_a": output_a.get(sample["id"], ""),
                "output_b": output_b.get(sample["id"], ""),
                "judgment": next(
                    (row for row in judgments if row.get("id") == sample["id"]),
                    {},
                ),
            }
            for sample in samples
        ],
        "acceptance_rule": (
            "Flash-Liteの全体平均がFlash比0.25点以内、accuracyとpreservationで"
            "3点未満がなく、カテゴリ別で重大な劣化がなければ切替候補。"
        ),
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("usage", "metrics")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

import json

from scripts import verify_sns_tools_lite
from scripts.verify_translation_models import _read_jsonl, summarize


def test_summarize_groups_scores_by_category() -> None:
    samples = [
        {"id": "a", "category": "hn_title"},
        {"id": "b", "category": "x_post"},
    ]
    judgments = [
        {
            "id": "a",
            "a_accuracy": 5,
            "a_naturalness": 4,
            "a_preservation": 5,
            "a_instruction": 4,
            "b_accuracy": 4,
            "b_naturalness": 4,
            "b_preservation": 4,
            "b_instruction": 4,
            "winner": "A",
        },
        {
            "id": "b",
            "a_accuracy": 4,
            "a_naturalness": 4,
            "a_preservation": 4,
            "a_instruction": 4,
            "b_accuracy": 5,
            "b_naturalness": 5,
            "b_preservation": 5,
            "b_instruction": 5,
            "winner": "B",
        },
    ]

    result = summarize(judgments, samples)

    assert result["all"]["a_wins"] == 1
    assert result["all"]["b_wins"] == 1
    assert result["hn_title"]["a_average"] == 4.5
    assert result["x_post"]["b_average"] == 5.0


def test_read_jsonl_preserves_unicode_line_separator(tmp_path) -> None:
    path = tmp_path / "sample.jsonl"
    rows = [
        {"id": "a", "text": "first\u2028second"},
        {"id": "b", "text": "plain"},
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )

    assert _read_jsonl(path) == rows


def test_verify_sns_tools_loader_preserves_unicode_line_separator(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data" / "tools"
    data_dir.mkdir(parents=True)
    rows = [
        {"id": "a", "title": "one\u2028two"},
        {"id": "b", "title": "plain"},
    ]
    (data_dir / "2026-07-06.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(verify_sns_tools_lite, "BASE", tmp_path)

    assert verify_sns_tools_lite.load_jsonl_dir("tools", n_files=1, max_items=10) == rows

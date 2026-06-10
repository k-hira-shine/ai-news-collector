from scripts.verify_translation_models import summarize


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

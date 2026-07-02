import pytest

import money_analyzer
import sns_analyzer


def _item(item_id: str) -> dict:
    return {
        "id": item_id,
        "author_followers": 10000,
        "content": "test",
        "engagement": {"likes": 1},
    }


def test_money_analysis_splits_failed_batch(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_analyze(items, model_name, api_key, config):
        calls.append([i["id"] for i in items])
        if len(items) > 1:
            raise RuntimeError("response truncated")
        return [{"id": items[0]["id"], "summary": "ok"}]

    monkeypatch.setattr(money_analyzer, "_analyze_batch", fake_analyze)

    result = money_analyzer._analyze_batch_resilient(
        [_item("a"), _item("b")],
        "model",
        "key",
        {},
    )

    assert [r["id"] for r in result] == ["a", "b"]
    assert calls == [["a", "b"], ["a", "b"], ["a"], ["b"]]


def test_sns_analysis_splits_failed_batch(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_analyze(items, model_name, api_key, config):
        calls.append([i["id"] for i in items])
        if len(items) > 1:
            raise RuntimeError("response truncated")
        return [{"id": items[0]["id"], "summary": "ok"}]

    monkeypatch.setattr(sns_analyzer, "_analyze_batch", fake_analyze)

    result = sns_analyzer._analyze_batch_resilient(
        [_item("a"), _item("b")],
        "model",
        "key",
        {},
    )

    assert [r["id"] for r in result] == ["a", "b"]
    assert calls == [["a", "b"], ["a", "b"], ["a"], ["b"]]


def test_sns_analysis_raises_when_single_item_keeps_failing(monkeypatch) -> None:
    def fake_analyze(items, model_name, api_key, config):
        raise RuntimeError("gemini unavailable")

    monkeypatch.setattr(sns_analyzer, "_analyze_batch", fake_analyze)

    with pytest.raises(RuntimeError, match="SNS analysis failed for item a"):
        sns_analyzer._analyze_batch_resilient([_item("a")], "model", "key", {})

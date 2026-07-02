from incident_status import resolve_incident_for_write


def test_collect_success_clears_existing_incident_when_requested() -> None:
    existing = {
        "active": "true",
        "severity": "warning",
        "title": "収集パイプラインに警告",
    }

    resolved = resolve_incident_for_write(
        "collect",
        "success",
        stats={"total": 84, "analysis_meta": {"top_articles_count": 10}},
        config={"alerts": {"enabled": True}},
        existing=existing,
        clear_on_success=True,
    )

    assert resolved is None


def test_buzz_success_clears_existing_incident_when_requested() -> None:
    existing = {
        "active": "true",
        "severity": "warning",
        "title": "buzz が warning で終了",
    }

    resolved = resolve_incident_for_write(
        "buzz",
        "success",
        existing=existing,
        clear_on_success=True,
    )

    assert resolved is None

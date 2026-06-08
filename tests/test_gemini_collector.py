from datetime import timezone

from gemini_collector import _parse_date_from_string, _parse_rss_entry_date


def test_parse_date_from_string_normalizes_naive_iso_to_utc() -> None:
    dt = _parse_date_from_string("2026-06-09T12:34:56")
    assert dt is not None
    assert dt.tzinfo == timezone.utc


def test_parse_rss_struct_time_is_utc_aware() -> None:
    entry = {
        "published_parsed": (2026, 6, 9, 12, 34, 56, 1, 160, 0),
    }
    dt = _parse_rss_entry_date(entry)
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.isoformat() == "2026-06-09T12:34:56+00:00"

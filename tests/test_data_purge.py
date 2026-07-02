from datetime import date, timedelta

from utils import _date_from_filename, purge_dated_files


def test_date_from_filename_accepts_dated_prefix() -> None:
    assert _date_from_filename("2026-06-01.jsonl") == date(2026, 6, 1)
    assert _date_from_filename("2026-06-01_morning_analysis.json") == date(2026, 6, 1)
    assert _date_from_filename("latest.json") is None


def test_purge_dated_files_uses_filename_date_not_mtime(tmp_path) -> None:
    old = date.today() - timedelta(days=40)
    new = date.today() - timedelta(days=5)
    old_path = tmp_path / f"{old.isoformat()}.jsonl"
    new_path = tmp_path / f"{new.isoformat()}.jsonl"
    ignored_path = tmp_path / "not-dated.jsonl"
    old_path.write_text("old\n", encoding="utf-8")
    new_path.write_text("new\n", encoding="utf-8")
    ignored_path.write_text("ignored\n", encoding="utf-8")

    removed = purge_dated_files(str(tmp_path), keep_days=30, suffixes=(".jsonl",))

    assert removed == [old_path.name]
    assert not old_path.exists()
    assert new_path.exists()
    assert ignored_path.exists()

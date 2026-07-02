from pathlib import Path

from incident_status import find_leaked_incident_css_files


def test_current_docs_do_not_leak_incident_css() -> None:
    leaked = find_leaked_incident_css_files()
    assert leaked == []


def test_find_leaked_incident_css_files_ignores_style_blocks(tmp_path: Path) -> None:
    (tmp_path / "ok.html").write_text(
        "<html><head><style>.incident-mount-wrap { color: red; }</style></head><body></body></html>",
        encoding="utf-8",
    )

    assert find_leaked_incident_css_files(str(tmp_path)) == []


def test_find_leaked_incident_css_files_detects_body_leak(tmp_path: Path) -> None:
    (tmp_path / "bad.html").write_text(
        "<html><head></head><body>.incident-mount-wrap { color: red; }</body></html>",
        encoding="utf-8",
    )

    assert find_leaked_incident_css_files(str(tmp_path)) == ["bad.html"]

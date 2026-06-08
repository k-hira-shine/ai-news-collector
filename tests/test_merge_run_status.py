import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / ".github" / "scripts" / "merge_run_status.py"
SPEC = importlib.util.spec_from_file_location("merge_run_status", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_merge_statuses_keeps_newest_state_per_workflow() -> None:
    left = {
        "updated_at": "2026-06-09T03:10:00+09:00",
        "workflows": {
            "collect": {"status": "success", "ts": "2026-06-09T03:05:00+09:00"},
            "buzz": {"status": "success", "ts": "2026-06-09T03:10:00+09:00"},
        },
    }
    right = {
        "updated_at": "2026-06-09T03:31:00+09:00",
        "workflows": {
            "collect": {"status": "success", "ts": "2026-06-09T03:05:00+09:00"},
            "buzz": {"status": "success", "ts": "2026-06-08T02:42:00+09:00"},
            "money": {"status": "success", "ts": "2026-06-09T03:31:00+09:00"},
        },
    }

    merged, selected = MODULE.merge_statuses(left, right)

    assert merged["workflows"]["buzz"]["ts"] == "2026-06-09T03:10:00+09:00"
    assert merged["workflows"]["money"]["ts"] == "2026-06-09T03:31:00+09:00"
    assert selected["buzz"] == "left"
    assert merged["overall"] == "success"
    assert merged["updated_at"] == "2026-06-09 03:31 JST"

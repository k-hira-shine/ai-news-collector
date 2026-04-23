"""Discord 配信結果の永続化（次回 run で前回失敗を検知するため）"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("ai-news.discord_state")

STATE_REL = os.path.join("data", "runtime", "discord_state.json")


def _state_path() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, STATE_REL)


def load_discord_state() -> dict[str, Any]:
    path = _state_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read discord state %s: %s", path, e)
        return {}


def save_discord_state(payload: dict[str, Any]) -> None:
    path = _state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    out: dict[str, Any] = {
        **payload,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    logger.info("Discord delivery state saved → %s (ok=%s)", path, out.get("ok"))


def merge_delivery_results(*parts: dict[str, Any] | None) -> dict[str, Any]:
    """複数回の配信（notify + 完了行など）を 1 つのサマリにまとめる"""
    valid: list[dict] = [p for p in parts if p is not None]
    if not valid:
        return {
            "ok": True,
            "skipped": True,
            "reason": "empty",
            "total": 0,
            "succeeded": 0,
            "failed_parts": [],
        }
    if all(p.get("skipped") for p in valid):
        return {
            "ok": False,
            "skipped": True,
            "reason": "all_skipped",
            "total": 0,
            "succeeded": 0,
            "failed_parts": [],
        }
    tot = 0
    suc = 0
    fail: list[str] = []
    for p in valid:
        if p.get("skipped"):
            continue
        tot += int(p.get("total", 0))
        suc += int(p.get("succeeded", 0))
        fail.extend(p.get("failed_parts") or [])
    return {
        "ok": len(fail) == 0,
        "skipped": False,
        "reason": "",
        "total": tot,
        "succeeded": suc,
        "failed_parts": fail,
    }

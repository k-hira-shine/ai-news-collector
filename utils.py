"""共通ユーティリティ: リトライ、ログ、ハッシュ、日付処理"""

import functools
import hashlib
import logging
import os
import random
import time
import zoneinfo
from datetime import datetime, timezone

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(level=logging.INFO) -> logging.Logger:
    logging.basicConfig(format=LOG_FORMAT, level=level)
    return logging.getLogger("ai-news")


def retry(max_retries=3, base_delay=2, max_delay=30, exceptions=(Exception,)):
    """Exponential backoff リトライデコレータ（ジッター付き）"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_retries:
                        raise
                    delay = min(base_delay * (2**attempt), max_delay)
                    jitter = delay * random.uniform(0, 0.3)
                    total_delay = delay + jitter
                    logging.getLogger("ai-news").warning(
                        "Retry %d/%d for %s (%.0fs wait): %s",
                        attempt + 1, max_retries, func.__name__, total_delay, e,
                    )
                    time.sleep(total_delay)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


def hash_url(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_str() -> str:
    return datetime.now(zoneinfo.ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")


def time_slot() -> str:
    """JST で朝(05-13時)は morning、それ以外は evening"""
    jst = datetime.now(zoneinfo.ZoneInfo("Asia/Tokyo"))
    return "morning" if 5 <= jst.hour < 14 else "evening"


def parse_datetime(s: str) -> datetime | None:
    """ISO 形式 / RFC 2822 形式の日時文字列をパース (失敗時 None)"""
    if not s:
        return None
    # ISO 8601
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        pass
    # RFC 2822 (X/Twitter: "Sat Apr 04 23:28:36 +0000 2026")
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(s)
    except (ValueError, TypeError):
        return None


def data_dir(*parts: str) -> str:
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    return os.path.join(base, *parts)


# ── 実行ログ ──────────────────────────────────────────────────────────
import json as _json


def log_run(
    workflow: str,
    status: str,
    *,
    elapsed_sec: float = 0,
    items_collected: int = 0,
    items_analyzed: int = 0,
    apify_cost_usd: float = 0,
    error: str = "",
    extra: dict | None = None,
) -> None:
    """実行結果を data/logs/YYYY-MM-DD.jsonl に追記（1行1レコード）。

    Args:
        workflow: "collect" | "money" | "buzz" など
        status:   "success" | "error" | "warning"
        ...
    """
    JST = zoneinfo.ZoneInfo("Asia/Tokyo")
    now = datetime.now(JST)
    log_dir = data_dir("logs")
    os.makedirs(log_dir, exist_ok=True)

    record = {
        "ts": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M JST"),
        "workflow": workflow,
        "status": status,
        "elapsed_sec": round(elapsed_sec, 1),
        "items_collected": items_collected,
        "items_analyzed": items_analyzed,
        "apify_cost_usd": round(apify_cost_usd, 4),
        "error": error,
    }
    if extra:
        record.update(extra)

    log_path = os.path.join(log_dir, f"{now.strftime('%Y-%m-%d')}.jsonl")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(_json.dumps(record, ensure_ascii=False) + "\n")

    # 30日より古いログを削除
    _purge_old_logs(log_dir, keep_days=30)


def _purge_old_logs(log_dir: str, keep_days: int = 30) -> None:
    from datetime import timezone as _tz
    cutoff = datetime.now(_tz.utc).timestamp() - keep_days * 86400
    for fname in os.listdir(log_dir):
        if not fname.endswith(".jsonl"):
            continue
        fpath = os.path.join(log_dir, fname)
        if os.path.getmtime(fpath) < cutoff:
            os.remove(fpath)
            logging.getLogger("ai-news").info("Purged old log: %s", fname)


def read_run_logs(days: int = 7) -> list[dict]:
    """直近 days 日分のログレコードを新しい順で返す"""
    log_dir = data_dir("logs")
    if not os.path.isdir(log_dir):
        return []
    records: list[dict] = []
    for fname in sorted(os.listdir(log_dir), reverse=True):
        if not fname.endswith(".jsonl"):
            continue
        fpath = os.path.join(log_dir, fname)
        with open(fpath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(_json.loads(line))
                    except Exception:
                        pass
        if len(records) >= days * 20:  # 1日最大20件想定
            break
    return records

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
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def time_slot() -> str:
    """JST で朝(05-13時)は morning、それ以外は evening"""
    jst = datetime.now(zoneinfo.ZoneInfo("Asia/Tokyo"))
    return "morning" if 5 <= jst.hour < 14 else "evening"


def parse_datetime(s: str) -> datetime | None:
    """ISO 形式の日時文字列をパース (失敗時 None)"""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def data_dir(*parts: str) -> str:
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    return os.path.join(base, *parts)

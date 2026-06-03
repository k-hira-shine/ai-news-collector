#!/usr/bin/env python3
"""xquik / Apify X 検索の最小プローブ（フル収集・分析・図解なし）

使い方:
  APIFY_TOKEN=... python3 scripts/probe_x_upstream.py

成功: exit 0 / 「OK: N 件」
失敗: exit 1 / ログに x_api_unavailable 等
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from apify_client import ApifyClient

from collector import _fetch_apify_run_log, _inspect_apify_run_log, _is_valid_tweet_item
from utils import apify_actor_call, apify_run_get


def main() -> int:
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        print("APIFY_TOKEN が未設定です", file=sys.stderr)
        return 2

    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    run_input = {
        "searchTerms": ["from:OpenAI -filter:replies"],
        "queryType": "Latest",
        "maxItems": 3,
        "includeSearchTerms": False,
        "since": since,
    }

    client = ApifyClient(token)
    print(f"Probing xquik/x-tweet-scraper (since={since}, maxItems=3) ...")
    run = apify_actor_call(client.actor("xquik/x-tweet-scraper"), run_input=run_input, wait_seconds=120)
    run_id = apify_run_get(run, "id", "")
    status = apify_run_get(run, "status", "")
    cost = float(apify_run_get(run, "usageTotalUsd") or 0)

    valid = 0
    ds_id = apify_run_get(run, "defaultDatasetId")
    if ds_id:
        for raw in client.dataset(ds_id).iterate_items():
            url = (raw.get("url") or raw.get("tweetUrl") or "").strip()
            text = (raw.get("text") or raw.get("fullText") or "").strip()
            if _is_valid_tweet_item({"url": url, "content": text}):
                valid += 1

    inspection = _inspect_apify_run_log(_fetch_apify_run_log(client, run_id)) if run_id else {}
    hints = inspection.get("hints") or []

    print(f"run={run_id} status={status} valid_tweets={valid} cost_usd={cost:.4f}")
    if hints:
        print(f"hints={', '.join(hints)}")
    if inspection.get("sample_error"):
        print(f"log_sample={inspection['sample_error']}")

    if valid > 0:
        print("OK: 上流は応答してツイートを取得できました")
        return 0

    if "x_api_unavailable" in hints or "http_502" in hints:
        print("NG: 上流 API 障害の可能性（x_api_unavailable / 502）", file=sys.stderr)
        return 1

    print("NG: 0 件（原因はログの hints を確認）", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

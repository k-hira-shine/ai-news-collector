#!/usr/bin/env python3
"""Cursor SDK の最小試用スクリプト（ローカルエージェント・1回実行）。

事前準備:
  1. source .venv/bin/activate
     pip install -r requirements-sdk.txt
  2. Cursor Dashboard → Integrations で API キーを発行
     https://cursor.com/dashboard/integrations
  3. export CURSOR_API_KEY="cursor_..."

実行例:
  python scripts/cursor_sdk_try.py
  python scripts/cursor_sdk_try.py "config.yaml の x_twitter セクションを説明して"
"""

from __future__ import annotations

import os
import sys

from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PROMPT = "README.md を読んで、このプロジェクトが何をするものか3行で要約して。"


def main() -> int:
    api_key = os.environ.get("CURSOR_API_KEY")
    if not api_key:
        print(
            "CURSOR_API_KEY が未設定です。\n"
            "Dashboard → Integrations でキーを発行し、\n"
            "  export CURSOR_API_KEY='cursor_...'\n"
            "を実行してから再試行してください。",
            file=sys.stderr,
        )
        return 1

    prompt = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT

    try:
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=api_key,
                model="composer-2.5",
                local=LocalAgentOptions(cwd=ROOT),
            ),
        )
    except CursorAgentError as err:
        print(
            f"起動失敗: {err.message} (retryable={err.is_retryable})",
            file=sys.stderr,
        )
        return 1

    if result.status == "error":
        print(f"実行失敗: run_id={result.id}", file=sys.stderr)
        return 2

    print(result.result or "(応答なし)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

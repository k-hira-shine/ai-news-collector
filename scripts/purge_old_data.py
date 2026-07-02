#!/usr/bin/env python3
"""日付ファイル名ベースで古い data ファイルを削除する。

Actions の checkout は mtime を現在時刻にするため、mtime ベースの purge は効かない。
このスクリプトは YYYY-MM-DD で始まるファイル名だけを対象にする。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import purge_dated_files


DEFAULT_POLICIES: dict[str, tuple[int, tuple[str, ...]]] = {
    "data/logs": (30, (".jsonl",)),
    "data/daily": (45, (".jsonl",)),
    "data/hn": (45, (".jsonl",)),
    "data/gemini_usage": (60, (".jsonl",)),
    "data/analysis": (75, (".json",)),
    "data/tools": (90, (".jsonl",)),
}


def purge(root: Path = ROOT, *, dry_run: bool = False) -> dict[str, list[str]]:
    removed_by_dir: dict[str, list[str]] = {}
    for rel, (keep_days, suffixes) in DEFAULT_POLICIES.items():
        directory = root / rel
        if dry_run:
            removed = _would_remove(directory, keep_days=keep_days, suffixes=suffixes)
        else:
            removed = purge_dated_files(str(directory), keep_days=keep_days, suffixes=suffixes)
        if removed:
            removed_by_dir[rel] = removed
    return removed_by_dir


def _would_remove(directory: Path, *, keep_days: int, suffixes: tuple[str, ...]) -> list[str]:
    from datetime import datetime, timedelta, timezone
    from utils import _date_from_filename

    if keep_days <= 0 or not directory.is_dir():
        return []
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=keep_days)
    out = []
    for path in directory.iterdir():
        if not path.is_file() or not path.name.endswith(suffixes):
            continue
        file_date = _date_from_filename(path.name)
        if file_date is not None and file_date < cutoff:
            out.append(path.name)
    return sorted(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge old dated data files")
    parser.add_argument("--dry-run", action="store_true", help="削除せず対象だけ表示")
    args = parser.parse_args()

    removed_by_dir = purge(dry_run=args.dry_run)
    if not removed_by_dir:
        print("No old dated data files to purge")
        return 0

    verb = "Would purge" if args.dry_run else "Purged"
    total = 0
    for rel, files in removed_by_dir.items():
        total += len(files)
        print(f"{verb} {len(files)} files from {rel}: {', '.join(files[:8])}{' ...' if len(files) > 8 else ''}")
    print(f"{verb} {total} files total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

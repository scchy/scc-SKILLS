#!/usr/bin/env python3
"""Retrieve experiment history from the journal."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import load_entries, DEFAULT_JOURNAL_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Query experiment history")
    parser.add_argument(
        "--limit", type=int, default=20, help="Max entries to return"
    )
    parser.add_argument(
        "--filter_status",
        choices=["all", "success", "buggy"],
        default="all",
        help="Filter by outcome",
    )
    parser.add_argument(
        "--tag", default=None, help="Filter by exact tag match"
    )
    parser.add_argument(
        "--journal_path",
        default=str(DEFAULT_JOURNAL_PATH),
        help="Override journal file path",
    )
    args = parser.parse_args()

    entries = load_entries(Path(args.journal_path))

    if args.filter_status == "success":
        entries = [e for e in entries if not e.get("is_bug", True)]
    elif args.filter_status == "buggy":
        entries = [e for e in entries if e.get("is_bug", True)]

    if args.tag:
        entries = [e for e in entries if args.tag in e.get("tags", [])]

    entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    entries = entries[: args.limit]

    print(json.dumps(entries, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

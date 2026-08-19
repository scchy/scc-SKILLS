#!/usr/bin/env python3
"""Retrieve experiment history from the journal.

Output protocol: stdout carries a single compact JSON array (agent-consumable);
errors are reported as a JSON object plus a non-zero exit code.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import derive_task_id, get_journal_path, load_entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Query experiment history")
    parser.add_argument(
        "--task_id",
        default=None,
        help="Task identifier. If omitted, auto-derived from dataset fingerprint or $TASK_ID env var.",
    )
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
    args = parser.parse_args()

    try:
        # Auto-derive task_id if not provided
        task_id = args.task_id or derive_task_id()
        journal_path = get_journal_path(task_id)
        entries = load_entries(journal_path)

        if args.filter_status == "success":
            entries = [e for e in entries if not e.get("is_bug", True)]
        elif args.filter_status == "buggy":
            entries = [e for e in entries if e.get("is_bug", True)]

        if args.tag:
            entries = [e for e in entries if args.tag in e.get("tags", [])]

        entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        entries = entries[: args.limit]
    except Exception as e:
        message = f"unexpected {type(e).__name__}: {e}"
        print(f"[review-experiment] Error: {message}", file=sys.stderr)
        print(json.dumps({"status": "error", "error": message}))
        sys.exit(2)

    print(json.dumps(entries, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()

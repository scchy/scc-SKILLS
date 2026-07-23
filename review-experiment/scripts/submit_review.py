#!/usr/bin/env python3
"""Submit a structured review of a completed experiment.

Output protocol: stdout carries a single JSON object (agent-consumable);
human-readable logs and warnings go to stderr.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    append_entry,
    append_md_fallback,
    cache_task_id,
    derive_task_id,
    get_journal_path,
    load_entries,
)


def _str2bool(value: str) -> bool:
    s = value.lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(
        f"expected one of true/false/1/0/yes/no, got {value!r}"
    )


def _fail(message: str) -> None:
    """Report an error the agent can parse, then exit non-zero."""
    print(f"[review-experiment] Error: {message}", file=sys.stderr)
    print(json.dumps({"status": "error", "error": message}))
    sys.exit(2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit experiment review")
    parser.add_argument(
        "--task_id",
        default=None,
        help="Task identifier. If omitted, auto-derived from dataset fingerprint or $TASK_ID env var.",
    )
    parser.add_argument("--submission_id", required=True)
    parser.add_argument(
        "--is_bug",
        type=_str2bool,
        required=True,
        help="true if execution failed or metric is invalid",
    )
    parser.add_argument(
        "--metric",
        type=float,
        default=None,
        help="CV metric value. Omit or pass null if is_bug=true",
    )
    parser.add_argument(
        "--lower_is_better",
        type=_str2bool,
        required=True,
        help="true for RMSE/MAE/LogLoss, false for Accuracy/F1/AUC",
    )
    parser.add_argument("--summary", required=True)
    parser.add_argument("--parent_id", default=None)
    parser.add_argument(
        "--tags",
        default="[]",
        help='JSON array of strings, e.g., \'["lightgbm", "baseline"]\'',
    )
    args = parser.parse_args()

    try:
        tags = json.loads(args.tags) if args.tags else []
        if not isinstance(tags, list):
            raise ValueError("value must be a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        _fail(
            f"invalid --tags ({e}). "
            'Expected a JSON array, e.g., \'["lightgbm", "baseline"]\''
        )

    try:
        # An explicit task_id wins and locks the session cache, so mixed
        # explicit/auto calls stay on the same journal.
        task_id = cache_task_id(args.task_id) if args.task_id else derive_task_id()
        journal_path = get_journal_path(task_id)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "submission_id": args.submission_id,
            "is_bug": args.is_bug,
            "metric": args.metric if not args.is_bug else None,
            "lower_is_better": args.lower_is_better,
            "summary": args.summary,
            "parent_id": args.parent_id,
            "tags": tags,
            "task_id": task_id,
        }

        duplicate = any(
            e.get("submission_id") == args.submission_id
            for e in load_entries(journal_path)
        )

        append_entry(entry, journal_path)
        append_md_fallback(entry, journal_path)
    except ValueError as e:
        _fail(str(e))
    except Exception as e:
        _fail(f"unexpected {type(e).__name__}: {e}")

    warnings = []
    if duplicate:
        warnings.append(
            f"submission_id '{args.submission_id}' already exists in the "
            "journal; verify this is not a duplicate experiment"
        )
    if not args.is_bug and args.metric is None:
        warnings.append(
            "metric is missing for a non-bug experiment; "
            "pass --metric so results stay comparable"
        )

    result = {"status": "ok", "submission_id": args.submission_id, "task_id": task_id}
    if warnings:
        result["warnings"] = warnings
        for w in warnings:
            print(f"[review-experiment] WARNING: {w}", file=sys.stderr)
    print(
        f"[review-experiment] Recorded {args.submission_id} for task {task_id}",
        file=sys.stderr,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()

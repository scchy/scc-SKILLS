#!/usr/bin/env python3
"""Submit a structured review of a completed experiment."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import append_entry, append_md_fallback, load_entries, DEFAULT_JOURNAL_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit experiment review")
    parser.add_argument("--submission_id", required=True)
    parser.add_argument(
        "--is_bug",
        type=lambda x: x.lower() in ("true", "1", "yes"),
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
        type=lambda x: x.lower() in ("true", "1", "yes"),
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
    parser.add_argument(
        "--journal_path",
        default=str(DEFAULT_JOURNAL_PATH),
        help="Override journal file path",
    )
    args = parser.parse_args()

    try:
        tags = json.loads(args.tags) if args.tags else []
        if not isinstance(tags, list):
            raise ValueError("tags must be a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        print(
            f"[review-experiment] Error: invalid --tags value ({e}). "
            'Expected a JSON array, e.g., \'["lightgbm", "baseline"]\'',
            file=sys.stderr,
        )
        sys.exit(2)

    journal_path = Path(args.journal_path)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "submission_id": args.submission_id,
        "is_bug": args.is_bug,
        "metric": args.metric if not args.is_bug else None,
        "lower_is_better": args.lower_is_better,
        "summary": args.summary,
        "parent_id": args.parent_id,
        "tags": tags,
    }

    duplicate = any(
        e.get("submission_id") == args.submission_id
        for e in load_entries(journal_path)
    )

    append_entry(entry, journal_path)
    append_md_fallback(entry, journal_path)

    print(f"[review-experiment] Recorded {args.submission_id}")
    result = {"status": "ok", "submission_id": args.submission_id}
    if duplicate:
        warning = (
            f"submission_id '{args.submission_id}' already exists in the "
            "journal; verify this is not a duplicate experiment"
        )
        result["warning"] = warning
        print(f"[review-experiment] WARNING: {warning}", file=sys.stderr)
    print(json.dumps(result))


if __name__ == "__main__":
    main()

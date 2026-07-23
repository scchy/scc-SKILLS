"""Shared utilities for review-experiment skill."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_JOURNAL_PATH = Path("./working/experiment_journal.jsonl")


def ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_entries(path: Path = DEFAULT_JOURNAL_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def append_entry(entry: dict[str, Any], path: Path = DEFAULT_JOURNAL_PATH) -> None:
    ensure_dir(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def append_md_fallback(
    entry: dict[str, Any], journal_path: Path = DEFAULT_JOURNAL_PATH
) -> None:
    log_md = journal_path.parent / "experiment_log.md"
    ensure_dir(log_md)
    with open(log_md, "a", encoding="utf-8") as f:
        f.write(f"\n## {entry['submission_id']}\n")
        f.write(f"- **timestamp**: {entry.get('timestamp')}\n")
        f.write(f"- **metric**: {entry.get('metric')}\n")
        f.write(f"- **lower_is_better**: {entry.get('lower_is_better')}\n")
        f.write(f"- **is_bug**: {entry.get('is_bug')}\n")
        f.write(f"- **summary**: {entry.get('summary')}\n")
        if entry.get("parent_id"):
            f.write(f"- **parent_id**: {entry['parent_id']}\n")
        if entry.get("tags"):
            f.write(f"- **tags**: {entry['tags']}\n")

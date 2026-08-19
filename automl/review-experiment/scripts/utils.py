"""Shared utilities for review-experiment skill."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

# In the kaggle-kaggle sandbox, run_skill_script executes scripts from a
# temporary directory, so relative defaults would lose data between calls.
# Default to the persistent sandbox work dir (/work) when it exists.
_SANDBOX_ROOT = Path("/work")
WORKING_DIR = Path(
    os.environ.get("WORKING_DIR")
    or (_SANDBOX_ROOT / "working" if _SANDBOX_ROOT.is_dir() else "./working")
)
INPUT_DIR = os.environ.get("INPUT_DIR") or (
    str(_SANDBOX_ROOT) if _SANDBOX_ROOT.is_dir() else "./input"
)
TASK_ID_CACHE = WORKING_DIR / ".review_experiment_task_id"
TASK_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
FINGERPRINT_PREFIX = "task_"


def validate_task_id(task_id: str) -> str:
    """Reject task IDs that could escape ./working/ via path traversal."""
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise ValueError(
            f"invalid task_id {task_id!r}: only letters, digits, '_' and '-' are allowed"
        )
    return task_id


def _compute_fingerprint(data_dir: str = INPUT_DIR) -> str | None:
    """Compute dataset fingerprint. Supports CSV and Parquet.

    Looks for train.csv / train.parquet in `data_dir` first, then in the
    current working directory (competition sandboxes place data at root).
    """
    candidates = [Path(data_dir)]
    cwd = Path(".")
    try:
        if cwd.resolve() != candidates[0].resolve():
            candidates.append(cwd)
    except OSError:
        candidates.append(cwd)

    for base in candidates:
        # Try CSV first
        train_csv = base / "train.csv"
        if train_csv.exists():
            try:
                with open(train_csv, "rb") as f:
                    header = f.read(8192)
                first_line = header.split(b"\n")[0].decode("utf-8", errors="ignore")
                cols = first_line.strip().split(",")
                file_size = train_csv.stat().st_size
                fingerprint = f"csv_{len(cols)}_{'_'.join(cols[:3])}_{file_size}"
                return hashlib.md5(fingerprint.encode()).hexdigest()[:12]
            except Exception:
                pass

        # Try Parquet
        train_parquet = base / "train.parquet"
        if train_parquet.exists():
            try:
                file_size = train_parquet.stat().st_size
                # Use first 8KB as rough fingerprint (parquet metadata varies)
                with open(train_parquet, "rb") as f:
                    header = f.read(8192)
                fingerprint = f"parquet_{file_size}_{hashlib.md5(header).hexdigest()[:8]}"
                return hashlib.md5(fingerprint.encode()).hexdigest()[:12]
            except Exception:
                pass

    return None


def cache_task_id(task_id: str) -> str:
    """Validate and persist task_id as the session-locked ID."""
    validate_task_id(task_id)
    try:
        TASK_ID_CACHE.parent.mkdir(parents=True, exist_ok=True)
        TASK_ID_CACHE.write_text(task_id, encoding="utf-8")
    except OSError:
        pass
    return task_id


def derive_task_id(data_dir: str = INPUT_DIR, fallback: str = "default_task") -> str:
    """Return a stable task ID, cached for the entire session.

    Priority:
    1. Cached task_id from ./working/.review_experiment_task_id (session lock)
    2. Environment variable TASK_ID
    3. Computed fingerprint from dataset (CSV or Parquet)
    4. Fallback string

    The cache prevents mid-session drift, but a cached fingerprint-derived ID
    is re-derived when the current dataset fingerprint no longer matches
    (i.e. the dataset was swapped for a different task).
    """
    fp = _compute_fingerprint(data_dir)

    # 1. Session cache — trusted unless it is a stale fingerprint-derived ID
    if TASK_ID_CACHE.exists():
        try:
            cached = TASK_ID_CACHE.read_text(encoding="utf-8").strip()
        except OSError:
            cached = ""
        if cached:
            stale = (
                cached.startswith(FINGERPRINT_PREFIX)
                and fp is not None
                and cached != f"{FINGERPRINT_PREFIX}{fp}"
            )
            if not stale:
                return validate_task_id(cached)

    # 2. Environment variable
    env_id = os.environ.get("TASK_ID")
    if env_id:
        return cache_task_id(env_id)

    # 3. Dataset fingerprint
    if fp:
        return cache_task_id(f"{FINGERPRINT_PREFIX}{fp}")

    # 4. Fallback
    return cache_task_id(fallback)


def get_journal_path(task_id: str | None = None) -> Path:
    """Return task-isolated journal path."""
    if not task_id:
        task_id = derive_task_id()
    return WORKING_DIR / validate_task_id(task_id) / "experiment_journal.jsonl"


def ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_entries(journal_path: Path) -> list[dict[str, Any]]:
    if not journal_path.exists():
        return []
    entries = []
    with open(journal_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def append_entry(entry: dict[str, Any], journal_path: Path) -> None:
    ensure_dir(journal_path)
    with open(journal_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def append_md_fallback(entry: dict[str, Any], journal_path: Path) -> None:
    """Append a human-readable entry next to the journal file."""
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

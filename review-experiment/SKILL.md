---
name: review-experiment
description: >-
  Maintain and query the experiment journal for AutoML agents.
  Supports task-isolated journals to prevent cross-task contamination.
  Auto-derives task ID from dataset fingerprint if not provided by environment.
  Provides structured review submission and history retrieval
  to prevent duplicate experiments and track metric evolution.
---

# Review Experiment Skill

This skill equips the agent with a lightweight JSONL-based experiment journal.
Use it to record every experiment outcome and query past results before planning new ones.

**Task Isolation**: The skill automatically derives a stable `task_id` from the dataset fingerprint (column names, column count, file size hash) if the environment does not provide `$TASK_ID`. This ensures experiments are correctly isolated even when the framework does not pass an explicit task identifier.

**Output Protocol**: Scripts print a single JSON object (compact, no pretty-printing) to stdout — parse it directly. Human-readable logs and warnings go to stderr. Failures exit non-zero and print `{"status": "error", "error": "..."}`.

## How to Run (IMPORTANT)

Skill files are **not** on the sandbox filesystem. Do **not** use `run_command("python skills/...")` or `cat skills/...` — they will fail with "No such file or directory". Use the dedicated skill tools instead:

- Execute a script: `run_skill_script(skill_name="review-experiment", file_path="scripts/<name>.py", args={...})`
- Read a reference doc: `load_skill_resource(skill_name="review-experiment", file_path="references/<name>.md")`

Scripts run from a temporary directory that is deleted afterwards, but all persistent state is written to the sandbox work dir (`/work/working/`), so journals survive across calls.

**Paths**: data is read from `/work/train.csv` (override with `INPUT_DIR`), journals go to `/work/working` (override with `WORKING_DIR`). Outside the sandbox the defaults fall back to `./input` and `./working`.

## Available Scripts

### 1. `submit_review.py`
Submit a structured review after every `submit_predictions` or code execution.

**Usage**:
```python
run_skill_script(
    skill_name="review-experiment",
    file_path="scripts/submit_review.py",
    args={
        "submission_id": "sub_1",
        "is_bug": "false",
        "metric": "0.8542",
        "lower_is_better": "false",
        "summary": "LightGBM baseline CV AUC 0.854",
        "tags": '["lightgbm", "baseline"]',
    },
)
```

**Arguments**:
- `--task_id`: Optional. If omitted, auto-derived from the `train.csv` fingerprint or `$TASK_ID` env var.
- `--submission_id`: Submission ID (e.g., `sub_1`) or local run ID.
- `--is_bug`: `true` if execution failed or metric is invalid.
- `--metric`: CV metric value. Use `null` or omit if `is_bug=true`.
- `--lower_is_better`: `true` for RMSE/MAE/LogLoss, `false` for Accuracy/F1/AUC.
- `--summary`: 2-3 sentence empirical finding or bug description.
- `--parent_id`: Parent submission ID for lineage tracking (optional).
- `--tags`: JSON array of tags, e.g., `'["lightgbm", "baseline"]'` (optional).

**Side Effects**:
- Appends to `/work/working/<task_id>/experiment_journal.jsonl`
- Appends to `/work/working/<task_id>/experiment_log.md` (human-readable fallback)
- Warns (but still records) if `submission_id` already exists in the journal
- An explicit `--task_id` is cached to `/work/working/.review_experiment_task_id` to keep later auto-derived calls on the same journal

**Auto-derived task_id**: The script reads the `train.csv` header (first 8KB, looked up in `$INPUT_DIR` — `/work` in the sandbox), hashes column count + first 3 column names + file size. This produces a stable ID for the same dataset across sessions. The ID is cached in the working dir; if the dataset is swapped for a different one, the stale cached ID is discarded and re-derived. Task IDs may only contain letters, digits, `_` and `-`.

### 2. `get_history.py`
Retrieve past experiment reviews before planning a new experiment.

**Usage**:
```python
run_skill_script(
    skill_name="review-experiment",
    file_path="scripts/get_history.py",
    args={"limit": "20", "filter_status": "all"},
)
```

**Arguments**:
- `--task_id`: Optional. If omitted, auto-derived from dataset fingerprint or `$TASK_ID` env var.
- `--limit`: Max entries to return (default: `20`).
- `--filter_status`: `all` | `success` | `buggy` (default: `all`).
- `--tag`: Filter by exact tag match (optional).

**Output**: Compact JSON array printed to stdout for agent consumption.

---

## Domain Knowledge Resources

### `experiment_journal_guide.md`
Guidelines on maintaining an effective experiment journal and avoiding common pitfalls.
Read it with:
```python
load_skill_resource(
    skill_name="review-experiment",
    file_path="references/experiment_journal_guide.md",
)
```

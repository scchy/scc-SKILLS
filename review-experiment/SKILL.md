---
name: review-experiment
description: >-
  Maintain and query the experiment journal for AutoML agents.
  Provides structured review submission and history retrieval
  to prevent duplicate experiments and track metric evolution.
---

# Review Experiment Skill

This skill equips the agent with a lightweight JSONL-based experiment journal.
Use it to record every experiment outcome and query past results before planning new ones.

## Available Scripts

### 1. `submit_review.py`
Submit a structured review after every `submit_predictions` or code execution.

**Usage via `run_skill_script`**:
```python
run_skill_script(
    skill_name="review_experiment",
    script_name="submit_review.py",
    args='--submission_id sub_1 --is_bug false --metric 0.8542 --lower_is_better false --summary "LightGBM baseline CV AUC 0.854" --tags '["lightgbm", "baseline"]'',
)
```

**Arguments**:
- `--submission_id`: Submission ID (e.g., `sub_1`) or local run ID.
- `--is_bug`: `true` if execution failed or metric is invalid.
- `--metric`: CV metric value. Use `null` or omit if `is_bug=true`.
- `--lower_is_better`: `true` for RMSE/MAE/LogLoss, `false` for Accuracy/F1/AUC.
- `--summary`: 2-3 sentence empirical finding or bug description.
- `--parent_id`: Parent submission ID for lineage tracking (optional).
- `--tags`: JSON array of tags, e.g., `'["lightgbm", "baseline"]'` (optional).
- `--journal_path`: Override journal file path (default: `./working/experiment_journal.jsonl`).

**Side Effects**:
- Appends to the journal JSONL (default: `./working/experiment_journal.jsonl`)
- Appends to `experiment_log.md` in the same directory as the journal (human-readable fallback)
- Warns (but still records) if `submission_id` already exists in the journal

### 2. `get_history.py`
Retrieve past experiment reviews before planning a new experiment.

**Usage via `run_skill_script`**:
```python
run_skill_script(
    skill_name="review_experiment",
    script_name="get_history.py",
    args="--limit 10 --filter_status success",
)
```

**Arguments**:
- `--limit`: Max entries to return (default: `20`).
- `--filter_status`: `all` | `success` | `buggy` (default: `all`).
- `--tag`: Filter by exact tag match (optional).
- `--journal_path`: Override journal file path (default: `./working/experiment_journal.jsonl`).

**Output**: JSON array printed to stdout for agent consumption.

---

## Domain Knowledge Resources

### `experiment_journal_guide.md`
Guidelines on maintaining an effective experiment journal and avoiding common pitfalls.
You can read it using the `load_skill_resource` tool:
```python
load_skill_resource(
    skill_name="review_experiment",
    resource_name="experiment_journal_guide.md",
)
```

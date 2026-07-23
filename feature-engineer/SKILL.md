---
name: feature-engineer
description: >-
  Provides a robust Python script for automated, leakage-safe feature generation
  on tabular data. Use when preparing train/test data for modeling — before
  training a baseline. Handles CSV/Parquet I/O, missing value imputation,
  row-level statistics, datetime parts, and categorical encoding — all fit
  on train only.
---

# Feature Engineer Skill

This skill equips the agent with a pre-packaged Python CLI script for automated feature engineering.

**Output Protocol**: The script prints a single JSON summary to stdout — parse it directly. Human-readable logs go to stderr. Failures exit non-zero and print `{"status": "error", "error": "..."}`.

## Usage

### Normal environment (skill files on disk)

```bash
python scripts/generate_features.py --train train.csv --test test.csv --target target --output_dir .
```

Reference docs live under `references/` — just read them.

### ADK / kaggle-kaggle sandbox (skill files NOT on disk)

In harnesses where skills are injected as tools instead of files, `run_command("python skills/...")` and `cat skills/...` fail with "No such file or directory". Use the harness's skill tools instead:

- Execute a script: `run_skill_script(skill_name="feature-engineer", file_path="scripts/<name>.py", args={...})`
- Read a reference doc: `load_skill_resource(skill_name="feature-engineer", file_path="references/<name>.md")`

The script then runs from a temporary directory that is deleted afterwards, so all input/output paths must be **absolute**. The sandbox keeps data at `/work` (e.g. `/work/train.csv`); write outputs to `/work` as well — only files under `/work` persist and are visible to later `run_command` calls.

## Available Scripts

### 1. `generate_features.py`
Automatically identifies column types, imputes missing values, and generates generic features. Everything is **fit on train only** and applied to test (see `leakage_checklist.md`).

**Usage**:
```bash
# On disk:
python scripts/generate_features.py \
    --train train.csv --test test.csv --target target --output_dir .
```
```python
# ADK / kaggle-kaggle sandbox:
run_skill_script(
    skill_name="feature-engineer",
    file_path="scripts/generate_features.py",
    args={
        "train": "/work/train.csv",
        "test": "/work/test.csv",
        "target": "target",
        "output_dir": "/work",
    },
)
```
Omitting `train`/`test`/`output_dir` defaults them to `/work` when it exists, otherwise the current directory.

**Arguments**:
- `--train`: Path to train file, `.csv` or `.parquet` (default: `/work/train.csv` in sandbox).
- `--test`: Path to test file, `.csv` or `.parquet` (default: `/work/test.csv` in sandbox).
- `--target`: Name of the target column (default: `target`).
- `--output_dir`: Directory for engineered outputs (default: same as data dir).
- `--id_cols`: Comma-separated extra columns to keep but exclude from row stats (optional; columns named `id` or `*_id` are excluded automatically).
- `--one_hot_max`: Max unique values for one-hot encoding (default: `10`); higher-cardinality columns get frequency encoding.

**What it generates**:
- `row_nan_count` — per-row missing count, computed *before* imputation (missingness is signal)
- Row-wise numeric stats — `row_mean`, `row_std`, `row_min`, `row_max`, `row_median` (ID-like columns excluded)
- Datetime calendar parts — `<col>_year`, `<col>_month`, `<col>_day`, `<col>_dow` (string columns ≥90% parseable as dates are auto-detected, since CSV loads dates as strings)
- Numeric string promotion — object columns ≥90% parseable as numbers (e.g. `"12.5"`, `"1,000"`) are converted to numeric instead of being encoded as categoricals
- One-hot encoding for low-cardinality categoricals (unseen test categories become all-zero)
- Frequency encoding for high-cardinality categoricals (unseen test categories become 0)

**Outputs**: `train_engineered.<ext>` and `test_engineered.<ext>` in `--output_dir` (extension follows the train input). **Row order and row count are preserved** — outputs can be joined back to the raw files (e.g. to build a submission) by row position. A JSON summary on stdout lists shapes, dropped columns, imputation counts, generated features, auto-detected column conversions, and `warnings` for suspicious columns (constant columns, per-row-unique categoricals that may be disguised IDs).

Task-specific features (group-by aggregations, lags, interactions) are intentionally NOT included — write those yourself based on the data.

---

## Domain Knowledge Resources

### `leakage_checklist.md`
A concise guide on preventing data leakage during feature engineering. On disk, read `references/leakage_checklist.md` directly; in the ADK sandbox:
```python
load_skill_resource(
    skill_name="feature-engineer",
    file_path="references/leakage_checklist.md",
)
```

### `feature_recipes.md`
Code templates for the task-specific features `generate_features.py` intentionally does not generate: group-by aggregations, time-series lags, out-of-fold target encoding, and interactions. On disk, read `references/feature_recipes.md` directly; in the ADK sandbox:
```python
load_skill_resource(
    skill_name="feature-engineer",
    file_path="references/feature_recipes.md",
)
```

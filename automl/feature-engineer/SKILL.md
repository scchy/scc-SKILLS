---
name: feature-engineer
description: >-
  Provides a robust Python script for automated feature generation.
  Handles missing value imputation and numeric aggregations. Use for quick,
  low-risk baseline feature preparation on tabular data.
---

# Feature Engineer Skill

This skill equips the agent with a pre-packaged Python CLI script for automated feature engineering: column-type detection, leakage-safe missing value imputation (fit on train only), and a row-mean aggregation feature. Task-specific features (group-by aggregations, lags, interactions) are intentionally NOT included — write those yourself with custom code.

## Usage

### Normal environment (skill files on disk)

```bash
python scripts/generate_features.py --train train.csv --test test.csv --target target
```

### ADK / kaggle-kaggle sandbox (skill files NOT on disk)

In harnesses where skills are injected as tools instead of files, `run_command("python skills/...")` fails with "No such file or directory". Use `run_skill_script` instead:

```python
run_skill_script(
    skill_name="feature-engineer",
    file_path="scripts/generate_features.py",
    args={"train": "/work/train.csv", "test": "/work/test.csv", "target": "target"},
)
```

The script then runs from a temporary directory that is deleted afterwards — pass **absolute paths**. Omitting `train`/`test`/`output_dir` defaults them to `/work` when it exists, otherwise the current directory.

**Arguments**:
- `--train`: Path to train file, `.csv` (default: `/work/train.csv` in sandbox).
- `--test`: Path to test file, `.csv` (default: `/work/test.csv` in sandbox).
- `--target`: Name of the target column (default: `target`).
- `--output_dir`: Directory for engineered outputs (default: same as data dir).

**Outputs**: `train_engineered.csv` and `test_engineered.csv` in `--output_dir`. Row order and row count are preserved — outputs can be joined back to the raw files by row position.

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
Code templates for the task-specific features this script intentionally does not generate: group-by aggregations, time-series lags, out-of-fold target encoding, and interactions. On disk, read `references/feature_recipes.md` directly; in the ADK sandbox:
```python
load_skill_resource(
    skill_name="feature-engineer",
    file_path="references/feature_recipes.md",
)
```

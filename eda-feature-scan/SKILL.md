---
name: eda-feature-scan
description: Perform exploratory data analysis (EDA) on tabular CSV or Parquet datasets using Polars. Scans numerical, categorical, and cross-categorical feature distributions, then generates encoding maps, fill-na strategies, and standardization parameters for model training. Use when the user needs to analyze feature distributions, generate EDA reports, or prepare feature engineering configs for ML pipelines.
---

# EDA Feature Scan

Two-stage EDA pipeline for tabular data:

1. **Feature Scan** (`parquet_feature_scan.py`): Scans CSV/Parquet files for numerical/categorical/cross-categorical statistics using Polars lazy evaluation
2. **Report Generation** (`generate_eda_report.py`): Produces encoding maps, fill-na strategies, and numerical standardization params from scan results

## How to Run (IMPORTANT)

Skill files are **not** on the sandbox filesystem. Do **not** use `run_command("python skills/...")` or `cat skills/...` — they will fail with "No such file or directory". Use the dedicated skill tools instead:

- Execute a script: `run_skill_script(skill_name="eda-feature-scan", file_path="scripts/<name>.py", args={...})`
- Read a reference doc: `load_skill_resource(skill_name="eda-feature-scan", file_path="references/<name>")`

Path rules under `run_skill_script`:

- The script runs from a temporary directory that is deleted afterwards — **all data input/output paths must be absolute** (`/work/...`). Only files under `/work` persist and are visible to later `run_command` calls.
- The skill's own `references/` and `scripts/` files ARE materialized next to the script, so `--config references/eda.yaml` (relative) works.
- `--data_dir` must contain **only** the file(s) to scan — the scanner unions every CSV/Parquet it finds in the directory. `/work` also holds `test.csv` (no target column) and `sample_submission.csv`, which would break the scan, so stage the input first:

```python
run_command("mkdir -p /work/working/eda_input && cp /work/train.csv /work/working/eda_input/")
```

## Stage 1: Feature Scan

```python
run_skill_script(
    skill_name="eda-feature-scan",
    file_path="scripts/parquet_feature_scan.py",
    args={
        "data_dir": "/work/working/eda_input",
        "output_dir": "/work/working/eda_scan",
        "config": "references/eda.yaml",
        "file_type": "csv",
        "sample_ratio": "1.0",
    },
)
```

**Output files** (in `output_dir`):
- `num_features.json` — numerical stats (mean/std on P1–P99 clipped data)
- `cat_features.json` — categorical distributions and cardinality
- `cross_cat_features.json` — cross-categorical pair statistics

**Arguments**:
- `--data_dir` (required): directory containing input CSV/Parquet files — stage a copy containing only the files to scan (see above)
- `--output_dir` (required): absolute output directory, e.g. `/work/working/eda_scan`
- `--config` (required): YAML config with an `eda_info` section; use `references/eda.yaml` (generic defaults: all columns, no forced types, 0.3 sampling)
- `--file_type`: `csv` or `parquet` (default from config, then auto-detect)
- `--sample_ratio`: sampling ratio (0-1]; use `1.0` for competition-sized data, lower for huge data
- `--streaming` / `--no-streaming`: force Polars streaming engine on/off

## Stage 2: Report Generation

```python
run_skill_script(
    skill_name="eda-feature-scan",
    file_path="scripts/generate_eda_report.py",
    args={
        "num_features": "/work/working/eda_scan/num_features.json",
        "cat_features": "/work/working/eda_scan/cat_features.json",
        "cross_cat_features": "/work/working/eda_scan/cross_cat_features.json",
        "output_dir": "/work/working/eda_output",
    },
)
```

`--cross_cat_features` is optional. `--num_features` and `--cat_features` are required.

**Output files** (in `output_dir`):
- `EDA_report.md` — human-readable analysis report
- `encoding_map.json` — categorical feature label encoding map
- `fill_na_map.json` — missing value fill strategies
- `numerical_stats.json` — mean/std for numerical standardization

These are **advisory references** for the modeling agent — actual imputation/encoding is performed by the `feature-engineer` skill or custom code, which fits its own statistics on train only.

## Configuration

The bundled `references/eda.yaml` is a generic default (scan all columns, no forced categorical types, no cross pairs, `sample_ratio: 0.3`). For dataset-specific scans (exclude IDs/labels, force integer-coded columns to categorical, add cross pairs), read it first with `load_skill_resource(skill_name="eda-feature-scan", file_path="references/eda.yaml")`, then write a customized copy to `/work/working/my_eda.yaml` with `write_file` and pass `--config /work/working/my_eda.yaml`.

Key `eda_info` fields: `features`, `exclude_features`, `force_cat_features`, `city_col`, `cross_cat_pairs`, `file_type`, `use_streaming`, `num_stats_batch_size`, `sample_ratio`.

## Key Design Decisions

- **Streaming mode**: Auto-enabled for >500M rows. Use `--streaming` or `--no-streaming` to override
- **Sampling**: `--sample_ratio 0.1` scans only 10% of files for quick exploration
- **Memory safety**: High-cardinality categoricals (>5M unique) skip top-N details; cross-cat pairs >10M combinations are skipped
- **Quantile computation**: `mean`/`std` are computed on `[P1, P99]` clipped data (robust to outliers)

## Troubleshooting

- **Segmentation fault (exit 139)**: Reduce `num_stats_batch_size` to 1, enable `--streaming`, or use `--sample_ratio 0.1`
- **OOM on cross-cat stats**: Reduce features in `cross_cat_pairs` or increase sampling
- **Slow scan**: Use `--sample_ratio 0.1` for quick exploration, then full run for production
- **Schema mismatch error**: `--data_dir` contains files with different columns (e.g. `test.csv` without target) — stage only `train.csv` as described above

For detailed API reference, see `references/reference.md` (via `load_skill_resource`).

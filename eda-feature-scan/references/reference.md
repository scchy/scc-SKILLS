# EDA Feature Scan - API Reference

## parquet_feature_scan.py

### Core Functions

#### `scan_data_files(data_dir, file_type="parquet", pattern=None, recursive=True) -> list[Path]`
Scans directory for Parquet or CSV files. Supports recursive search for nested date subdirectories.

#### `scan_parquet_files(data_dir, pattern="*.parquet", recursive=True) -> list[Path]`
Backward-compatible wrapper that scans directory for Parquet files.

#### `build_lazy_frame(files, columns=None, file_type="parquet") -> pl.LazyFrame`
Creates a LazyFrame from Parquet or CSV files. Uses `pl.scan_parquet()` or `pl.scan_csv()` with direct file list (avoids concat query tree bloat). CSV uses `infer_schema_length=100_000` for robust dtype detection.

#### `summarize_features(files, features, exclude_features, force_cat_features, city_col, cross_cat_pairs, file_type="parquet", ...) -> tuple`
Main orchestration function. Returns `(cat_feature, num_feature, cross_cat)`.

**Parameters:**
- `features`: List of columns to scan (None = all columns)
- `exclude_features`: Columns to skip (IDs, timestamps, labels)
- `force_cat_features`: Columns to treat as categorical regardless of dtype
- `city_col`: Column for per-city median calculation (e.g., "city_code")
- `cross_cat_pairs`: List of pairs `[["cat_a", "cat_b"], ...]`
- `file_type`: Input file type, `"parquet"` or `"csv"` (default: `"parquet"`)
- `use_streaming`: None=auto (>500M rows), True/False to force
- `num_stats_batch_size`: Numerical stats batch size (1=safest)
- `city_median_batch_size`: City median batch size
- `sample_ratio`: EDA sampling ratio (0-1), default 0.3

#### `compute_num_stats_batch(lf, features, total_rows, batch_size, pbar) -> dict`
Batch-computes numerical statistics. Two-phase collect:
1. First collect: base stats (null_count, nunique, min, max, zero_count, median, quantiles P1-P99)
2. Second collect: mean/std on [P1, P99] clipped data using constants from phase 1

This two-phase approach prevents Polars segfault on >1B row datasets caused by nested quantile+filter in a single collect.

#### `compute_cat_stats(lf, feature, total_rows, precomputed_base) -> dict`
Categorical feature statistics with memory safety:
- Skips top-N details if nunique > 5,000,000
- Collects up to 1000 top items, truncates at 30 items with 95% cumulative coverage

#### `compute_city_medians_batch(lf, features, city_col, batch_size) -> dict`
Per-city median for numerical features (used for missing value imputation reference).

#### `compute_cross_cat_stats(lf, cat_a, cat_b, coverage=0.95, max_combinations=10M) -> dict`
Cross-categorical distribution. Collects two columns, then group_by+sort. Skips if combinations > 10M.

### Output JSON Schema

#### num_features.json
```json
{
  "feature_name": {
    "nunique": 1234,
    "null_count": 100,
    "null_ratio": 0.001,
    "zero_count": 500,
    "zero_ratio": 0.005,
    "mean": 10.5,
    "median": 8.0,
    "std": 5.2,
    "min": 0.0,
    "max": 999.0,
    "P1": 0.5, "P10": 2.0, "P25": 4.0, "P50": 8.0,
    "P75": 12.0, "P90": 20.0, "P99": 100.0,
    "city_median": {"city_1": 7.5, "city_2": 9.0}
  }
}
```

#### cat_features.json
```json
{
  "feature_name": {
    "nunique": 50,
    "null_count": 10,
    "null_ratio": 0.0001,
    "top30_items": {"cat_val_1": 100000, "cat_val_2": 50000},
    "top30_ratios": {"cat_val_1": 0.3, "cat_val_2": 0.15},
    "top30_items_skipped": false,
    "actual_coverage": 0.95,
    "items_collected": 30
  }
}
```

#### cross_cat_features.json
```json
{
  "cat_a__x__cat_b": {
    "cat_a_value_1": {"cat_b_value_1": 0.3, "cat_b_value_2": 0.2},
    "cat_a_value_2": {"cat_b_value_1": 0.1}
  }
}
```

---

## generate_eda_report.py

### EDAReportGenerator Class

#### `__init__(num_features_path, cat_features_path, cross_cat_features_path)`
Loads JSON scan results.

#### `analyze_features() -> dict`
Analyzes features and generates recommendations:
- Drop features with null_ratio > 0.9, single-value, or zero_ratio > 0.95
- Embedding dimension suggestions based on nunique:
  - <=10: min(4, nunique)
  - <=50: min(8, nunique)
  - <=100: min(16, nunique)
  - >100: min(32, sqrt(nunique))

#### `generate_encoding_map() -> dict`
Label encoding for categorical features. Assigns sequential IDs to top items, with "OTH"=0 for rare categories. Handles cross-categorical features with parent-child encoding.

#### `generate_fill_na_map() -> dict`
Missing value strategies:
- Numerical: median (0 if all zeros)
- Categorical: mode (most frequent category)

#### `generate_numeric_std_mean() -> dict`
Standardization parameters (mean/std) for each numerical feature.

#### `generate_markdown_report(analysis) -> str`
Human-readable EDA report with data overview, quality analysis, and modeling recommendations.

#### `save_outputs(output_dir) -> None`
Saves all outputs:
- `EDA_report.md`
- `encoding_map.json`
- `fill_na_map.json`
- `numerical_stats.json`

---

## Configuration Reference (eda.yaml)

```yaml
eda_info:
  # Required: Feature columns to analyze
  features:
    - feature_1
    - feature_2

  # Optional: Columns to exclude
  exclude_features:
    - id
    - dt
    - label

  # Optional: Force integer columns as categorical
  force_cat_features:
    - city_code
    - is_rain

  # Optional: City column for per-city median
  city_col: city_code

  # Optional: Cross-categorical pairs
  cross_cat_pairs:
    - ["city_code", "region_code"]

  # Optional: Input file type (parquet or csv; null=auto-detect)
  file_type: parquet

  # Optional: Streaming engine (null=auto for >500M rows)
  use_streaming: null

  # Optional: Batch sizes (lower=safer, higher=faster)
  num_stats_batch_size: 1
  city_median_batch_size: 1

  # Optional: Sampling ratio (0-1)
  sample_ratio: 0.3
```

---

## Performance Tuning Guide

| Data Size | Recommended Settings |
|-----------|---------------------|
| <100M rows | Default, `num_stats_batch_size=3` |
| 100M-500M | `num_stats_batch_size=1`, `sample_ratio=0.5` |
| 500M-1B | `--streaming`, `sample_ratio=0.3` |
| >1B rows | `--streaming`, `sample_ratio=0.1-0.2`, `num_stats_batch_size=1` |

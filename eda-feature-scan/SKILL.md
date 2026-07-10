---
name: eda-feature-scan
description: Perform exploratory data analysis (EDA) on large-scale Parquet or CSV datasets using Polars. Scans numerical, categorical, and cross-categorical feature distributions, then generates encoding maps, fill-na strategies, and standardization parameters for model training. Use when the user needs to analyze feature distributions in Parquet/CSV data, generate EDA reports, or prepare feature engineering configs for ML pipelines.
---

# EDA Feature Scan

## Overview

Two-stage EDA pipeline for large-scale Parquet/CSV data (tested on 1.5B+ rows):

1. **Feature Scan** (`parquet_feature_scan.py`): Scans Parquet/CSV files for numerical/categorical/cross-categorical statistics using Polars lazy evaluation
2. **Report Generation** (`generate_eda_report.py`): Produces encoding maps, fill-na strategies, and numerical standardization params from scan results

## Quick Start

### Prerequisites

```bash
pip install polars pandas pyarrow openpyxl pyyaml tqdm
```

### Stage 1: Feature Scan

```bash
# Via shell wrapper (recommended)
bash scripts/run_feature_scan.sh \
    -d /path/to/parquet_data \
    -o /path/to/eda_output \
    -c configs/eda.yaml

# CSV input
bash scripts/run_feature_scan.sh \
    -d /path/to/csv_data \
    -o /path/to/eda_output \
    -c configs/eda.yaml \
    -t csv

# Via Python directly
python scripts/parquet_feature_scan.py \
    --data_dir /path/to/parquet_data \
    --output_dir /path/to/eda_output \
    --config configs/eda.yaml \
    --sample_ratio 0.3

# CSV via Python directly
python scripts/parquet_feature_scan.py \
    --data_dir /path/to/csv_data \
    --output_dir /path/to/eda_output \
    --config configs/eda.yaml \
    --file_type csv
```

**Output files:**
- `num_features.json` / `num_features.xlsx` - Numerical feature stats
- `cat_features.json` / `cat_features.xlsx` - Categorical feature stats
- `cross_cat_features.json` / `cross_cat_features.xlsx` - Cross-categorical stats

### Stage 2: Report Generation

```bash
bash scripts/run_generate_eda_report.sh \
    -n /path/to/eda_output/num_features.json \
    -c /path/to/eda_output/cat_features.json \
    -x /path/to/eda_output/cross_cat_features.json \
    -o /path/to/encoder_output
```

**Output files:**
- `EDA_report.md` - Human-readable analysis report
- `encoding_map.json` - Categorical feature label encoding map
- `fill_na_map.json` - Missing value fill strategies
- `numerical_stats.json` - Mean/std for numerical standardization

## Configuration

YAML config with `eda_info` section. See `configs/eda.yaml` for full example.

Key fields:

```yaml
eda_info:
  features: [...]          # Feature columns to scan (optional, None=all)
  exclude_features: [...]  # Columns to exclude (IDs, timestamps, labels)
  force_cat_features: [...] # Force treat as categorical (integer-encoded cats)
  city_col: city_code      # Column for per-city median calculation
  cross_cat_pairs:         # Cross-categorical pairs to analyze
    - ["city_code", "order_start_lv7h3"]
  file_type: parquet       # parquet or csv; null=auto-detect
  use_streaming: null      # null=auto, true/false to force
  num_stats_batch_size: 1  # Batch size for numerical stats (lower=safer)
  city_median_batch_size: 1
  sample_ratio: 0.3        # EDA sampling ratio (0-1)
```

## Key Design Decisions

### Large Data Safety

- **Streaming mode**: Auto-enabled for >500M rows. Use `--streaming` or `--no-streaming` to override
- **Batch processing**: Numerical stats computed in batches (default 1 per batch for max stability)
- **Sampling**: `--sample_ratio 0.1` scans only 10% of files for quick exploration
- **Memory safety**: High-cardinality categoricals (>5M unique) skip top-N details; cross-cat pairs >10M combinations are skipped

### Quantile Computation

Numerical `mean`/`std` are computed on `[P1, P99]` clipped data (robust to outliers). This is done in two separate `collect()` calls to avoid Polars segfault on >1B row datasets.

## Parameters Reference

### run_feature_scan.sh

| Flag | Description | Default |
|------|-------------|---------|
| `-d, --data` | Parquet/CSV data directory | `$PROJ_ROOT/data/sample_data` |
| `-t, --file-type` | Input file type: `parquet` or `csv` | Auto-detect, fallback `parquet` |
| `-o, --output` | Output directory | `$PROJ_ROOT/data_engineering/eda/output/feature_summary` |
| `-c, --config` | EDA config YAML | `configs/eda.yaml` |
| `-s, --sample-ratio` | Sampling ratio 0-1 | From config or 0.3 |

### parquet_feature_scan.py

| Flag | Description |
|------|-------------|
| `--data_dir` | Parquet/CSV data directory (required) |
| `--file_type` | Input file type: `parquet` or `csv` (optional) |
| `--output_dir` | Output directory (required) |
| `--config` | Config YAML with `eda_info` (required) |
| `--streaming` | Force Polars streaming engine |
| `--no-streaming` | Force in-memory engine |
| `--sample_ratio` | Override config sample ratio |

## Full Pipeline Example

```bash
# 1. Scan features (parquet)
bash scripts/run_feature_scan.sh \
    -d /data/parquet_dir \
    -o /output/eda_scan \
    -c configs/eda.yaml

# 1. Scan features (csv)
bash scripts/run_feature_scan.sh \
    -d /data/csv_dir \
    -o /output/eda_scan \
    -c configs/eda.yaml \
    -t csv

# 2. Generate encoder configs
bash scripts/run_generate_eda_report.sh \
    -n /output/eda_scan/num_features.json \
    -c /output/eda_scan/cat_features.json \
    -x /output/eda_scan/cross_cat_features.json \
    -o /output/encoder
```

## Troubleshooting

- **Segmentation fault (exit 139)**: Reduce `num_stats_batch_size` to 1, enable `--streaming`, or use `--sample_ratio 0.1`
- **OOM on cross-cat stats**: Reduce features in `cross_cat_pairs` or increase sampling
- **Slow scan**: Use `--sample_ratio 0.1` for quick exploration, then full run for production

For detailed API reference, see [reference.md](reference.md).

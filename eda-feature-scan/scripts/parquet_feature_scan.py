#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Create Date: 2026-04-15
# Author: ChengChao.Sun + Kimi2.5
# Function: Streaming feature distribution statistics aggregation tool (optimized)
"""
Streaming feature distribution statistics aggregation tool (optimized).

Optimizations:
1. Categorical features
    - Unique value count
    - Null count and ratio
    - Top-30 frequencies (and ratios), dynamically adjusted by cumulative coverage
      (at least 30 until 95% coverage)
2. Numerical features
    - Unique value count
    - Null count and ratio
    - Zero count and ratio
    - Mean, median, std, min, max
    - Batch quantiles (P1, P10, P25, P50, P75, P90, P99)
    - Per-city median based on city_code (for missing value imputation reference)
3. Cross-categorical statistics
    - Cross-counts of two categorical features, keeping items with 95% cumulative
      coverage per cat_a
4. Performance and memory safety optimizations (for 1B+ rows)
    - Batch collect for numerical/categorical base stats to reduce IO
    - Per-city medians aggregated in batches
    - Cross stats use pure Polars window functions, avoiding pandas conversion
      and Python-level loops
    - Key large queries enable streaming mode by default to reduce memory peaks
    - Add nunique safety thresholds for categorical top-N and cross stats to
      prevent high-cardinality OOM
    - Rebuild LazyFrame after determining target columns, reading only required columns
"""
# ============================================================================================================================
from __future__ import annotations

import argparse
import gc
import json
import logging
import random
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl
import yaml
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration constants
QUANTILES = [0.01, 0.10, 0.25, 0.50, 0.75, 0.90, 0.99]
QUANTILE_NAMES = ["P1", "P10", "P25", "P50", "P75", "P90", "P99"]

# Enable streaming mode by default above this threshold to avoid Polars query plan
# complexity crashes in non-streaming mode.
# Even with the default 30% sampling, large tables may still have hundreds of
# millions of rows, so the threshold should not be too high.
LARGE_DATASET_THRESHOLD = 100_000_000


def _collect(lf: pl.LazyFrame, streaming: bool = False) -> pl.DataFrame:
    """Unified collect entry point.

    Streaming mode is recommended only for large tables (>1e9 rows) with tight
    memory; it is disabled by default to avoid scheduling overhead and unusually
    high CPU usage.
    """
    try:
        if streaming:
            return lf.collect(engine="streaming")
        return lf.collect()
    except TypeError:
        return lf.collect()


def _collect_safe(lf: pl.LazyFrame, streaming: bool = False, description: str = "") -> pl.DataFrame:
    """Collect entry point with fallback.

    Use streaming mode directly when streaming=True; otherwise try non-streaming
    first, and fall back to streaming mode once if a Python-level exception occurs.
    Note: Low-level segmentation faults such as SIGSEGV cannot be caught by Python,
    so for ultra-large datasets pass streaming=True directly.
    """
    if streaming:
        return _collect(lf, streaming=True)
    try:
        return _collect(lf, streaming=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "collect failed (%s), retrying with streaming mode: %s",
            description or "unknown",
            exc,
        )
        return _collect(lf, streaming=True)


def scan_data_files(
    data_dir: Path,
    file_type: str = "parquet",
    pattern: str | None = None,
    recursive: bool = True,
) -> list[Path]:
    """Scan all data files in directory and sort by filename.

    Args:
        data_dir: root data directory
        file_type: "parquet" or "csv"
        pattern: file match pattern (default: *.{file_type})
        recursive: whether to scan subdirectories recursively, default True
                   (for multi-level date subdirectory structures)
    """
    file_type = file_type.lower()
    if file_type not in ("parquet", "csv"):
        raise ValueError(f"Unsupported file_type: {file_type}, only 'parquet' and 'csv' are supported")
    if pattern is None:
        pattern = f"*.{file_type}"
    if recursive:
        files = sorted(data_dir.rglob(pattern))
    else:
        files = sorted(data_dir.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No {file_type} files matching {pattern} found in directory {data_dir}")
    return files


def scan_parquet_files(data_dir: Path, pattern: str = "*.parquet", recursive: bool = True) -> list[Path]:
    """Backward-compatible wrapper for scanning parquet files."""
    return scan_data_files(data_dir, file_type="parquet", pattern=pattern, recursive=recursive)


def sample_files(files: list[Path], sample_ratio: float, seed: int = 42) -> list[Path]:
    """Sample at parquet file level to avoid LazyFrame.sample compatibility issues.

    Accelerates the EDA phase: randomly sample a fraction of files, compatible
    with all Polars versions, coexists with streaming mode, and usually still
    represents the overall distribution.
    """
    if sample_ratio >= 1.0 or not files:
        return files

    random.seed(seed)
    k = max(1, int(len(files) * sample_ratio))
    sampled = random.sample(files, k)
    return sorted(sampled)


def build_lazy_frame(
    files: list[Path],
    columns: list[str] | None = None,
    file_type: str = "parquet",
) -> pl.LazyFrame:
    """Create LazyFrame from file list (pass list directly to avoid explicit concat query tree bloat).

    Supports both Parquet and CSV inputs.
    """
    file_type = file_type.lower()
    if file_type == "parquet":
        lf = pl.scan_parquet([str(f) for f in files])
    elif file_type == "csv":
        # Use a large schema inference sample for robust dtype detection on wide CSVs.
        lf = pl.scan_csv([str(f) for f in files], infer_schema_length=100_000)
    else:
        raise ValueError(f"Unsupported file_type: {file_type}, only 'parquet' and 'csv' are supported")
    if columns:
        lf = lf.select(columns)
    return lf


def is_numeric_dtype(dtype: pl.DataType) -> bool:
    """Check whether dtype is numeric (integer, float, Decimal)."""
    return dtype.is_numeric()


def is_categorical_dtype(dtype: pl.DataType) -> bool:
    """Check whether dtype is categorical (string, boolean, categorical)."""
    return dtype in (pl.String, pl.Boolean, pl.Categorical, pl.Enum)


def compute_cat_stats(
    lf: pl.LazyFrame,
    feature: str,
    total_rows: int,
    max_items_hard: int = 100_000,
    precomputed_base: tuple[int, int] | None = None,
    nunique_safe_threshold: int = 5_000_000,
) -> dict[str, Any]:
    """Perform one-shot aggregation statistics for categorical features (memory-safe).

    Perform only one collect to fetch a safe top limit (default 1000), then truncate
    in Python to avoid repeated group_by+sort from progressive limits.
    If nunique exceeds the safety threshold, skip top-N detail statistics.
    """
    if precomputed_base is not None:
        null_count, nunique = precomputed_base
    else:
        agg_df = _collect(
            lf.select(
                [
                    pl.col(feature).null_count().alias("null_count"),
                    pl.col(feature).n_unique().alias("nunique"),
                ]
            )
        )
        null_count = int(agg_df["null_count"][0])
        nunique = int(agg_df["nunique"][0])

    # Skip details for ultra-high cardinality to prevent group_by OOM
    if nunique > nunique_safe_threshold:
        logger.warning(
            "Column '%s' cardinality too high (nunique=%d > %d), skipping top-N detail statistics",
            feature,
            nunique,
            nunique_safe_threshold,
        )
        return {
            "nunique": nunique,
            "null_count": null_count,
            "null_ratio": null_count / total_rows,
            "top30_items": {},
            "top30_ratios": {},
            "top30_items_skipped": True,
        }

    # Fetch a safe upper limit in one go to avoid repeated collects
    safe_limit = min(nunique, max_items_hard, 1_000)
    vc_df = _collect(
        lf.filter(pl.col(feature).is_not_null())
        .group_by(feature)
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
        .limit(safe_limit)
        .with_columns((pl.col("count") / total_rows).alias("count_ratio"))
    )

    top_items: dict[str, int] = {}
    top_ratios: dict[str, float] = {}
    cumulative_ratio = 0.0
    stop_idx = 0

    for idx, row in enumerate(vc_df.iter_rows(named=True)):
        key = str(row[feature])
        ratio = float(row["count_ratio"])
        top_items[key] = int(row["count"])
        top_ratios[key] = ratio
        cumulative_ratio += ratio
        stop_idx = idx + 1
        if idx + 1 >= 30 and cumulative_ratio >= 0.95:
            break

    # If 1000 items are not enough for 95%, do not expand further (computational cost far outweighs benefit under high cardinality)
    return {
        "nunique": nunique,
        "null_count": null_count,
        "null_ratio": null_count / total_rows,
        "top30_items": top_items,
        "top30_ratios": top_ratios,
        "top30_items_skipped": False,
        "actual_coverage": cumulative_ratio,
        "items_collected": stop_idx,
    }


def compute_cat_base_batch(
    lf: pl.LazyFrame,
    features: list[str],
    batch_size: int = 10,
) -> dict[str, tuple[int, int]]:
    """Batch-compute categorical feature base metadata (null_count, nunique), reducing query plan complexity by batch."""
    if not features:
        return {}
    result: dict[str, tuple[int, int]] = {}
    for i in range(0, len(features), batch_size):
        batch = features[i : i + batch_size]
        exprs = []
        for feature in batch:
            exprs.extend(
                [
                    pl.col(feature).null_count().alias(f"{feature}__null_count"),
                    pl.col(feature).n_unique().alias(f"{feature}__nunique"),
                ]
            )
        df = _collect(lf.select(exprs))
        row = df.row(0, named=True)
        for feature in batch:
            result[feature] = (
                int(row[f"{feature}__null_count"]),
                int(row[f"{feature}__nunique"]),
            )
    return result


def compute_num_stats(lf: pl.LazyFrame, feature: str, total_rows: int) -> dict[str, Any]:
    """Perform one-shot aggregation statistics for numerical features (including batch quantiles)."""
    base_exprs = [
        pl.col(feature).null_count().alias("null_count"),
        pl.col(feature).n_unique().alias("nunique"),
        pl.col(feature).mean().alias("mean"),
        pl.col(feature).median().alias("median"),
        pl.col(feature).std().alias("std"),
        pl.col(feature).min().alias("min"),
        pl.col(feature).max().alias("max"),
        (pl.col(feature) == 0).sum().alias("zero_count"),
    ]

    # Batch quantiles
    quantile_exprs = [
        pl.col(feature).quantile(q, interpolation="linear").alias(name)
        for q, name in zip(QUANTILES, QUANTILE_NAMES)
    ]

    df = _collect(lf.select(base_exprs + quantile_exprs))
    row = df.row(0, named=True)

    null_count = int(row["null_count"])
    zero_count = int(row["zero_count"])

    result: dict[str, Any] = {
        "nunique": int(row["nunique"]),
        "null_count": null_count,
        "null_ratio": null_count / total_rows,
        "zero_count": zero_count,
        "zero_ratio": zero_count / total_rows,
        "mean": float(row["mean"]) if row["mean"] is not None else None,
        "median": float(row["median"]) if row["median"] is not None else None,
        "std": float(row["std"]) if row["std"] is not None else None,
        "min": float(row["min"]) if row["min"] is not None else None,
        "max": float(row["max"]) if row["max"] is not None else None,
    }

    for name in QUANTILE_NAMES:
        val = row[name]
        result[name] = float(val) if val is not None else None

    return result


def _compute_num_stats_single(
    lf: pl.LazyFrame,
    feature: str,
    total_rows: int,
    use_streaming: bool = False,
) -> dict[str, Any]:
    """Compute base statistics for a single numerical feature (internal implementation).

    For ultra-large datasets with 1B+ rows, batch>1 may make Polars query plans too
    complex and trigger Segmentation fault. Here we process one column at a time and
    automatically fall back to streaming mode on failure.
    """
    # ---- First collect: base stats + all quantiles (no nested filter) ----
    base_exprs = [
        pl.col(feature).null_count().alias(f"{feature}__null_count"),
        pl.col(feature).n_unique().alias(f"{feature}__nunique"),
        pl.col(feature).min().alias(f"{feature}__min"),
        pl.col(feature).max().alias(f"{feature}__max"),
        (pl.col(feature) == 0).sum().alias(f"{feature}__zero_count"),
        pl.col(feature).median().alias(f"{feature}__median"),
    ]
    for q, name in zip(QUANTILES, QUANTILE_NAMES):
        base_exprs.append(
            pl.col(feature).quantile(q, interpolation="linear").alias(f"{feature}__{name}")
        )
    base_df = _collect_safe(lf.select(base_exprs), streaming=use_streaming, description=f"num base {feature}")
    base_row = base_df.row(0, named=True)

    # ---- Second collect: compute mean/std after clipping by P1/P99 ----
    p1_val = base_row[f"{feature}__P1"]
    p99_val = base_row[f"{feature}__P99"]
    if p1_val is not None and p99_val is not None:
        clipped_df = _collect_safe(
            lf.select([
                pl.col(feature)
                .filter((pl.col(feature) >= p1_val) & (pl.col(feature) <= p99_val))
                .mean()
                .alias(f"{feature}__mean"),
                pl.col(feature)
                .filter((pl.col(feature) >= p1_val) & (pl.col(feature) <= p99_val))
                .std()
                .alias(f"{feature}__std"),
            ]),
            streaming=use_streaming,
            description=f"num clipped {feature}",
        )
        clipped_row = clipped_df.row(0, named=True)
    else:
        clipped_row = {f"{feature}__mean": None, f"{feature}__std": None}

    null_count = int(base_row[f"{feature}__null_count"])
    zero_count = int(base_row[f"{feature}__zero_count"])
    result: dict[str, Any] = {
        "nunique": int(base_row[f"{feature}__nunique"]),
        "null_count": null_count,
        "null_ratio": null_count / total_rows,
        "zero_count": zero_count,
        "zero_ratio": zero_count / total_rows,
        "mean": float(clipped_row[f"{feature}__mean"]) if clipped_row[f"{feature}__mean"] is not None else None,
        "median": float(base_row[f"{feature}__median"]) if base_row[f"{feature}__median"] is not None else None,
        "std": float(clipped_row[f"{feature}__std"]) if clipped_row[f"{feature}__std"] is not None else None,
        "min": float(base_row[f"{feature}__min"]) if base_row[f"{feature}__min"] is not None else None,
        "max": float(base_row[f"{feature}__max"]) if base_row[f"{feature}__max"] is not None else None,
    }
    for name in QUANTILE_NAMES:
        val = base_row[f"{feature}__{name}"]
        result[name] = float(val) if val is not None else None
    return result


def compute_num_stats_batch(
    lf: pl.LazyFrame,
    features: list[str],
    total_rows: int,
    batch_size: int = 1,
    pbar: tqdm | None = None,
    use_streaming: bool = False,
) -> dict[str, dict[str, Any]]:
    """Batch-compute numerical feature base statistics to reduce collect calls.

    Default batch_size=1, process each column independently and automatically fall
    back to streaming mode, avoiding Segmentation faults from overly complex query
    plans in 1B+ rows / thousands of parquet files scenarios.
    If a column still fails, it is skipped and logged instead of crashing the whole task.
    """
    if not features:
        return {}
    result: dict[str, dict[str, Any]] = {}
    failed_features: list[str] = []
    for i in range(0, len(features), batch_size):
        batch = features[i : i + batch_size]
        for feature in batch:
            try:
                result[feature] = _compute_num_stats_single(lf, feature, total_rows, use_streaming=use_streaming)
            except Exception as exc:  # noqa: BLE001
                logger.error("Numerical feature '%s' statistics failed: %s", feature, exc)
                failed_features.append(feature)
            gc.collect()
        if pbar is not None:
            pbar.update(len(batch))
    if failed_features:
        logger.warning("%d numerical features failed statistics: %s", len(failed_features), failed_features)
    return result


def compute_city_median(
    lf: pl.LazyFrame, feature: str, city_col: str = "city_code"
) -> dict[str, float]:
    """Compute per-city median for numerical features, used as reference for missing value imputation."""
    df = _collect(
        lf.filter(pl.col(feature).is_not_null() & pl.col(city_col).is_not_null())
        .group_by(city_col)
        .agg(pl.col(feature).median().alias("median"))
    )
    result: dict[str, float] = {}
    for row in df.iter_rows(named=True):
        city = str(row[city_col])
        med = row["median"]
        result[city] = float(med) if med is not None else None
    return result


def compute_city_medians_batch(
    lf: pl.LazyFrame,
    features: list[str],
    city_col: str = "city_code",
    batch_size: int = 1,
    pbar: tqdm | None = None,
    use_streaming: bool = False,
) -> dict[str, dict[str, float]]:
    """Batch-compute per-city medians for numerical features.

    Default batch_size=1 to reduce single-query complexity on ultra-large datasets,
    with streaming fallback per column. Failed columns are skipped and logged, not
    crashing the overall task.
    """
    result: dict[str, dict[str, float]] = {f: {} for f in features}
    failed_features: list[str] = []
    for i in range(0, len(features), batch_size):
        batch = features[i : i + batch_size]
        for feat in batch:
            try:
                df = _collect_safe(
                    lf.filter(pl.col(city_col).is_not_null())
                    .group_by(city_col)
                    .agg(pl.col(feat).median().alias(feat)),
                    streaming=use_streaming,
                    description=f"city median {feat}",
                )
                city_meds: dict[str, float] = {}
                for row in df.iter_rows(named=True):
                    city = str(row[city_col])
                    med = row[feat]
                    city_meds[city] = float(med) if med is not None else None
                result[feat] = city_meds
            except Exception as exc:  # noqa: BLE001
                logger.error("Per-city median '%s' computation failed: %s", feat, exc)
                failed_features.append(feat)
            gc.collect()
        if pbar is not None:
            pbar.update(len(batch))
    if failed_features:
        logger.warning("%d per-city median computations failed: %s", len(failed_features), failed_features)
    return result


def compute_cross_cat_stats(
    lf: pl.LazyFrame,
    cat_a: str,
    cat_b: str,
    coverage: float = 0.95,
    max_combinations: int = 10_000_000,
) -> dict[str, dict[str, float]]:
    """Compute cross-counts of two categorical features and keep items covering cumulative_ratio per cat_a.

    First collect two columns, then use group_by+agg+sort to get counts and sort
    globally descending, finally cumsum-truncate by cat_a in Python to avoid window
    functions. If actual combination count exceeds the safety threshold, skip directly
    to prevent OOM.
    """
    # Safety threshold check: directly compute actual unique combination count of (cat_a, cat_b) in data
    real_comb = int(
        _collect(
            lf.filter(pl.col(cat_a).is_not_null() & pl.col(cat_b).is_not_null())
            .select(
                pl.concat_str([pl.col(cat_a), pl.lit("::"), pl.col(cat_b)])
                .n_unique()
                .alias("n_comb")
            )
        )["n_comb"][0]
    )
    if real_comb > max_combinations:
        logger.warning(
            "Cross stats %s x %s actual combinations %d > %d, skipping to prevent OOM",
            cat_a,
            cat_b,
            real_comb,
            max_combinations,
        )
        return {}

    # After collecting two columns, use group_by+agg+sort, equivalent to value_counts
    df = _collect(
        lf.filter(pl.col(cat_a).is_not_null() & pl.col(cat_b).is_not_null())
        .select([cat_a, cat_b])
    )
    vc = df.group_by([cat_a, cat_b]).agg(pl.len().alias("count")).sort("count", descending=True)

    result: dict[str, dict[str, float]] = {}
    partitions = vc.partition_by(cat_a, as_dict=True)
    for a_val, sub in partitions.items():
        a_key = str(a_val[0]) if isinstance(a_val, tuple) else str(a_val)
        total = sub["count"].sum()
        cumsum = 0.0
        part_result: dict[str, float] = {}
        for row in sub.iter_rows(named=True):
            b_key = str(row[cat_b])
            ratio = float(row["count"]) / total
            part_result[b_key] = ratio
            cumsum += ratio
            if cumsum >= coverage:
                break
        result[a_key] = part_result
    return result


def summarize_features(
    files: list[Path],
    features: list[str] | None = None,
    exclude_features: list[str] | None = None,
    force_cat_features: list[str] | None = None,
    city_col: str | None = None,
    cross_cat_pairs: list[list[str]] | None = None,
    use_streaming: bool | None = None,
    num_stats_batch_size: int = 1,
    city_median_batch_size: int = 1,
    sample_ratio: float = 0.3,
    file_type: str = "parquet",
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, dict[str, float]]]]:
    """
    Aggregate statistics for all features.

    Args:
        files: list of data file paths (parquet or csv)
        features: columns to analyze, None means all
        exclude_features: columns to exclude (e.g., ID, timestamp, etc.)
        force_cat_features: column names forced as categorical (e.g., integer-encoded category IDs)
        city_col: column used for per-city median, None means skip
        cross_cat_pairs: list of categorical pairs for cross stats, e.g., [["city_code", "lv7H3"]]
        use_streaming: whether to force Polars streaming mode; None means auto by data size
        num_stats_batch_size: numerical stats batch size (default 1, increase for speed)
        city_median_batch_size: per-city median batch size (default 1, increase for speed)
        sample_ratio: sampling ratio (0-1) to accelerate EDA; default 0.3
        file_type: input file type, "parquet" or "csv" (default: parquet)

    Returns:
        (cat_feature_dict, num_feature_dict, cross_cat_dict)
    """
    if not (0 < sample_ratio <= 1.0):
        raise ValueError(f"sample_ratio must be in (0, 1], current value: {sample_ratio}")

    # Sampling accelerates EDA (sample parquet files, compatible with all Polars versions and supports streaming)
    if sample_ratio < 1.0:
        original_count = len(files)
        files = sample_files(files, sample_ratio)
        logger.info(
            "EDA sampling enabled: %.1f%% | %s files: %d -> %d",
            sample_ratio * 100,
            file_type,
            original_count,
            len(files),
        )

    # Step 1: Read metadata only to get schema
    lf_meta = build_lazy_frame(files, file_type=file_type)
    if hasattr(lf_meta, "collect_schema"):
        schema = lf_meta.collect_schema()  # type: ignore[operator]
        all_columns = list(schema.names())
    else:
        schema = lf_meta.schema
        all_columns = list(schema.keys())

    if features is not None:
        all_columns = [c for c in all_columns if c in features]
    if exclude_features:
        all_columns = [c for c in all_columns if c not in exclude_features]

    if not all_columns:
        raise ValueError("No available feature columns for statistics")

    # Step 2: Rebuild LazyFrame, reading only required columns to reduce IO and memory
    lf = build_lazy_frame(files, columns=all_columns, file_type=file_type)

    total_rows = _collect(lf.select(pl.len())).item()
    if use_streaming is None:
        use_streaming = total_rows > LARGE_DATASET_THRESHOLD
    logger.info(
        "Total rows: %s (after sampling) | features to analyze: %d | streaming mode: %s",
        f"{total_rows:,}",
        len(all_columns),
        "enabled" if use_streaming else "disabled",
    )

    force_cat_set = set(force_cat_features or ())
    city_col_valid = city_col is not None and city_col in all_columns

    # Pre-classify columns
    cat_cols: list[str] = []
    num_cols: list[str] = []
    skipped: list[str] = []

    for col in all_columns:
        dtype = schema[col]
        if col in force_cat_set or is_categorical_dtype(dtype):
            cat_cols.append(col)
        elif is_numeric_dtype(dtype):
            num_cols.append(col)
        else:
            logger.warning("Column '%s' type %s not supported, skipped", col, dtype)
            skipped.append(col)

    # Batch-compute numerical feature base stats (default batch_size=1 to avoid Polars query plan complexity causing Segmentation fault on ultra-large datasets)
    with tqdm(total=len(num_cols), desc="Computing numerical feature statistics") as pbar:
        num_feature: dict[str, dict[str, Any]] = compute_num_stats_batch(
            lf, num_cols, total_rows, batch_size=num_stats_batch_size, pbar=pbar, use_streaming=use_streaming
        )

    # Batch-compute per-city medians
    if city_col_valid and num_cols:
        logger.info("Starting batch computation of per-city medians for %d numerical features...", len(num_cols))
        with tqdm(total=len(num_cols), desc="Computing per-city medians") as pbar:
            city_medians = compute_city_medians_batch(
                lf, num_cols, city_col=city_col, batch_size=city_median_batch_size, pbar=pbar, use_streaming=use_streaming
            )
        for col in num_cols:
            if col in num_feature:
                num_feature[col]["city_median"] = city_medians.get(col, {})

    # Batch-compute categorical feature base metadata (1 collect)
    cat_base: dict[str, tuple[int, int]] = compute_cat_base_batch(lf, cat_cols)

    # Compute categorical feature top-N one by one (high cardinality requires progressive limit, cannot fully batch)
    cat_feature: dict[str, dict[str, Any]] = {}
    for col in tqdm(cat_cols, desc="Computing categorical feature distributions"):
        try:
            cat_feature[col] = compute_cat_stats(
                lf, col, total_rows, precomputed_base=cat_base.get(col)
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Column '%s' statistics failed: %s", col, exc)
            skipped.append(col)

    if skipped:
        logger.info("Skipped %d features: %s", len(skipped), skipped[:10])

    # Cross-categorical statistics (pure Polars window functions + combination safety threshold)
    cross_cat: dict[str, dict[str, dict[str, float]]] = {}
    cross_cat_pairs = cross_cat_pairs or []
    for pair in tqdm(cross_cat_pairs, desc="Computing cross-categorical statistics"):
        if len(pair) != 2:
            logger.warning("cross_cat_pairs format error, must be a pair list: %s", pair)
            continue
        cat_a, cat_b = pair[0], pair[1]
        if cat_a not in all_columns or cat_b not in all_columns:
            logger.warning("Cross stat columns do not exist, skipping: %s x %s", cat_a, cat_b)
            continue
        try:
            key = f"{cat_a}__x__{cat_b}"
            cross_cat[key] = compute_cross_cat_stats(lf, cat_a, cat_b, coverage=0.95)
        except Exception as exc:  # noqa: BLE001
            logger.error("Cross stats %s x %s failed: %s", cat_a, cat_b, exc)

    return cat_feature, num_feature, cross_cat


def _flatten_cat_features(cat_feature: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """Flatten categorical feature statistics into a readable DataFrame."""
    rows = []
    for feat, stats in cat_feature.items():
        top_items = stats.get("top30_items", {})
        top_ratios = stats.get("top30_ratios", {})
        # Merge top30 into a string for easy viewing in Excel
        top_str = "; ".join(
            f"{k}: {v} ({top_ratios.get(k, 0):.4f})"
            for k, v in list(top_items.items())[:10]
        )
        rows.append(
            {
                "feature": feat,
                "nunique": stats.get("nunique"),
                "null_count": stats.get("null_count"),
                "null_ratio": stats.get("null_ratio"),
                "top10_preview": top_str,
                "skipped": stats.get("top30_items_skipped", False),
            }
        )
    return pd.DataFrame(rows)


def _flatten_num_features(num_feature: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """Flatten numerical feature statistics into a readable DataFrame."""
    rows = []
    for feat, stats in num_feature.items():
        rows.append({"feature": feat, **stats})
    return pd.DataFrame(rows)


def _flatten_cross_cat(cross_cat: dict[str, dict[str, dict[str, float]]]) -> pd.DataFrame:
    """Flatten cross-categorical statistics into a readable DataFrame."""
    rows = []
    for pair_key, city_dict in cross_cat.items():
        total_cities = len(city_dict)
        total_items = sum(len(v) for v in city_dict.values())
        # Show top 3 items for the first 3 cities as preview
        preview_parts = []
        for city, items in list(city_dict.items())[:3]:
            item_preview = ", ".join(
                f"{k}({v:.4f})" for k, v in list(items.items())[:3]
            )
            preview_parts.append(f"{city}: [{item_preview}]")
        preview = "; ".join(preview_parts)
        rows.append(
            {
                "pair": pair_key,
                "total_cities": total_cities,
                "total_items": total_items,
                "preview": preview,
            }
        )
    return pd.DataFrame(rows)


def save_results(
    cat_feature: dict[str, dict[str, Any]],
    num_feature: dict[str, dict[str, Any]],
    cross_cat: dict[str, dict[str, dict[str, float]]],
    output_dir: Path,
) -> None:
    """Save results to JSON and Excel."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON (preserve full structure)
    with open(output_dir / "cat_features.json", "w", encoding="utf-8") as f:
        json.dump(cat_feature, f, ensure_ascii=False, indent=2)
    with open(output_dir / "num_features.json", "w", encoding="utf-8") as f:
        json.dump(num_feature, f, ensure_ascii=False, indent=2)
    if cross_cat:
        with open(output_dir / "cross_cat_features.json", "w", encoding="utf-8") as f:
            json.dump(cross_cat, f, ensure_ascii=False, indent=2)

    # Excel (for easy viewing)
    if cat_feature:
        cat_df = _flatten_cat_features(cat_feature)
        cat_df.to_excel(output_dir / "cat_features.xlsx", index=False)

    if num_feature:
        # city_median is a dict and not suitable for direct flattening into Excel columns; remove and save separately
        num_df = _flatten_num_features(num_feature)
        drop_cols = [c for c in num_df.columns if c == "city_median"]
        if drop_cols:
            num_df = num_df.drop(columns=drop_cols)
        num_df.to_excel(output_dir / "num_features.xlsx", index=False)

    if cross_cat:
        cross_df = _flatten_cross_cat(cross_cat)
        cross_df.to_excel(output_dir / "cross_cat_features.xlsx", index=False)

    logger.info("Results saved to: %s", output_dir)


def load_config(config_path: Path) -> dict[str, Any]:
    """Read YAML config file and return eda_info contents."""
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    eda_info = cfg.get("eda_info", {})
    return {
        "features": eda_info.get("features"),
        "exclude_features": eda_info.get("exclude_features"),
        "force_cat_features": eda_info.get("force_cat_features"),
        "city_col": eda_info.get("city_col"),
        "cross_cat_pairs": eda_info.get("cross_cat_pairs"),
        "use_streaming": eda_info.get("use_streaming"),
        "num_stats_batch_size": eda_info.get("num_stats_batch_size", 1),
        "city_median_batch_size": eda_info.get("city_median_batch_size", 1),
        "sample_ratio": eda_info.get("sample_ratio", 0.3),
        "file_type": eda_info.get("file_type"),
    }


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Parquet feature distribution statistics aggregation tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data_dir",
        type=Path,
        required=True,
        help="Directory containing input parquet or csv files",
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        required=True,
        help="Directory to save output results",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="YAML config file path (must contain eda_info section)",
    )
    parser.add_argument(
        "--streaming",
        action="store_true",
        help="Force enable Polars streaming mode (auto by data size by default, enabled automatically above 500M rows)",
    )
    parser.add_argument(
        "--no-streaming",
        dest="no_streaming",
        action="store_true",
        help="Force disable Polars streaming mode (even if data size exceeds 500M rows)",
    )
    parser.add_argument(
        "--sample_ratio",
        type=float,
        default=None,
        help="EDA sampling ratio (0-1), config file takes precedence, fallback 0.3 if not specified",
    )
    parser.add_argument(
        "--file_type",
        type=str,
        default=None,
        choices=["parquet", "csv"],
        help="Input file type (default from config, fallback auto-detect, then parquet)",
    )
    return parser.parse_args()


def main() -> None:
    """Main function."""
    args = parse_args()

    DATA_DIR = args.data_dir
    OUTPUT_DIR = args.output_dir
    CONFIG_PATH = args.config

    if not DATA_DIR.exists():
        raise FileNotFoundError(f"Data directory does not exist: {DATA_DIR}")
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file does not exist: {CONFIG_PATH}")

    eda_cfg = load_config(CONFIG_PATH)

    # Resolve file type: CLI > config > auto-detect > parquet
    file_type = args.file_type or eda_cfg.get("file_type")
    if file_type is None:
        has_csv = any(DATA_DIR.rglob("*.csv"))
        has_parquet = any(DATA_DIR.rglob("*.parquet"))
        if has_csv and not has_parquet:
            file_type = "csv"
        else:
            file_type = "parquet"
    file_type = file_type.lower()
    if file_type not in ("parquet", "csv"):
        raise ValueError(f"Unsupported file_type: {file_type}")

    files = scan_data_files(DATA_DIR, file_type=file_type)
    logger.info("Found %d %s files", len(files), file_type)

    # Priority: CLI --streaming / --no-streaming > config file > auto
    use_streaming: bool | None = eda_cfg.get("use_streaming")
    if args.streaming:
        use_streaming = True
    elif args.no_streaming:
        use_streaming = False

    # Priority: CLI --sample_ratio > config file > default 0.3
    sample_ratio = eda_cfg.get("sample_ratio", 0.3)
    if args.sample_ratio is not None:
        sample_ratio = args.sample_ratio

    cat_feature, num_feature, cross_cat = summarize_features(
        files,
        features=eda_cfg.get("features"),
        exclude_features=eda_cfg.get("exclude_features"),
        force_cat_features=eda_cfg.get("force_cat_features"),
        city_col=eda_cfg.get("city_col"),
        cross_cat_pairs=eda_cfg.get("cross_cat_pairs"),
        use_streaming=use_streaming,
        num_stats_batch_size=eda_cfg.get("num_stats_batch_size", 1),
        city_median_batch_size=eda_cfg.get("city_median_batch_size", 1),
        sample_ratio=sample_ratio,
        file_type=file_type,
    )

    save_results(cat_feature, num_feature, cross_cat, OUTPUT_DIR)
    logger.info(
        "Categorical features: %d | numerical features: %d | cross stat pairs: %d",
        len(cat_feature),
        len(num_feature),
        len(cross_cat),
    )


def test_():
    DATA_DIR = Path(
        '/data/cb_data'
    )
    FEATURES = [
        'order_response_rate',
        'billing_online_rate',
        'label',
        'city_code',
        'company_no',
        'day_of_week',
        'log_time_slice',
        'order_start_lv7h3',
        'is_rain',
        'order_submit_service_type',
        'estimate_minute',
        'estimate_price',
        'estimate_km',
        'h3_value_start',
        'h3_value_end',
        'bub_pay',
        'bub_pay2',
        'bub_pay3',
        'bub_pay6',
        'bub_pay12',
        'bub_pay24',
        'est_distance',
        'est_time',
        'service_type_order_num',
        'service_type_order_num2',
        'service_type_order_num3',
        'service_type_order_num6',
        'service_type_order_num12',
        'service_type_order_num24',
        'service_type_lock_num',
        'service_type_lock_num2',
        'service_type_lock_num3',
        'service_type_lock_num6',
        'service_type_lock_num12',
        'service_type_lock_num24',
        'service_type_received_num',
        'service_type_received_num2',
        'service_type_received_num3',
        'service_type_received_num6',
        'service_type_received_num12',
        'service_type_received_num24',
        'service_type_bub_num',
        'service_type_bub_num2',
        'service_type_bub_num3',
        'service_type_bub_num6',
        'service_type_bub_num12',
        'service_type_bub_num24',
        'pay_receive',
        'pay_receive2',
        'pay_receive3',
        'pay_receive6',
        'pay_receive12',
        'pay_receive24',
        'bub_gmv',
        'bub_gmv2',
        'bub_gmv3',
        'bub_gmv6',
        'bub_gmv12',
        'bub_gmv24',
        'ts_free_driver_num_type2',
        'ts_free_driver_num2_type2',
        'ts_free_driver_num3_type2',
        'ts_free_driver_num6_type2',
        'ts_free_driver_num_type7',
        'ts_free_driver_num2_type7',
        'ts_free_driver_num3_type7',
        'ts_free_driver_num6_type7',
        'ts_service_driver_num_type2',
        'ts_service_driver_num2_type2',
        'ts_service_driver_num3_type2',
        'ts_service_driver_num6_type2',
        'ts_service_driver_num_type7',
        'ts_service_driver_num2_type7',
        'ts_service_driver_num3_type7',
        'ts_service_driver_num6_type7',
        'ts_total_driver_num_type2',
        'ts_total_driver_num2_type2',
        'ts_total_driver_num3_type2',
        'ts_total_driver_num6_type2',
        'ts_total_driver_num_type7',
        'ts_total_driver_num2_type7',
        'ts_total_driver_num3_type7',
        'ts_total_driver_num6_type7',
        'service_type_response_rate',
        'service_type_response_rate2',
        'service_type_response_rate3',
        'service_type_response_rate6',
        'service_type_response_rate12',
        'service_type_response_rate24',
        'max_response_rate',
        'min_response_rate',
        'mean_response_rate',
        'service_type_response_rate_city',
        'service_type_response_rate2_city',
        'service_type_response_rate3_city',
        'service_type_response_rate6_city',
        'service_type_response_rate12_city',
        'service_type_response_rate24_city',
    ]
    cat_feature, num_feature, cross_cat = summarize_features(
        scan_data_files(DATA_DIR, file_type="parquet"),
        features=FEATURES,          # Optional: analyze only specified columns
        exclude_features=["id", "dt"],        # Optional: exclude meaningless columns
        force_cat_features=["city_code", 'order_start_lv7h3', 'is_rain', 'order_submit_service_type'],     # Optional: force categorical statistics
        city_col='city_code',
        cross_cat_pairs=[["city_code", 'order_start_lv7h3']]
    )


if __name__ == "__main__":
    main()

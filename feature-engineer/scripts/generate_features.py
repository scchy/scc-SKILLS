#!/usr/bin/env python3
"""Automated, leakage-safe feature generation for tabular ML.

Pipeline (everything is fit on train only, then applied to test):
1. Align train/test columns (dropped columns are reported, not silently lost)
2. Record row-level missingness (row_nan_count) BEFORE imputation
3. Impute numeric columns (median) and categorical columns (most frequent)
4. Extract calendar parts from datetime columns (year/month/day/dayofweek)
5. Add row-wise stats over numeric columns (mean/std/min/max/median),
   excluding ID-like columns (named `id` or `*_id`, plus --id_cols)
6. Encode categoricals: one-hot for low cardinality, frequency encoding
   for high cardinality (maps fit on train; unseen test categories -> 0)

Output protocol: stdout carries a single JSON summary (agent-consumable);
human-readable logs go to stderr. Failures exit non-zero with a JSON error.
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
except ImportError as e:
    # Agent-facing preflight: report missing deps as structured errors
    # instead of a raw ImportError traceback. The sandbox has no internet,
    # so do NOT suggest pip install — the agent must fall back to custom code.
    print(
        json.dumps(
            {
                "status": "error",
                "error": f"missing dependency '{e.name}' (expected pre-installed; "
                "no internet in sandbox — fall back to writing custom pandas-free code)",
            }
        )
    )
    sys.exit(2)

DEFAULT_ONE_HOT_MAX = 10


def log(message: str) -> None:
    print(f"[feature-engineer] {message}", file=sys.stderr)


def fail(message: str) -> None:
    log(f"Error: {message}")
    print(json.dumps({"status": "error", "error": message}))
    sys.exit(2)


def read_table(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        fail(f"file not found: {path}")
    suffix = p.suffix.lower()
    try:
        if suffix == ".csv":
            return pd.read_csv(p)
        if suffix == ".parquet":
            return pd.read_parquet(p)
    except Exception as e:
        fail(f"failed to read {path}: {type(e).__name__}: {e}")
    fail(f"unsupported extension '{suffix}' (expected .csv or .parquet)")


def write_table(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False)


def is_id_like(col: str) -> bool:
    c = col.lower()
    return c == "id" or c.endswith("_id")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate automated ML features.")
    parser.add_argument("--train", default="train.csv", help="Path to train file (.csv/.parquet)")
    parser.add_argument("--test", default="test.csv", help="Path to test file (.csv/.parquet)")
    parser.add_argument("--target", default="target", help="Target column name in train")
    parser.add_argument(
        "--output_dir",
        default=".",
        help="Directory for engineered outputs (default: current directory)",
    )
    parser.add_argument(
        "--id_cols",
        default="",
        help="Comma-separated extra columns to keep but exclude from row stats",
    )
    parser.add_argument(
        "--one_hot_max",
        type=int,
        default=DEFAULT_ONE_HOT_MAX,
        help=f"Max unique values for one-hot encoding (default: {DEFAULT_ONE_HOT_MAX}); "
        "higher-cardinality columns get frequency encoding",
    )
    args = parser.parse_args()

    train_df = read_table(args.train)
    test_df = read_table(args.test)

    # Separate target (kept aside so it never influences feature fitting)
    target_series = None
    if args.target in train_df.columns:
        target_series = train_df[args.target]
        train_df = train_df.drop(columns=[args.target])
    else:
        log(f"Warning: target column '{args.target}' not found in train file")

    # Align columns; report what gets dropped instead of losing it silently
    common_cols = [c for c in train_df.columns if c in test_df.columns]
    train_only = [c for c in train_df.columns if c not in test_df.columns]
    test_only = [c for c in test_df.columns if c not in train_df.columns]
    train_df = train_df[common_cols].copy()
    test_df = test_df[common_cols].copy()

    # Drop columns that are entirely missing in train (nothing to impute from)
    empty_cols = train_df.columns[train_df.isna().all()].tolist()
    if empty_cols:
        train_df = train_df.drop(columns=empty_cols)
        test_df = test_df.drop(columns=empty_cols)
        log(f"Dropped all-missing columns: {empty_cols}")

    extra_id_cols = [c.strip() for c in args.id_cols.split(",") if c.strip()]
    stat_excluded = [c for c in train_df.columns if is_id_like(c) or c in extra_id_cols]

    num_cols = train_df.select_dtypes(include=[np.number]).columns.tolist()
    dt_cols = train_df.select_dtypes(include=["datetime", "datetimetz"]).columns.tolist()
    cat_cols = [
        c for c in train_df.columns if c not in num_cols and c not in dt_cols
    ]

    # CSV loads datetimes as strings; promote object columns that are >=90%
    # parseable as dates so they get calendar parts instead of encoding
    dt_detected = []
    for col in list(cat_cols):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed_train = pd.to_datetime(train_df[col], errors="coerce")
        if parsed_train.notna().mean() >= 0.9:
            train_df[col] = parsed_train
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                test_df[col] = pd.to_datetime(test_df[col], errors="coerce")
            cat_cols.remove(col)
            dt_cols.append(col)
            dt_detected.append(col)

    # Promote object columns that are >=90% numeric (numbers are often stored
    # as strings in CSVs, e.g. "12.5" or "1,000"); otherwise they would be
    # wrongly treated as categoricals and encoded
    num_detected = []
    for col in list(cat_cols):
        cleaned_train = train_df[col].astype(str).str.replace(",", "", regex=False)
        parsed_train = pd.to_numeric(cleaned_train, errors="coerce")
        if parsed_train.notna().mean() >= 0.9:
            train_df[col] = parsed_train
            cleaned_test = test_df[col].astype(str).str.replace(",", "", regex=False)
            test_df[col] = pd.to_numeric(cleaned_test, errors="coerce")
            cat_cols.remove(col)
            num_cols.append(col)
            num_detected.append(col)

    # Surface suspicious columns instead of letting them pass silently
    quality_warnings = []
    constant_cols = [
        c for c in train_df.columns if train_df[c].nunique(dropna=False) <= 1
    ]
    if constant_cols:
        quality_warnings.append(f"constant columns with no variance: {constant_cols}")
    id_like_cats = [
        c for c in cat_cols if len(train_df) and train_df[c].nunique() == len(train_df)
    ]
    if id_like_cats:
        quality_warnings.append(
            f"categorical columns with one unique value per row (possible IDs): "
            f"{id_like_cats}; consider passing them via --id_cols"
        )
    for w in quality_warnings:
        log(f"Warning: {w}")

    stat_cols = [c for c in num_cols if c not in stat_excluded]

    log(f"Shapes: train={train_df.shape}, test={test_df.shape}")
    log(f"numeric={len(num_cols)}, categorical={len(cat_cols)}, datetime={len(dt_cols)}")

    features_added: dict[str, list[str]] = {}

    # Row-level missingness BEFORE imputation — missingness itself is signal
    aligned_cols = train_df.columns.tolist()
    train_df["row_nan_count"] = train_df[aligned_cols].isna().sum(axis=1)
    test_df["row_nan_count"] = test_df[aligned_cols].isna().sum(axis=1)
    features_added["row_nan_count"] = ["row_nan_count"]

    # Imputation: statistics computed on train, applied to both (no leakage).
    # Plain pandas fillna is used instead of sklearn because SimpleImputer
    # does not reliably treat None as missing in object columns.
    imputed = {}
    if num_cols:
        imputed["numeric_train"] = int(train_df[num_cols].isna().sum().sum())
        imputed["numeric_test"] = int(test_df[num_cols].isna().sum().sum())
        medians = train_df[num_cols].median()
        train_df[num_cols] = train_df[num_cols].fillna(medians)
        test_df[num_cols] = test_df[num_cols].fillna(medians)
    if cat_cols:
        imputed["categorical_train"] = int(train_df[cat_cols].isna().sum().sum())
        imputed["categorical_test"] = int(test_df[cat_cols].isna().sum().sum())
        for col in cat_cols:
            mode = train_df[col].mode(dropna=True)
            fill_value = mode.iloc[0] if len(mode) else "missing"
            train_df[col] = train_df[col].fillna(fill_value)
            test_df[col] = test_df[col].fillna(fill_value)

    # Datetime columns -> calendar parts (original column dropped)
    dt_features = []
    for col in dt_cols:
        for part, values_train, values_test in (
            ("year", train_df[col].dt.year, test_df[col].dt.year),
            ("month", train_df[col].dt.month, test_df[col].dt.month),
            ("day", train_df[col].dt.day, test_df[col].dt.day),
            ("dow", train_df[col].dt.dayofweek, test_df[col].dt.dayofweek),
        ):
            name = f"{col}_{part}"
            train_df[name] = values_train
            test_df[name] = values_test
            dt_features.append(name)
        train_df = train_df.drop(columns=[col])
        test_df = test_df.drop(columns=[col])
        num_cols.extend(dt_features[-4:])
    if dt_features:
        features_added["datetime_parts"] = dt_features

    # Row-wise numeric stats (ID-like columns excluded)
    row_stats = []
    if stat_cols:
        stats = {
            "row_mean": lambda df: df[stat_cols].mean(axis=1),
            "row_min": lambda df: df[stat_cols].min(axis=1),
            "row_max": lambda df: df[stat_cols].max(axis=1),
            "row_median": lambda df: df[stat_cols].median(axis=1),
        }
        if len(stat_cols) >= 2:
            stats["row_std"] = lambda df: df[stat_cols].std(axis=1)
        for name, fn in stats.items():
            train_df[name] = fn(train_df)
            test_df[name] = fn(test_df)
            row_stats.append(name)
        features_added["row_stats"] = row_stats

    # Categorical encoding: one-hot (low cardinality) or frequency (high)
    one_hot_map: dict[str, int] = {}
    freq_cols: list[str] = []
    for col in cat_cols:
        n_unique = train_df[col].nunique()
        if n_unique <= args.one_hot_max:
            cats = sorted(train_df[col].unique(), key=lambda v: str(v))
            train_dummies = pd.get_dummies(
                pd.Categorical(train_df[col], categories=cats), prefix=col
            ).astype(int)
            # Fixed train categories -> unseen test values become all-zero rows
            test_dummies = pd.get_dummies(
                pd.Categorical(test_df[col], categories=cats), prefix=col
            ).astype(int)
            train_dummies.index = train_df.index
            test_dummies.index = test_df.index
            train_df = pd.concat([train_df, train_dummies], axis=1)
            test_df = pd.concat([test_df, test_dummies], axis=1)
            one_hot_map[col] = len(cats)
        else:
            freq = train_df[col].value_counts(normalize=True)
            name = f"{col}_freq"
            train_df[name] = train_df[col].map(freq)
            test_df[name] = test_df[col].map(freq).fillna(0.0)
            freq_cols.append(name)
        train_df = train_df.drop(columns=[col])
        test_df = test_df.drop(columns=[col])
    if one_hot_map:
        features_added["one_hot"] = [
            f"{col} ({n} categories)" for col, n in one_hot_map.items()
        ]
    if freq_cols:
        features_added["frequency"] = freq_cols

    # Re-attach target (row order was never changed, index still aligned)
    if target_series is not None:
        train_df[args.target] = target_series

    out_dir = Path(args.output_dir)
    ext = Path(args.train).suffix.lower()
    ext = ext if ext in (".csv", ".parquet") else ".csv"
    train_out = out_dir / f"train_engineered{ext}"
    test_out = out_dir / f"test_engineered{ext}"
    write_table(train_df, train_out)
    write_table(test_df, test_out)

    log(f"Saved {train_out} and {test_out}")
    print(
        json.dumps(
            {
                "status": "ok",
                "train_output": str(train_out),
                "test_output": str(test_out),
                "train_shape": list(train_df.shape),
                "test_shape": list(test_df.shape),
                "dropped_columns": {
                    "train_only": train_only,
                    "test_only": test_only,
                    "all_missing": empty_cols,
                },
                "column_types": {
                    "numeric": len(num_cols),
                    "categorical": len(cat_cols),
                    "datetime": len(dt_cols),
                    "datetime_detected_from_strings": dt_detected,
                    "numeric_detected_from_strings": num_detected,
                },
                "warnings": quality_warnings,
                "excluded_from_row_stats": stat_excluded,
                "missing_values_imputed": imputed,
                "features_added": features_added,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

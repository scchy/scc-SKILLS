#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate EDA report and feature engineering config files based on data scan results.
"""

import json
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import os


class EDAReportGenerator:
    def __init__(self, num_features_path: str, cat_features_path: str, cross_cat_features_path: Optional[str] = None):
        """Initialize the EDA report generator. Cross-cat stats are optional."""
        self.num_features_path = num_features_path
        self.cat_features_path = cat_features_path
        self.cross_cat_features_path = cross_cat_features_path

        # Load data
        with open(num_features_path, "r", encoding="utf-8") as f:
            self.num_features = json.load(f)

        with open(cat_features_path, "r", encoding="utf-8") as f:
            self.cat_features = json.load(f)

        if cross_cat_features_path and os.path.exists(cross_cat_features_path):
            with open(cross_cat_features_path, "r", encoding="utf-8") as f:
                self.cross_cat_features = json.load(f)
        else:
            self.cross_cat_features = {}

    def analyze_features(self) -> Dict[str, Any]:
        """Analyze features and generate recommendations."""
        analysis = {
            "numerical_features": {},
            "categorical_features": {},
            "recommendations": {
                "drop_features": [],
                "encoding_suggestions": {},
                "embedding_dimensions": {},
                "fill_na_strategies": {},
            },
        }

        # Analyze numerical features
        for feature, stats in self.num_features.items():
            analysis["numerical_features"][feature] = {
                "null_ratio": stats["null_ratio"],
                "zero_ratio": stats.get("zero_ratio", 0),
                "nunique": stats["nunique"],
                "mean": stats["mean"],
                "std": stats["std"],
                "min": stats["min"],
                "max": stats["max"],
            }

            # Decide whether to drop
            if stats["null_ratio"] > 0.9:  # Missing rate exceeds 90%
                analysis["recommendations"]["drop_features"].append(feature)
            elif stats["nunique"] == 1:  # Single-value feature
                analysis["recommendations"]["drop_features"].append(feature)
            elif stats["zero_ratio"] > 0.95:  # Zero ratio too high
                analysis["recommendations"]["drop_features"].append(feature)

        # Analyze categorical features
        for feature, stats in self.cat_features.items():
            analysis["categorical_features"][feature] = {
                "null_ratio": stats["null_ratio"],
                "nunique": stats["nunique"],
                "top_categories": list(stats["top30_items"].keys())[:10],
                "top_ratios": list(stats["top30_ratios"].values())[:10],
            }

            # Compute embedding dimension suggestions
            nunique = stats["nunique"]
            if nunique <= 10:
                embedding_dim = min(4, nunique)
            elif nunique <= 50:
                embedding_dim = min(8, nunique)
            elif nunique <= 100:
                embedding_dim = min(16, nunique)
            else:
                embedding_dim = min(32, int(np.sqrt(nunique)))

            analysis["recommendations"]["embedding_dimensions"][feature] = embedding_dim

            # Missing value handling suggestions
            if stats["null_ratio"] > 0:
                analysis["recommendations"]["fill_na_strategies"][feature] = "mode"
            else:
                analysis["recommendations"]["fill_na_strategies"][feature] = "none"

        return analysis

    def generate_encoding_map(self) -> Dict[str, Dict[str, int]]:
        """Generate categorical feature encoding map."""
        encoding_map = {}
        bias = 0  # Base offset

        # Process ordinary categorical features
        for feature, stats in self.cat_features.items():
            if feature in encoding_map:
                continue
            categories = list(stats["top30_items"].keys())
            encoding = {}
            for idx, cat in enumerate(categories, 1):
                encoding[cat] = idx

            # Add OTH category
            encoding["OTH"] = 0
            encoding_map[feature] = encoding

        # Process cross features
        children_key = "None"
        for feature in self.cross_cat_features.keys():
            encoding = {}

            # Parse feature name to get parent_key and children_key
            if "__x__" in feature:
                parent_key, children_key = feature.split("__x__")[:2]

                # Get cross feature values
                cross_data = self.cross_cat_features[feature]
                current_idx = bias
                unique_children = set()
                for p, children_dict in cross_data.items():
                    if p not in encoding_map[parent_key]:
                        continue
                    for child_value in children_dict.keys():
                        if child_value not in unique_children:
                            unique_children.add(child_value)
                            encoding[child_value] = current_idx
                            current_idx += 1

                for parent_k, _ in cross_data.items():
                    if parent_k not in encoding_map[parent_key]:
                        continue
                    encoding[f"{parent_k}-OTH"] = current_idx
                    current_idx += 1

            encoding["OTH"] = current_idx
            encoding_map[children_key] = encoding

        return encoding_map

    def generate_fill_na_map(self) -> Dict[str, Any]:
        """Generate missing value fill map."""
        fill_na_map = {}

        # Numerical features
        for feature, stats in self.num_features.items():
            if stats["null_ratio"] > 0:
                if stats["mean"] == 0 and stats["std"] == 0:  # All zeros
                    fill_na_map[feature] = 0
                else:
                    fill_na_map[feature] = stats["median"]

        # Categorical features
        for feature, stats in self.cat_features.items():
            if stats["null_ratio"] > 0:
                top_categories = list(stats["top30_items"].keys())
                fill_na_map[feature] = top_categories[0] if top_categories else "unknown"

        return fill_na_map

    def generate_numeric_std_mean(self) -> Dict[str, float]:
        """Generate standardization parameters (mean/std) for numerical features."""
        std_mean_map = {}
        for feature, stats in self.num_features.items():
            std_mean_map[feature] = {
                "mean": stats["mean"],
                "std": stats["std"],
            }
        return std_mean_map

    def generate_markdown_report(self, analysis: Dict[str, Any]) -> str:
        """Generate the EDA report in Markdown format."""
        report = f"""# Data Feature Analysis Report

## 1. Data Overview

### 1.1 Numerical Features
Found **{len(analysis['numerical_features'])}** numerical features.

### 1.2 Categorical Features
Found **{len(analysis['categorical_features'])}** categorical features.

## 2. Feature Quality Analysis

### 2.1 Features Not Recommended for Modeling
The following features are not recommended for modeling due to data quality issues:

{chr(10).join([f"- **{feat}**: High missing rate or single value" for feat in analysis['recommendations']['drop_features']])}

### 2.2 Numerical Feature Statistics

| Feature | Missing Rate | Zero Ratio | Unique Count | Mean | Std | Min | Max |
|---------|-------------|------------|--------------|------|-----|-----|-----|
"""

        # Add numerical feature statistics table (first 10 only)
        for feat, stats in list(analysis["numerical_features"].items())[:10]:
            report += (
                f"| {feat} | {stats['null_ratio']:.2%} | {stats['zero_ratio']:.2%} | "
                f"{stats['nunique']} | {stats['mean']:.2f} | {stats['std']:.2f} | "
                f"{stats['min']:.2f} | {stats['max']:.2f} |\n"
            )

        report += f"""
### 2.3 Categorical Feature Statistics

| Feature | Missing Rate | Unique Count | Top 3 Categories | Ratios |
|---------|-------------|--------------|------------------|--------|
"""

        # Add categorical feature statistics table (first 10 only)
        for feat, stats in list(analysis["categorical_features"].items())[:10]:
            top_cats = stats["top_categories"][:3]
            top_ratios = stats["top_ratios"][:3]
            cats_str = ", ".join(top_cats)
            ratios_str = ", ".join([f"{r:.1%}" for r in top_ratios])
            report += f"| {feat} | {stats['null_ratio']:.2%} | {stats['nunique']} | {cats_str} | {ratios_str} |\n"

        report += """
## 3. Feature Engineering Suggestions

### 3.1 Categorical Feature Encoding Suggestions
- **Label Encoding**: Suitable for ordinal categorical variables
- **One-Hot Encoding**: Suitable for nominal categorical variables with few categories
- **Embedding**: Suitable for high-cardinality categorical variables; suggested dimensions:

| Feature | Unique Count | Suggested Embedding Dimension |
|---------|--------------|-------------------------------|
"""

        # Add embedding dimension suggestions (first 10 only)
        for feat, dim in list(analysis["recommendations"]["embedding_dimensions"].items())[:10]:
            nunique = analysis["categorical_features"][feat]["nunique"]
            report += f"| {feat} | {nunique} | {dim} |\n"

        report += """
### 3.2 Missing Value Handling Strategy
- **Numerical Features**: Fill with median
- **Categorical Features**: Fill with mode (most frequent category)

### 3.3 Cross Feature Handling
Based on cross_cat_features.json, special handling is suggested for the following cross features:
- City code × Order start region
- Company code × Time slice
- Other high-order interaction features

## 4. Modeling Suggestions

### 4.1 Data Preprocessing
1. **Handle missing values**: Fill according to the strategies above
2. **Feature scaling**: Standardize or normalize numerical features
3. **Encoding transformation**: Apply appropriate encoding to categorical features

### 4.2 Model Selection Suggestions
- **Tree models**: XGBoost, LightGBM, CatBoost (natively handle categorical variables)
- **Deep learning**: Wide&Deep, DeepFM (suitable for high-dimensional sparse features)
- **Ensemble methods**: Stacking methods combining multiple models

### 4.3 Hyperparameter Tuning Focus
- **Embedding dimension**: Grid search based on the table above
- **Regularization parameters**: Prevent overfitting
- **Learning rate**: Balance convergence speed and accuracy

## 5. Notes

1. **Data leakage**: Ensure correct handling of time-series features
2. **Class imbalance**: Consider using SMOTE or adjusting class weights
3. **Feature importance**: Use SHAP values for feature interpretation
4. **Model monitoring**: Establish an A/B test framework to continuously monitor model performance

---
*Report generated at: {timestamp}*
""".format(timestamp=pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))

        return report

    def save_outputs(self, output_dir: str = "."):
        """Save all output files."""

        # Analyze features
        analysis = self.analyze_features()

        # Generate report
        report = self.generate_markdown_report(analysis)

        # Save report
        with open(os.path.join(output_dir, "EDA_report.md"), "w", encoding="utf-8") as f:
            f.write(report)

        # Generate and save encoding map
        encoding_map = self.generate_encoding_map()
        with open(os.path.join(output_dir, "encoding_map.json"), "w", encoding="utf-8") as f:
            json.dump(encoding_map, f, ensure_ascii=False, indent=2)

        # Generate and save missing value fill map
        fill_na_map = self.generate_fill_na_map()
        with open(os.path.join(output_dir, "fill_na_map.json"), "w", encoding="utf-8") as f:
            json.dump(fill_na_map, f, ensure_ascii=False, indent=2)

        # Generate and save numerical feature standardization parameters
        numeric_std_mean = self.generate_numeric_std_mean()
        with open(os.path.join(output_dir, "numerical_stats.json"), "w", encoding="utf-8") as f:
            json.dump(numeric_std_mean, f, ensure_ascii=False, indent=2)

        print(f"[SUCCESS] All files saved to: {output_dir}")
        print("   - EDA_report.md")
        print("   - encoding_map.json")
        print("   - fill_na_map.json")
        print("   - numerical_stats.json")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate EDA report and feature engineering configs from scan results."
    )
    parser.add_argument("--num_features", required=True, help="Path to num_features.json")
    parser.add_argument("--cat_features", required=True, help="Path to cat_features.json")
    parser.add_argument(
        "--cross_cat_features",
        default=None,
        help="Path to cross_cat_features.json (optional)",
    )
    parser.add_argument(
        "--output_dir",
        default=".",
        help="Directory for outputs (use an absolute path under /work in the sandbox)",
    )
    args = parser.parse_args()

    generator = EDAReportGenerator(
        args.num_features, args.cat_features, args.cross_cat_features
    )
    os.makedirs(args.output_dir, exist_ok=True)
    generator.save_outputs(args.output_dir)

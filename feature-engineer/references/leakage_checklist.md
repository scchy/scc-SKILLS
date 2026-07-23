# Data Leakage Prevention Checklist

Data leakage occurs when information from outside the training dataset is used to create the model, leading to overly optimistic performance estimates during local validation and catastrophic failure on the private leaderboard.

When performing feature engineering, strictly adhere to the following principles:

## Target Leakage Prevention
- **Rule**: Ensure no feature is directly derived from or highly correlated with the target column in a way that would not be available at true inference time.
- **Check**: If a single feature has suspiciously high correlation or importance, investigate it first — it is often leakage.
- **Example**: Using `sale_price` to compute `price_per_sqft` when predicting `sale_price`.

## Temporal Leakage Prevention
- **Rule**: For time-ordered data, features for a row must only use information available *before* that row's timestamp.
- **Check**: Aggregations (mean, count, rolling stats) must be computed over past windows only, never the full series.
- **Example**: Computing a customer's average spend using transactions that happen after the prediction date.

## Train/Test Contamination
- **Rule**: Any statistic learned from data (imputation values, encodings, scalers, target means) must be fit on the **training folds only**, then applied to validation/test.
- **Check**: Fitting on the full dataset (train + test) before splitting leaks test distribution into training.
- **Note**: This skill's `generate_features.py` fits imputers and encoders on train only — keep it that way when extending it.

## Target Encoding Hygiene
- **Rule**: Target/mean encodings must be computed out-of-fold (or with smoothing/noise), never on the same rows they are applied to.
- **Check**: A target-encoded feature with near-perfect train correlation but poor validation correlation indicates in-fold encoding.

## Validation Strategy
- **Rule**: The local validation split must mimic the train/test relationship (time-based split for temporal data, group-based for grouped data).
- **Check**: If local CV and leaderboard disagree wildly, suspect the split strategy before suspecting the model.

## Duplicate & ID Columns
- **Rule**: Check for rows duplicated between train and test, and for ID columns that encode ordering or batch information correlated with the target.

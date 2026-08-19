# Feature Recipes — Task-Specific Feature Templates

`generate_features.py` produces a clean, leakage-safe baseline feature set.
The features below usually drive real leaderboard gains, but they require
task knowledge — generate them yourself after running the script.

**Golden rule**: any statistic must be fit on training data only (or
out-of-fold), then applied to validation/test. See `leakage_checklist.md`.

## 1. Group-by Aggregations

Best first move for categorical keys (user, item, region, category).

```python
# Stats of a numeric column per group, fit on train, mapped to both
agg = train.groupby("city")["income"].agg(["mean", "std", "count"])
agg.columns = [f"city_income_{c}" for c in agg.columns]
train = train.merge(agg, left_on="city", right_index=True, how="left")
test = test.merge(agg, left_on="city", right_index=True, how="left")
# Unseen groups in test stay NaN — leave them or fill with global stats
```

Useful variants: group size (`count`), nunique of one column within another
(`users per region`), ratio of row value to its group mean.

## 2. Time-Series Lags and Rolling Stats

Only when rows are time-ordered. Sort first, use only the past.

```python
df = df.sort_values("date")
df["sales_lag1"] = df.groupby("store")["sales"].shift(1)
df["sales_roll7"] = (
    df.groupby("store")["sales"]
      .transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean())
)
```

Never compute lags/rolling without `shift(1)` — otherwise the current row
leaks into its own feature.

## 3. Out-of-Fold Target Encoding

High-cardinality categoricals often beat frequency encoding with target
encoding — but only OOF, otherwise it leaks badly.

```python
from sklearn.model_selection import KFold

train["city_te"] = np.nan
kf = KFold(n_splits=5, shuffle=True, random_state=42)
for tr_idx, val_idx in kf.split(train):
    mapping = train.iloc[tr_idx].groupby("city")[target].mean()
    train.loc[val_idx, "city_te"] = train.iloc[val_idx]["city"].map(mapping)

# Test uses the mapping from the FULL train (this part is safe)
full_mapping = train.groupby("city")[target].mean()
test["city_te"] = test["city"].map(full_mapping).fillna(train[target].mean())
```

Add smoothing for small groups when categories are sparse:
`te = (count * mean + m * global_mean) / (count + m)` with `m` ~ 10-100.

## 4. Interactions

Cheap and often effective for tree models:

```python
train["age_x_income"] = train["age"] * train["income"]
train["city_user"] = train["city"].astype(str) + "_" + train["user_segment"].astype(str)
```

Keep the number small — each interaction should have a hypothesis behind it.

## 5. Count/Bin Features

```python
train["income_bin"] = pd.qcut(train["income"], q=10, labels=False, duplicates="drop")
freq = train["big_cat"].value_counts()
train["big_cat_count"] = train["big_cat"].map(freq)
test["big_cat_count"] = test["big_cat"].map(freq).fillna(0)
```

## After Generating Features

Record every variant in the experiment journal (review-experiment skill):
what you added, CV before/after. Feature engineering without a journal
degenerates into unrepeatable guessing.

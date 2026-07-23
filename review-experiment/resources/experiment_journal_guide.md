# Experiment Journal Guide

## Why Keep a Journal?

AutoML agents often repeat failed experiments or forget what worked.
A structured journal prevents this by making every outcome explicit and queryable.

## Best Practices

1. **Review after every execution** — not just successful ones. Bugs teach more than successes.
2. **Use CV scores, not public leaderboard** — the journal tracks generalization, not overfitting.
3. **Tag everything** — model family, feature strategy, data version. Tags make filtering trivial.
4. **Link parent experiments** — `parent_id` builds an experiment tree. Know which baseline a variant came from.
5. **Keep summaries actionable** — "LightGBM baseline CV 0.854" is better than "tried lightgbm".

## Common Pitfalls

- **Omitting `lower_is_better`** — downstream tools cannot compare experiments without knowing the metric direction.
- **Writing vague summaries** — "improved a bit" is useless. State before/after metric values.
- **Ignoring bugs** — if an experiment fails, record the error. The next agent (or you) will thank you.

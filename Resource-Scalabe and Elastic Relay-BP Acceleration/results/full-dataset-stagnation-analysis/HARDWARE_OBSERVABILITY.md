# Hardware observability assessment

This is an incremental-cost classification only; no RTL was designed or modified.

| Signal | Approximate incremental cost | Reason |
|---|---|---|
| Current residual weight | Trivial | The convergence phase already obtains the residual/syndrome result; a scalar count is already implicit in the analysis/cycle model. |
| Running-best residual | Trivial | One residual-width register and comparison. |
| Iterations since strict best improvement | Trivial | One saturating counter plus reset/enable from the best comparison. |
| New-best flag | Trivial | Direct comparator output. |
| Current residual minus best | Small | One narrow subtractor or comparison against a small threshold. |
| Relay-leg index / iteration in leg | Trivial | Existing controller state/counters. |
| Per-leg productive/stagnant/regressive status | Small | Snapshot start/best/end scalars and a few comparisons at the boundary. |
| Decision-change count | Moderate | Requires XOR and population count across the folded decision stream plus an accumulator; previous decisions may already be retained, but the reduction is extra. |
| Normalized decision churn | Moderate | The raw counter is preferable; explicit division is unnecessary if thresholds are pre-scaled. |
| Saturation event counters | Small | Saturation flags already exist in fixed arithmetic, but collecting them across message operations needs counters/routing. They were not predictive enough here to prioritize. |
| Full residual-vector Hamming distance/repetition | Expensive | Requires state storage/comparison and wide/folded population counting beyond a scalar residual. |
| Dense marginal, mu, or nu histories | Expensive | Large storage and bandwidth; deliberately excluded from this study. |

The strongest population signal—running-best stagnation—uses only trivial incremental state. Running-best level and residual gap are also cheap. Decision churn showed inconsistent conditional discrimination and costs more, so the current evidence does not justify treating it as essential. Leg index is free but mainly identifies survivor exposure rather than intrinsic state quality.

No hardware action, threshold, scheduling rule, or resource policy follows from this cost table.

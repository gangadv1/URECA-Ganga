# Running-best residual and late escape

## Frozen-condition strata

Among p=0.004 Target-3-eligible boundaries already stagnant for at least 120 iterations:

| Running-best residual | Boundaries | No best in next 3 legs | New best within 3 legs |
|---|---:|---:|---:|
| 1 | 79 | 88.6% | 11.4% |
| 2–3 | 74 | 68.9% | 31.1% |
| 4–8 | 66 | 63.6% | 36.4% |
| >8 | 9 | 22.2% | 77.8% |

At p=0.002, no eligible boundary reaches the frozen 120-iteration condition, so this interaction cannot be validated there.

Running-best residual materially changes false-positive risk at p=0.004. Paths already at residual 1 are more likely to remain unproductive over the next three legs than paths farther away. However, 9/79 residual-1 boundaries still improve within three legs; because the only strict improvement from residual 1 is convergence to zero, those cases are especially consequential even though they are less frequent.

Thus residual-1 paths are not statistically the *most likely* late escapes, but terminating one on stagnation alone can discard an imminent convergence. Redirecting resources without terminating the path is a different decision and was not evaluated.

## Observed escape events

At p=0.004 there are 26 productive-leg escape events after a preceding boundary with at least 120 stagnant iterations, across 16 unique trajectories. Twelve events occur in nine trajectories that ultimately succeed logically; seven events themselves converge. Fourteen events improve the best but occur in trajectories that still exhaust the budget. Stagnation before escape ranges from 122 to 1,338 iterations.

There are no qualifying p=0.002 events because the frozen condition never activates. Exact cases, including the preceding best, consecutive unproductive legs, escape leg, and improvement, are in `late_escape_cases.csv`.

These escapes are the central safety limitation: closeness to convergence improves prediction, but does not turn stagnation into proof of futility.

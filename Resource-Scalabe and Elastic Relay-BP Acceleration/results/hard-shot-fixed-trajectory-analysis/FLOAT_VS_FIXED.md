# A3 float versus fixed-point findings

The float study used the same workloads and gamma streams, but its paths did not reproduce the archived fixed-point iteration/leg outcomes. The fixed study here does reproduce all archived outcomes, so it is the primary evidence for hardware-oriented follow-up.

| A3 observation | Fixed-point classification | Evidence |
|---|---|---|
| Long running-best stagnation distinguishes hard paths | Reproduced strongly | Easy trajectories average a 4.3-iteration longest streak; severe/rescue paths 844; failures 1,775. |
| Hard paths have higher decision churn | Reproduced strongly | Easy mean churn is 69 bits/iteration versus 344 for severe/rescue paths; this remains movement rather than a causal explanation. |
| Many later legs consume work without durable progress | Reproduced strongly | At the 5-check rule, 192/254 legs (75.6%) are stagnant, regressive, or merely weak; only 48 (18.9%) are productive. |
| Hard behavior is a stagnation/oscillation/regression mixture | Reproduced strongly | Severe paths combine long no-best streaks, 974 churning-stagnation steps on average, residual increases, and many regressive endpoints. Exact repeats alone remain weak. |
| First-leg residual behavior is informative but insufficient | Reproduced weakly | Correlations with cycles are modest: residual/best at iteration 10 are 0.38/0.41 and end-of-leg no-improvement streak is 0.42. Exceptions are substantial. |
| Low marginal confidence accompanies difficulty | Reproduced weakly | Near-zero fraction is 0.0266 for easy versus 0.0417 for severe/rescue, and iteration-10 near-zero fraction correlates 0.40 with cycles. It is non-monotone across individual paths. |
| Initial syndrome weight alone is weak | Reproduced weakly | Fixed correlation with cycles is 0.33, larger than float's 0.05 but still inadequate: low-start-weight severe paths and high-start-weight easier paths coexist. |
| Exact residual repeats identify hard behavior | Contradicted as a standalone indicator | Repeats occur but churning without an exact repeat is far more common; failures average only a small number of frozen/repeated steps relative to 1,940 iterations. |
| A3's saved E1 rescue mechanism can be inferred from float | Cannot compare | Float changed four archived convergence classes. Only the exact fixed replay can explain those rescue pairs. |

The main findings that survive arithmetic change are running-best stagnation, continued decision/residual motion while stalled, and low relay-leg productivity. Marginal confidence and first-leg summaries retain weaker associations. Saturation is an additional fixed-only observable, but it is not a primary explanation here.

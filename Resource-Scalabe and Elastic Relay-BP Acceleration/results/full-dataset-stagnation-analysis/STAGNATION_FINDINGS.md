# Full-population stagnation findings

## Reproduction gate

All 128 archived N=1/E0 paths reproduced exactly: syndrome/logical hashes, convergence, logical classification, total iterations, relay legs, candidate weight, final RNG state, random-word count, and accepted-gamma count. There are no mismatches. Interpretation covers 24,433 iterations and 419 completed legs.

## Population and relay-leg productivity

The population has 69 one-leg successes, 56 multi-leg successes, and 3 failures. Under the strict-improvement definition, 223/419 legs (53.2%) are productive, 95 (22.7%) stagnant, and 101 (24.1%) regressive. Thus 196/419 legs (46.8%) establish no new global best.

This is outcome-dependent: all 69 one-leg successes are productive; multi-leg successes contain 147/254 productive legs (57.9%) and 107/254 unproductive legs (42.1%); failures contain only 7/96 productive legs (7.3%) and 89/96 unproductive legs (92.7%).

## Does stagnation predict future unproductivity?

Yes, with moderate—not decisive—discrimination. At completed leg boundaries:

| Target | Risk-set base rate | Stagnation threshold | Precision | Recall | Specificity | Balanced accuracy |
|---|---:|---:|---:|---:|---:|---:|
| Next leg unproductive | 67.4% (196/291) | 120 | 84.9% | 65.8% | 75.8% | 70.8% |
| Next 2 legs unproductive | 53.8% (155/288) | 120 | 74.5% | 71.6% | 71.4% | 71.5% |
| Next 3 legs unproductive | 45.3% (129/285) | 120 | 68.5% | 77.5% | 70.5% | 74.0% |
| Next 120 iterations unproductive | 53.8% (155/288) | 120 | 74.5% | 71.6% | 71.4% | 71.5% |

The relationship is monotone in precision. For Target 3, precision rises from 49.2% at 10 stagnant iterations to 59.4% at 60, 68.5% at 120, 75.0% at 180, and 79.4% at 240. Recall falls from 100% to 62.8%, so longer thresholds do not dominate shorter ones. Per-iteration metrics show the same association (Target 3 balanced accuracy about 0.73--0.75 at thresholds 60--180), but their thousands of rows are highly dependent and must not be interpreted as independent trials.

## Decision churn and other conditioning signals

Decision churn does not add a stable monotone signal beyond stagnation. Among Target-3 boundaries already stagnant for 120 iterations, future-unproductive rates are 82.1%, 64.0%, and 67.4% in low, medium, and high churn tertiles. At 60 iterations the corresponding Target-2 rates are 84.8%, 70.6%, and 56.9%, but at 120 they become 82.8%, 69.7%, and 77.3%. Low churn can indicate a more frozen path, yet the non-monotonic pattern and strong leg/outcome confounding make the incremental evidence weak.

Residual gap and current residual add modest monotone separation at the representative Target-3/120 boundary: rates are 57.6/68.0/74.6% across residual-gap tertiles and 59.0/71.2/72.7% across current-residual tertiles. Running-best residual is stronger: a best of at most 1 has an 80.3% Target-3 rate, versus very small groups at higher best values. Leg index is strongest descriptively (25.0/37.7/91.8% across tertiles), but it is also the clearest proxy for survival and accumulated exposure.

For multi-leg successes alone at the same Target-3/120 boundary, the base rate is only 36.6%; best residual at most 1 raises it to 50.0%, residual gap above 20 to 42.9%, and leg index above 8 to 68.2%. These smaller effects show why the all-population values must not be read as intrinsic predictor performance.

## Survivor-bias checks and earliest warning

The association remains but weakens materially after risk-set controls:

- Failure boundaries dominate late high-stagnation observations: for Target 3 at threshold 120, failures have 98.7% precision and 89.1% balanced accuracy, while multi-leg successes have 36.6% precision and 61.4% balanced accuracy.
- At legs 1--2, a 120-iteration stagnation threshold never fires; balanced accuracy is 0.50. At legs 3+, Target-3 precision is 68.5%, but specificity is only 36.1% because the late survivor risk set already has a 61.7% positive rate.
- Iterations 10 and 20 provide no warning from this counter because the counter cannot yet reach the tested meaningful durations. At iteration 40 and the first-leg endpoint, the few `>=40` cases are false positives for multi-leg targets. End-of-second-leg stagnation is also poorly discriminative in this sample.

The earliest defensible warning from **stagnation alone** is therefore after approximately 120 iterations without a new best, generally at or after the third leg. It can precede three additional unproductive legs, but it is not an early first-leg discriminator.

## False positives

The representative leg-boundary rule `stagnation >=120` for Target 3 produces 46 false-positive boundaries across 20 unique shots. These are important successful escapes, not noise. Examples include `(20260810,4)` at legs 6, 7, and 13--15 and `(20260810,9)` at legs 21--23: each later obtains a strict improvement within three legs despite a long prior stall. `population_summary.json` retains exact examples.

These cases prevent interpreting stagnation as proof of futility. They also show why this analysis cannot directly determine an action or stopping threshold.

## Direct conclusions

1. **All trajectories reproduced?** Yes, 128/128 with zero mismatches.
2. **How common are unproductive legs?** 196/419, or 46.8%; 42.1% even among multi-leg successes and 92.7% among failures.
3. **Does stagnation predict future unproductivity?** Yes.
4. **How strongly?** Moderately: at 120 iterations, balanced accuracy is 0.71--0.74 across targets and precision improves by about 11--23 percentage points over risk-set base rates.
5. **Does churn add information?** Weakly and inconsistently; no monotone incremental relationship is established.
6. **Most robust combination?** Stagnation duration plus running-best residual, with residual gap as a secondary descriptor. Leg index is informative but heavily survivor-confounded.
7. **Earliest useful warning?** About 120 no-best iterations, usually at/after leg 3; not iterations 10--40 or the first two leg endpoints.
8. **Important false positives?** Long-stalled successful paths that escape within three subsequent legs; 46 boundaries/20 shots for the representative rule.
9. **After survivor controls?** Present but weaker: multi-leg-success balanced accuracy is 0.61 versus 0.89 in failures at Target 3/120.
10. **Cheap observables?** Running best, stagnation counter, new-best flag, residual gap, and leg index are trivial/small. Churn is moderate.
11. **Why no heuristic yet?** Only three failures, one `p`/workload, repeated dependent observations, thresholds inspected in-sample, substantial survivor bias, and consequential successful false positives.
12. **Next analysis question:** On independent archived workloads or newly designated validation data across multiple `p` values, does a pre-registered combination of stagnation duration and running-best level retain calibration within the multi-leg-success/failure risk set?

## Overall assessment

The signal is **MODERATE**. Quantitatively, 120-iteration stagnation predicts three future unproductive legs with 68.5% precision, 77.5% recall, 70.5% specificity, and 74.0% balanced accuracy versus a 45.3% base rate. However, performance falls to 61.4% balanced accuracy within multi-leg successes and there are 46 representative false-positive boundaries, so the evidence is not strong enough to define a heuristic.

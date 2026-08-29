# Out-of-sample multi-p validation findings

## Population shift

| p | Shots | Multi-leg trajectories | Unproductive legs | Failures | Logical errors among converged |
|---:|---:|---:|---:|---:|---:|
| 0.002 | 64 | 17.2% | 4/81 = 4.9% | 0/64 | 0 |
| 0.003 discovery | 128 | 46.1% | 196/419 = 46.8% | 3/128 | 0 |
| 0.004 | 64 | 62.5% | 300/448 = 67.0% | 8/64 | 0 |

Unproductive work and failures rise sharply across these samples. This is an observed association across different deterministic workloads, not a fitted p-dependent model.

## Frozen 120 rule: Target 3

| p | Eligible boundaries | Base rate | Precision | Recall | Specificity | Balanced accuracy | False-positive boundaries |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.002 | 17 | 0.0% | undefined | undefined | 100% | undefined | 0 |
| 0.003 | 285 | 45.3% | 68.5% | 77.5% | 70.5% | 74.0% | 46 |
| 0.004 | 368 | 58.4% | 72.4% | 76.7% | 58.8% | 67.8% | 63 |

At p=0.004, precision and recall are close to discovery (+3.9 and −0.8 percentage points), but specificity falls 11.7 points and balanced accuracy falls 6.2 points. This is supportive but moderately shifted calibration.

At p=0.002, the maximum non-converged-boundary stagnation is only 112 iterations. The frozen rule never predicts positive, and no eligible boundary has three future unproductive legs. The rule therefore cannot be validated or refuted at this p; its operating region is absent.

For all four p=0.004 targets, frozen-rule balanced accuracy is 67.8–70.4%. For multi-leg successes alone, it is 66.8–69.6%; for eight failures, 60.3–63.9%, with high base rates and limited specificity. These are repeated boundaries, not independent-shot sample sizes.

## Threshold sensitivity—not tuning

For p=0.004 Target 3, precision is 67.9% at 60 iterations, 72.4% at the frozen 120, and 72.4% at 240. Thus the discovery relation “longer stagnation implies greater future unproductivity” is non-decreasing but plateaus. At p=0.003 it increased 59.4% → 68.5% → 79.4%. At p=0.002, four 60-iteration predictions are all false and no boundary reaches 120 or 240, so monotonicity is not assessable.

## Required conclusions

1. **Generalization to p=0.002:** Inconclusive. The regime is easier and never enters the frozen rule's operating region.
2. **Generalization to p=0.004:** Yes, moderately. Precision/recall remain similar, while specificity and balanced accuracy degrade.
3. **Is 120 reasonably stable?** For p=0.003→0.004, moderately stable; across all three p values, not yet established.
4. **Does running best affect false positives?** Yes materially: three-leg escape probability ranges from 11.4% at best=1 to 36.4% at best=4–8, with only nine observations above 8.
5. **Are residual-1 paths dangerous to terminate/redirect?** Termination is consequential: 9/79 improve to zero within three legs. They are less likely to escape than higher-best paths, so “especially dangerous” is not supported in relative-frequency terms. Resource redirection without termination was not evaluated.
6. **How common are successful late escapes?** At p=0.004, 26 escape events occur in 16 trajectories; 12 events belong to nine eventual logical successes. None qualify at p=0.002.
7. **Does unproductive work rise with p?** Yes in these samples: 4.9% → 46.8% → 67.0%.
8. **Are observables hardware-cheap?** Yes: running best, stagnation counter, residual gap, and leg index remain trivial/small incremental state. No RTL was assessed.
9. **Enough evidence to begin heuristic design?** No. The low-p regime provides no activation/calibration evidence, p=0.004 has only eight failures, and late escapes remain common.
10. **Exact design problem if yes:** Not applicable; design is not authorized or mature.
11. **Missing validation:** More independent seeds/shots, especially enough p=0.002 multi-leg paths; an independent confirmatory p=0.003 cohort; and evaluation of consequences for late successful escapes under a predeclared decision objective.

## Calibration classification

Across physical error rates the result is **inconclusive**. The p=0.004 signal generalizes moderately, but p=0.002 never reaches 120 stagnant iterations and supplies no positive Target-2/3/4 cases. Absence of activation is not evidence of stable calibration.

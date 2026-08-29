# Trajectory findings

## Reproduction boundary

All 13 syndromes and logical vectors passed their archived hash checks, and all
26 E0/E1 xorshift gamma streams were reconstructed exactly.  The archived study,
however, used fixed-point decoding.  These required canonical-float replays have
zero exact iteration/leg matches with those fixed trajectories.  Twenty-two of 26
convergence/logical classes match; the four mismatches are saved E0 failures
`(20260809,18)`, `(20260810,26)`, `(20260811,26)` becoming successful in float,
and saved E1 failure `(20260812,14)` becoming successful in float.

Consequently, “easy”, “severe”, and “rescue” are historical selection labels from
the fixed study.  They are not silently treated as float outcome labels.

## 1. What most clearly distinguishes easy from hard trajectories?

Within the canonical-float traces, the clearest difference is sustained progress
versus long periods without a new best residual.  The six easy-control trajectories
(E0/E1 duplicates for three shots) all converge in leg 1, average 41.3 iterations,
and have a mean longest no-best-improvement streak of 13 iterations.  The ten
historically severe trajectories average 540.6 iterations, 9.1 legs, and a longest
streak of 400.6 iterations.

Decision churn is also higher: mean per-iteration decision changes are 37.9 for
easy controls versus 305.8 for the historically severe group.  Residual-weight
increases average 13.3 versus 214.3 per trajectory, although much of this difference
is exposure to more iterations.  The approximate per-iteration rates are 32% and
40%, respectively.

## 2. What distinguishes successful E1 rescues from failing E0 trajectories?

That fixed-point mechanism is **not reproduced by the canonical-float replay**.
All three saved failing E0 paths converge in float:

- `(20260809,18)`: float E0 187 iterations/3 legs; E1 550/9.
- `(20260810,26)`: both float paths converge identically in leg 1 at iteration 46.
- `(20260811,26)`: float E0 352/6; E1 1263/21.

Thus no evidence-backed float claim can be made about “successful E1 versus failing
E0” for these three shots.  What can be observed is that, after identical first
legs, the longer float paths accumulate much longer stagnation: 456 versus 126
iterations for `(20260809,18)`, and 1107 versus 192 for `(20260811,26)`.

Only `(20260811,25)` has a substantial E1 advantage in this float panel: E1 uses
159 iterations/3 legs versus E0 460/8.  The other named fixed E1-major-improvement
cases reverse ordering in float, demonstrating arithmetic sensitivity.

## 3. Do hard trajectories show stagnation, oscillation, regression, or a mixture?

A mixture, dominated by stagnation relative to the running best and frequent
endpoint regression between legs.  Exact residual-vector repeats occur, as do
two-iteration returns, but they are not uniquely associated with hard traces:
easy trajectories actually have more exact repeats per iteration because they can
briefly revisit near-converged states.  Therefore exact repetition alone is not a
good hard-trajectory discriminator in this panel.

Residual-vector Hamming distance remains nonzero through many equal-weight steps,
showing that equal residual weight often hides continuing state motion.  This is
oscillation-like/churn behavior, not proof of a stable limit cycle.

## 4. Are there long relay legs with little useful progress?

Yes.  Of 122 full 60-iteration later legs, 61 end with a worse residual than they
started with.  Twenty full legs improve their within-leg minimum by at most two
checks.  Across hard/severe-labelled trajectories, endpoint classification gives
91 productive and 61 regressive legs.  No endpoint-equal legs occurred, so the
simple “stagnant” class is empty even though long no-global-best streaks are common.

Temporary within-leg improvements often disappear by the leg endpoint; this is why
minimum residual and endpoint residual are both retained.

## 5. Is first-leg behavior informative?

Moderately, but not deterministically.  Correlations with float total iterations
are 0.34 for first-leg ending residual, 0.27 for best first-leg residual, 0.42 for
residual at iteration 20, and 0.48 for the end-of-leg near-zero-belief fraction.
Initial residual has correlation only 0.05.

Easy and typical float paths reach residual zero during leg 1.  Most multileg paths
finish the first leg above zero and already show a larger residual at iterations
20–40.  Important exceptions remain: `(20260810,26)` converges in the float first
leg despite being a fixed-point failure, while some paths end leg 1 at residual
2–3 and still require several or many later legs.

## 6. Is initial syndrome weight alone useful?

No, not alone.  Its panel correlation with float iteration count is 0.05.  The
saved maximum-latency shot `(20260811,26)` begins at weight 130, lower than all
three easy controls (131, 144, and 153).  Conversely `(20260810,26)` begins at 233
but converges in 46 float iterations.

## 7. Are potentially usable early observables present?

Yes, descriptively: residual level and slope at fixed checkpoints, time since the
last global-best residual, residual-vector motion during equal-weight steps,
decision-bit churn, end-of-first-leg residual, and the near-zero-belief fraction.
These are available before full decoding completes.  Their hardware cost and
predictive reliability were not evaluated here.

## 8. Which signals are most promising for the next analysis?

The strongest next candidates are joint rather than single metrics:

1. running-best residual plus iterations since improvement;
2. residual endpoint versus within-leg minimum, to detect lost progress;
3. residual-vector distance when scalar residual weight is unchanged;
4. decision churn normalized by iteration count;
5. first-leg residual checkpoints combined with near-zero-belief fraction.

This is a prioritization for further analysis, not a heuristic proposal.

## 9. Robust versus anecdotal observations

Observed across several shots:

- E0/E1 first legs are identical in all 13 pairs.
- Diversity begins at global iteration 81 when both paths survive the first leg.
- Longer float paths consistently have longer no-best-improvement streaks.
- Many full relay legs end regressive despite temporary within-leg gains.
- Initial syndrome weight is weakly related to float difficulty.

Anecdotal or arithmetic-sensitive:

- The float direction of E0/E1 advantage for individual named rescue/major-win
  shots; several reverse relative to fixed point.
- Extremely large mean belief magnitudes in a few hard shots.
- Any claim that an exact residual repeat identifies a failure state.

## 10. What cannot be concluded?

This selected 13-shot panel cannot establish causation, population-level effect
sizes, a failure classifier, a fixed-point failure mechanism, hardware feasibility
of observables, logical-error-rate impact, or the value of any scheduling/folding
heuristic.  In particular, canonical-float traces cannot substitute for tracing the
archived fixed-point trajectories when explaining the N=1/N=2 hardware study.

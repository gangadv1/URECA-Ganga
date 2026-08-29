# First-leg analysis

The first leg is bit-for-bit common between E0 and E1 in all 13/13 shot pairs because it uses the same syndrome, prior, and uniform gamma=0.125. Diversity begins with later-leg gamma vectors.

## Recorded signals

For every trajectory the analysis records initial residual; residual after 5, 10,
20 and 40 iterations when reached; first-leg ending and best residual; longest
no-best-improvement streak; decision churn; mean/end belief magnitude; and the
fraction with `abs(belief) <= 1.0`.

## Exploratory correlations with canonical-float total iterations

```json
{
  "first_leg_best_residual": 0.27119044613422916,
  "first_leg_end_belief_abs": 0.010153008206704114,
  "first_leg_end_close_fraction": 0.4752563905981381,
  "first_leg_end_residual": 0.3429449480649821,
  "first_leg_longest_no_improvement": 0.11388316981954023,
  "first_leg_total_decision_changes": 0.26734726628666033,
  "initial_residual": 0.05078705116752296,
  "residual_after_10": 0.35161241579050556,
  "residual_after_20": 0.41664353282635097,
  "residual_after_40": 0.3706090266101629,
  "residual_after_5": 0.30212597270426567
}
```

The largest observed correlations are modest: end-of-first-leg near-zero-belief
fraction 0.48, residual at iteration 20 0.42, residual at iteration 40 0.37, and
end-of-first-leg residual 0.34.  Initial residual is only 0.05.  These correlations
are descriptive.  E0/E1 duplicate the same first-leg observation within a shot,
the panel is deliberately tail-enriched, and checkpoint values are missing when a
trajectory converges before that checkpoint.  No predictor was fit.

Initial syndrome weight is available before decoding, but the panel includes the
saved maximum-latency shot `(20260811,26)` with initial weight 130 and much easier
controls with comparable or greater weights.  It is therefore not sufficient by
itself as a difficulty indicator in this panel.

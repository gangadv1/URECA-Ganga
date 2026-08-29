# Fixed-point trajectory findings

## Reproduction boundary

All 26 E0/E1 trajectories exactly reproduce the archive on every required field. Interpretation below therefore applies to the fixed-point paths that generated the N=1/N=2 latency study, not float approximations.

## Direct answers

### 1. What most clearly distinguishes easy trajectories from hard ones?

Sustained running-best progress versus prolonged failure to establish a new best. The six easy engine trajectories converge in one leg and 17--22 iterations, with a mean longest no-best streak of 4.3. Severe/rescue trajectories average 1,102 iterations, 18.3 legs, and an 844-iteration longest streak; failures reach 1,940 iterations/32 legs and average a 1,775-iteration streak. Hard paths remain active: mean decision churn is 344 bits/iteration versus 69 for easy paths.

### 2. What distinguishes failed E0 paths from successful E1 rescues?

All pairs share iterations 1--80 exactly and first diverge at iteration 81, the first disordered leg. Successful E1 paths eventually establish a small number of durable new global bests and reach zero; failed E0 paths spend most later legs stagnant or regressive after reaching residual 1.

- `(20260809,18)`: E0 has 1 productive, 2 weak, 22 stagnant, 7 regressive legs and a 1,640-iteration maximum stall. E1 has 3/1/3/3 and converges at iteration 594; its final escape goes from residual 6 five iterations earlier to zero with only 40 decision flips in those five iterations.
- `(20260810,26)`: E0 has 2 productive and 30 unproductive legs, with a 1,811-iteration stall. E1's four legs are 3 productive plus 1 weak and it converges at 242.
- `(20260811,26)`: E0 has 1 productive, 1 weak, 19 stagnant, 11 regressive legs. E1 still struggles—2 productive, 1 weak, 9 stagnant, 9 regressive and a 1,090-iteration stall—but obtains the final residual-zero escape at 1,241.

The first disordered leg is not uniformly predictive: for `(20260809,18)` E0 briefly improves the global best from 8 to 5 while E1 does not, yet E1 ultimately wins. Gamma summaries differ after divergence, but no consistent gamma statistic identifies the winner and causation is not supported.

### 3. Are most expensive legs productive?

No. With a meaningful-improvement threshold of 5 checks, only 48/254 legs (18.9%) are productive; 14 (5.5%) are weak, 118 (46.5%) stagnant, and 74 (29.1%) regressive. The conclusion is threshold-robust: at thresholds 1 and 10, productive counts are 62 and 45, respectively. Many full 60-iteration legs therefore consume their entire budget without durable improvement.

### 4. Does fixed-point saturation explain failures?

No; it is at most a secondary correlate. Easy paths have no saturation and severe groups have more on average, but counterexamples are decisive:

- the one-leg typical paths show about 5.2% mean marginal saturation and over one million nu saturation events;
- hard `(20260810,4)` and `(20260810,9)` paths have no saturation;
- successful rescued E1 paths have *more* mean marginal saturation than failed paths (0.0040 versus 0.0032);
- for `(20260812,14)`, successful E0 has 0.0426 mean marginal saturation while failed E1 has 0.0089;
- mu and guarded-accumulator saturation are zero throughout all 15,123 iterations.

Repeated marginal/nu saturation sites and bursts exist, but they do not align consistently with failure or escape. Saturation cannot be the primary archived failure mechanism from this panel.

### 5. Is decision churn useful beyond scalar residual weight?

Yes descriptively. Hard paths often show large residual-vector and hard-decision movement while the scalar residual weight fails to beat its best. This separates frozen stagnation from churning stagnation: failures average about 1,726 churning-stagnation iterations but only a small number of frozen steps. Decision churn is therefore complementary to residual weight, though its independent predictive value has not been estimated.

### 6. Is residual-best stagnation robust?

Yes. It separates easy, severe, rescued, and failed groups strongly; appears in every long path; and is insensitive to the leg-category threshold. It is the most robust compact observable in this panel.

### 7. Is there repeated wasted work after progress stops?

Yes. Each failed E0 reaches residual 1 but then remains without a new best for 1,640--1,811 iterations. The reverse failed E1 stalls for 1,892 iterations. Combined with 192/254 nonproductive-or-weak legs, this is direct evidence of repeated work after durable progress has stopped.

### 8. Can hard paths be recognized substantially before exhaustion?

Some difficulty is visible early, but winners cannot be selected reliably from the first leg. Iteration-10/20 residual and running-best measures and time since best have correlations around 0.37--0.41 with cycles. By later legs, a long no-best streak plus repeated stagnant/regressive legs is a clear warning far before the 32-leg limit. Exact recognition performance was not evaluated.

### 9. Which signals appear usable by a future runtime analysis?

The most promising low-state observables are running-best residual, iterations since its last improvement, current residual, relay-leg endpoint/minimum versus the prior best, and a small counter of decision changes. These are candidate observables for further study, not a proposed heuristic.

### 10. Which signals are likely too expensive in hardware?

Dense mu/nu or marginal histories, full residual-vector comparison, per-edge repeated-saturation maps, medians, and exact residual-state cycle detection require substantially more storage/reduction logic than scalar counters. Their utility here does not establish hardware suitability.

### 11. Which float findings survive?

Strongly: long best-residual stagnation, churning motion during stagnation, low later-leg productivity, and initial syndrome weight being insufficient alone. Weakly: first-leg residual/marginal-confidence associations. The float replay could not reproduce the rescue outcomes, so fixed traces supersede it for rescue mechanisms. See `FLOAT_VS_FIXED.md`.

### 12. What cannot be concluded?

This panel cannot establish causality, generalize rates to all `p=0.003` shots, identify an optimal threshold, prove a predictor, assess logical-error-rate impact, quantify monitoring cost, or validate any scheduling/folding policy. It also cannot show that the observed gamma, churn, confidence, or saturation changes *cause* escape.

## Reverse counterexample: `(20260812,14)`

E0 succeeds at 403 iterations/7 legs; E1 exhausts 1,940/32. They first diverge at iteration 81. E0 eventually creates a second productive leg and reaches zero despite a 354-iteration stall; E1 reaches residual 1 but then spends 1,892 iterations without improvement, with 20 stagnant and 11 regressive legs after its sole productive leg. Failed E1 has less marginal saturation than successful E0, so saturation does not explain the reversal. The case demonstrates that allocating an independent path can consume a full budget without benefit; it does not by itself evaluate any resource-allocation policy.

## Failure-mode characterization

Hard trajectories are a mixture dominated by **churning stagnation**: the best residual stops improving while decisions and residual vectors continue moving. Regression is common at leg endpoints, and occasional near-best states are lost. Pure frozen states and exact repeats occur but are not the main cost. Successful rescues exhibit an escape event—ultimately a transition to residual zero—after independent later-leg exploration; that escape is not preceded by one consistent saturation, marginal-confidence, decision-churn, or gamma signature across all three cases.

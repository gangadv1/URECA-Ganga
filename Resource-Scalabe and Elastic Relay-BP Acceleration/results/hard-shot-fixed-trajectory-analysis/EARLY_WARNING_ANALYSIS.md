# Early-warning analysis

## What is available early

At iterations 5, 10, 20, 40, and the first-leg endpoint, the trace records residual weight and improvement, running best, time since the best, decision churn, marginal near-zero fraction (`|M| <= 16`), and marginal saturation fraction. These are compared descriptively with total iterations, legs, convergence, and archived cycles; no model or predictor was fit.

## Association with archived cycles

Across the 26 paired trajectories, the largest early correlations are modest:

- iteration 10 best residual: 0.41; iteration 10 residual: 0.38;
- iteration 20 time since best: 0.41; iteration 20 best/residual: 0.40/0.37;
- iteration 10 near-zero marginal fraction: 0.40;
- initial residual: 0.33;
- first-leg time since best: 0.42;
- first-leg decision churn: 0.25 and endpoint residual: 0.18.

Iteration-5 quantities are weaker (residual 0.35, best 0.34). Iteration-40 correlations are near zero because only trajectories that survive to that checkpoint contribute and many paths have already entered a common low-residual regime. Marginal saturation is zero at all fixed checkpoints and therefore has no checkpoint correlation.

## Interpretation

First-leg behavior contains some information, especially residual progress by iterations 10--20 and how long the path has failed to improve its running best. It is not deterministic. E0 and E1 have exactly identical first legs in every pair, including the three later E1 rescues and the reverse counterexample; first-leg signals can flag a difficult workload/path prefix but cannot choose which independent later trajectory will win.

Initial syndrome weight is not sufficient. Its 0.33 correlation is moderate in this selected fixed panel, yet `(20260811,26)` starts at 130 and fails on E0, while easy controls start at comparable or larger weights. Dynamic progress adds information unavailable from the starting weight.

The strongest early observables for the next *analysis* are running-best residual, time since last new best, residual at iterations 10--20, and decision churn conditioned on no best improvement. Near-zero marginal fraction is potentially informative but costs more to aggregate. Full residual-vector distance, dense marginal state, and edge-level saturation-site tracking are likely too expensive for routine hardware monitoring.

## Caveats

The sample is deliberately selected and small; E0/E1 duplicate first-leg values; early-converged paths censor later checkpoints; correlations mix shot difficulty with trajectory luck; and archived cycles are nearly determined by iteration/leg work. These results establish observability, not a threshold, policy, predictor, or causal mechanism.

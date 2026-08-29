# Full-dataset fixed-point stagnation analysis

## Purpose

This directory tests whether compact online observables predict *future* Relay-BP unproductivity across all 128 archived `p=0.003` N=1/E0 trajectories. It is observational analysis only: no decoder equation, arithmetic rule, gamma behavior, stopping rule, dataset, RTL, or architecture was changed.

## Exact replay

- Workload: `../circuit-level-multiseed/paired_samples.npz`.
- Archive: `../n1-vs-n2-hardware-latency/per_shot_results.csv` and `manifest.json`.
- Decoder: `reference/relay_bp_fixed.py::FixedRelayBPDecoder`, using its disabled-by-default observation callback.
- Locked configuration: signed b18, 22-bit guarded accumulator, `M=16`, `S=1`, `R=32`, first gamma `+2/16`, 80 first-leg iterations, 60 later-leg iterations, at most 32 legs, and the archived xorshift64 gamma sequence over `[-0.24,0.66]`.

All 128/128 E0 trajectories match workload hashes and every required archived outcome/RNG field. The trace contains 24,433 iterations and 419 legs.

## Future-only targets

At an observation point, the running best includes the current iteration. Targets use only later computation:

1. the next relay leg establishes no strict new global-best residual;
2. neither of the next two relay legs establishes one;
3. none of the next three relay legs establishes one;
4. 120 subsequent iterations elapse without a strict new global-best residual.

A negative target becomes determinable as soon as a future improvement occurs. A positive target is eligible only when the complete requested future horizon exists. Converged observation points are excluded. At a completed leg boundary, Target 4 usually coincides with Target 2 because later legs contain 60 iterations; both are retained because their definitions and possible within-leg observation points differ.

## Leg classification

- **Productive:** the leg converges or strictly improves the global best.
- **Regressive:** no global-best improvement and endpoint residual exceeds starting residual.
- **Stagnant:** no global-best improvement and endpoint is no worse than the start.

Unlike the prior hard-panel descriptive analysis, no five-check minimum is imposed: any strict future improvement makes a leg productive, matching the prediction targets.

## Statistical interpretation

Iteration rows and boundaries within a shot are correlated and are not treated as independent experimental replicates. Metrics are descriptive risk-set counts, not confidence intervals. Tables explicitly include eligible denominators and outcome/early-late strata to expose survivor bias. Churn and other signals use fixed tertiles derived from all non-converged leg boundaries; no threshold optimization or black-box model was performed.

## Files

- `reproduction_summary.json`: exact per-shot replay checks.
- `per_iteration_compact.csv`: online scalar observations and future targets.
- `per_leg_summary.csv`: completed-leg observations and future targets.
- `threshold_analysis.csv`: iteration/boundary confusion metrics, including survivor strata.
- `churn_conditioned_analysis.csv`: transparent tertile conditioning for churn, residual gap, residual, running best, and leg index.
- `checkpoint_analysis.csv`: iterations 10/20/40 and first/second/later leg-boundary risk sets.
- `population_summary.json`: population counts, definitions, and representative false positives.
- `STAGNATION_FINDINGS.md` and `HARDWARE_OBSERVABILITY.md`: interpretation.
- `stagnation_precision.png` and `leg_categories.png`: focused plots.
- `run_analysis.py` and `postprocess.py`: deterministic analysis programs.

## Limitations

The dataset contains only three N=1 failures, all at one physical error rate and code/circuit package. Repeated observations within a trajectory are dependent, thresholds were inspected on this same dataset, later risk sets are enriched for difficult trajectories, and predictive association is not causal or sufficient to define a runtime policy.

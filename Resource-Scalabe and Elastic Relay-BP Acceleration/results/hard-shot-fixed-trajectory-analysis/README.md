# Fixed-point hard-shot trajectory analysis

## Purpose

This directory contains a semantics-preserving replay and compact trajectory analysis of the locked fixed-point Relay-BP decoder for the selected 13-shot `p=0.003` panel. It explains archived N=1 failures, N=2 rescues, severe tails, and the reverse counterexample without changing the decoder equations, arithmetic, gamma law, stopping rules, or hardware.

## Exact panel

`(20260809,31)`, `(20260810,15)`, `(20260811,6)`, `(20260809,2)`, `(20260810,22)`, `(20260811,25)`, `(20260812,14)`, `(20260811,28)`, `(20260810,4)`, `(20260810,9)`, `(20260809,18)`, `(20260810,26)`, `(20260811,26)`.

Each tuple is `(sample_seed, shot)`. Both archived engines, E0 and E1, were replayed, giving 26 trajectories.

## Reproduction

- Workloads: `../circuit-level-multiseed/paired_samples.npz`, indexed by the archive's `sample_seeds` and per-seed shot axis.
- Archived expected results and hashes: `../n1-vs-n2-hardware-latency/per_shot_results.csv` and its manifest/configuration.
- Decoder: `reference/relay_bp_fixed.py::FixedRelayBPDecoder`.
- Gamma source: the archived 64-bit engine seed and `reference/gamma_rng_reference.py` hardware-xorshift rejection stream.
- Locked arithmetic: `b=18`, 22-bit guarded accumulator, `M=16`, separate scale, no explicit clip override; first leg gamma is exactly `0.125`.
- Limits: 80 iterations in leg 1, 60 in later legs, 32 legs.

All 26/26 trajectories exactly match the archive for convergence, logical classification, iteration count, relay-leg count, selected candidate weight, final RNG state, random-word count, and accepted-gamma count. Workload syndrome and observed-logical hashes also match. See `reproduction_summary.json`.

## Instrumentation and definitions

The decoder exposes an optional callback, disabled by default, after each iteration's existing state calculation. A callback-on/off equivalence check produced the same result and saturation totals. The hook observes state only.

- Marginal near zero: `|M| <= 16`, one fixed-point integer unit at the selected threshold.
- Marginal saturation: `+131071` or `-131072` for signed b18.
- Meaningful new-best improvement: at least 5 residual checks. Sensitivity is also reported at thresholds 1 and 10.
- Productive leg: converges or improves the prior global best by at least 5.
- Weak leg: improves the prior global best by 1--4.
- Regressive leg: establishes no new global best and ends at least 5 checks worse than it began.
- Stagnant leg: establishes no new global best and is not regressive.
- Frozen stagnation: no new best, residual-vector movement and decision movement both at most 2 bits.
- Churning stagnation: no new best and either movement is at least 10 bits.

Dense message arrays are not saved. The CSV contains scalar summaries, residual-vector movement/repetition, decision churn, and saturation counts. Repeated saturation-site counts are derived online.

## Contents

- `per_iteration_trace.csv`: 15,123 compact iteration rows.
- `per_leg_summary.csv`: 254 relay-leg rows.
- `per_trajectory_summary.csv`: 26 trajectory rows.
- `rescue_case_analysis.json`: paired rescue and counterexample details.
- `analysis_summary.json`: aggregate groups, early correlations, and category-threshold sensitivity.
- `FLOAT_VS_FIXED.md`, `FIXED_TRAJECTORY_FINDINGS.md`, `EARLY_WARNING_ANALYSIS.md`: interpretation.
- Seven PNG files: the requested high-value plots only.
- `run_analysis.py`: deterministic replay/analysis driver.

## Limitations

This is a selected, tail-enriched 13-shot panel, not a population sample. E0/E1 share the deterministic first leg, so first-leg rows are paired duplicates. Correlations are exploratory, checkpoint samples are censored when decoding finishes early, and observed associations do not establish causality or justify a heuristic.

# Hard-shot trajectory analysis

## Purpose

Compact per-iteration analysis of the locked 13-shot p=0.003 panel using
`reference/relay_bp_float.py::FloatRelayBPDecoder`.  No STIM samples are generated.

## Exact panel

- `(20260809, 31)`
- `(20260810, 15)`
- `(20260811, 6)`
- `(20260809, 2)`
- `(20260810, 22)`
- `(20260811, 25)`
- `(20260812, 14)`
- `(20260811, 28)`
- `(20260810, 4)`
- `(20260810, 9)`
- `(20260809, 18)`
- `(20260810, 26)`
- `(20260811, 26)`

Each workload is recovered from `results/circuit-level-multiseed/paired_samples.npz`.
The syndrome and logical hashes are checked against
`results/n1-vs-n2-hardware-latency/per_shot_results.csv` before decoding.

## Methodology

- Both E0 and E1 are replayed for every shot.
- E0 uses saved seed `s0`; E1 uses saved seed `s1`.
- The exact xorshift64/rejection-map gamma vectors are reconstructed with
  `fpga/verification/parallel_n2/gamma_rng_reference.py` and supplied explicitly.
- First leg is gamma 0.125 for 80 iterations; later legs are limited to 60;
  S=1 and R=32 are unchanged.
- A disabled-by-default callback observes completed canonical-float iterations.
- Dense mu/nu matrices are not saved.
- "Close to zero" means `abs(belief) <= 1.0` in float LLR units.

Relay-leg classes use a simple endpoint rule: productive if ending residual is
below starting residual, regressive if it is above, and stagnant if equal.  The
minimum/best fields separately retain temporary within-leg progress.

## Reproduction boundary

The archived latency study used `FixedRelayBPDecoder`, while this analysis is
required to use the canonical float decoder.  Workloads and gamma streams are
exactly reproducible, but fixed-point iteration/leg trajectories are not expected
to be identical.  There are 26/26 iteration/leg mismatches and
4/26 convergence/logical-class mismatches versus the saved
fixed study; these are explicitly retained in `per_trajectory_summary.csv`.

## Outputs

- `per_iteration_trace.csv`: compact iteration metrics and state hashes.
- `per_leg_summary.csv`: relay-leg productivity summaries.
- `per_trajectory_summary.csv`: float replay and saved-fixed comparison.
- `comparison_summary.json`: grouped and paired summaries.
- `FIRST_LEG_ANALYSIS.md` and `TRAJECTORY_FINDINGS.md`.
- Five focused plots.

## Limitations

- This is a selected 13-shot panel, not an unbiased performance sample.
- Float trajectories characterize canonical algorithm behavior but do not replace
  the saved fixed/RTL-calibrated hardware results.
- Residual hashes detect exact repeats; they do not prove a dynamical limit cycle.
- Associations are descriptive and cannot establish causation or justify a heuristic.

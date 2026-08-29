# Multi-p stagnation validation

## Purpose

This is an out-of-sample validation of the frozen p=0.003 rule `iterations since last strict new best >= 120` at completed relay-leg boundaries. No decoder, arithmetic, gamma, stopping, graph, RTL, or prior result was modified, and no threshold was optimized on validation data.

## Workload audit and sampling

Official circuit/DEM graph packages already existed at:

- `graphs/generated/gross_circuit_level/memory_Z_r12_p0p002`
- `graphs/generated/gross_circuit_level/memory_Z_r12_p0p004`

Each contains `circuit.stim`, its DEM, fault probabilities, detector/logical incidence, and only 16 saved circuit samples with both detector syndrome and logical observation (`circuit_samples.npz`, seed `20250617`). No saved fixed-point trajectory population existed at p=0.002 or p=0.004. The separate `official-crosscheck-high-p/inputs_0p004.npz` has 16 p=0.004 inputs but likewise does not meet the 64-shot design.

Therefore, 64 new deterministic circuit samples were drawn from each existing `circuit.stim`, without regenerating graph packages:

- p=0.002: sample seed `20260902`
- p=0.004: sample seed `20260904`

Neither seed was used in discovery. Exact syndromes/logicals are saved in `validation_samples.npz`; packed hashes are retained per shot. Decoder seeds use the archived formula `splitmix64(BASE_SEED ^ sample_seed ^ (shot * 0x100000001b3))`.

## Locked replay configuration

`FixedRelayBPDecoder`, signed b18 messages, 22-bit guarded accumulator, `M=16`, `S=1`, `R=32`, first gamma `+2/16`, 80 first-leg iterations, 60 later-leg iterations, xorshift64 hardware gamma semantics, and later interval `[-0.24,0.66]`.

The existing disabled-by-default observation callback is unchanged. Dense messages are not stored.

## Frozen targets

At each completed leg boundary, the pre-registered rule predicts:

1. no new global best in the next leg;
2. no new global best in either of the next two legs;
3. no new global best in any of the next three legs;
4. no new global best during the next 120 iterations.

Eligibility follows discovery: an improvement determines a negative target immediately; a positive target requires the complete future horizon; converged boundaries are excluded. Sensitivity at 60 and 240 is context only.

## Contents

- `manifest.json`: packages, seeds, locked configuration, and runtime.
- `validation_samples.npz`: exact newly sampled workloads.
- `per_shot_results.csv`: hashes, seed/RNG outcome, logical result, work, and runtime.
- `per_leg_summary.csv`: compact leg state and future targets.
- `validation_metrics.json`: frozen-rule metrics and running-best strata.
- `cross_p_comparison.csv`: p=0.002, reused p=0.003, and p=0.004 comparison.
- `late_escape_cases.csv`: every qualifying validation escape event.
- `MULTI_P_VALIDATION.md` and `RUNNING_BEST_ANALYSIS.md`: interpretation.
- Four focused PNG plots.

## Limitations

There are 64 shots per validation p, zero p=0.002 failures, eight p=0.004 failures, dependent boundaries within trajectories, and only one new sample seed per p. The frozen rule never activates at p=0.002. These facts preclude a general calibrated policy or confidence claim.

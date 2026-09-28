# Matched software experiment specification

## Status

Do not run the large benchmark until the reproduction check and the adapter validation pass. The proposed comparison is valid in principle, but the current status is **NOT_READY**.

## Frozen workload

Use the current URECA circuit-level artifact:

`graphs/generated/gross_circuit_level/memory_Z_r12_p0p003/circuit.stim`

It is the [[144,12,12]] Gross/bivariate-bicycle Z-memory circuit with 12 noisy QEC rounds, p=0.003 uniform-circuit noise, 288 circuit qubits, 1,728 detectors, and 12 observables. Freeze the circuit bytes and SHA-256 from its package manifest. Do not substitute the GARI default p=0.002 CL file during the matched run.

Use the existing paired panel first: Stim seeds `20260809, 20260810, 20260811, 20260812, 20260813`, 128 shots per seed, 640 unique shots. The arrays are in `results/circuit-level-multiseed/paired_samples.npz` as `syndromes` and `observed_logicals`. A later confidence run may expand the panel, but must preserve the exact generation protocol and report the seed list.

## Decoder inputs

Both decoders receive only:

1. the same detector-bit row `syndromes[seed_index, shot]`;
2. the same observable label row `observed_logicals[seed_index, shot]`, used only for scoring;
3. decoder-side static graph/matrix metadata and a declared prior model.

Neither decoder may receive sampled physical errors, DEM error IDs, `true_error`, or any postselected information. GARI's `err_data` output must remain unused. Relay-BP uses the packaged per-fault probabilities and `log((1-p_j)/p_j)` priors.

## GARI adapter gate

Before comparison, construct a read-only adapter that takes the frozen URECA circuit/DEM and reproduces GARI's `detector_error_model_to_check_matrices` plus `det_and_err_encoding` contract. Validate detector count, observable count, X/Z detector partition, fault-variable count, matrix shapes, detector order, and parity reconstruction on a tiny fixed sample. Compare no decoder outputs yet; the gate is structural and input-boundary focused. Record hashes of all adapter artifacts.

## Relay-BP configuration

Use the canonical float implementation and the validated high-success configuration: `S=1`, `R=32`, first relay leg maximum 80 iterations with gamma 0.125, later legs maximum 60 iterations with per-node gamma drawn from `[-0.12, 0.54]`, decoder seed `9100 + shot_index`. The canonical N=1/N=2 first-success selection is retained as a separate Relay-BP scaling experiment, not treated as equivalent to a GARI ensemble.

## GARI configuration

First reproduce the official original configuration in `reproduction_plan.md`. For the matched run, hold GARI's native normalization, iteration, schedule, prior, and ensemble settings fixed in a declared configuration. Do not tune GARI to make outputs agree with Relay-BP. If the original GARI decoder cannot consume this circuit after the adapter without source changes, stop and report the blocker instead of changing its algorithm.

## Outputs per shot

Store for each decoder:

- decoded correction in the decoder's native variable basis;
- predicted detector syndrome;
- predicted logical observables;
- syndrome-valid/converged flag;
- logical-correct flag;
- logical failure among syndrome-valid shots;
- native iteration count and relay legs or GARI ensemble iteration statistic;
- native winner/selection identifier;
- decoder wall-clock duration measured around decode only.

Store the common input hashes and circuit/package hashes in every result manifest.

## Predicates and rates

The common syndrome predicate is `H_common @ correction mod 2 == sampled_detector_bits` after each decoder's documented variable-to-fault mapping. The common logical predicate is `A_common @ correction mod 2 == observed_logicals`. Report:

- all-shot failure rate, counting nonconvergence as failure;
- syndrome-valid logical-error rate;
- nonconvergence rate;
- success rate conditional on syndrome convergence;
- LER as the empirical all-shot logical/block failure rate for this common panel.

Do not silently convert the two implementations to different per-round conventions. If a per-round LER is also reported, state the exact Sinter conversion, number of rounds, and K, and keep it secondary to the common all-shot predicate.

## Iteration and cost metrics

Do not equate one GARI normalized-min-sum iteration to one Relay-BP iteration. Report native counts separately. Add an implementation-independent workload metric where available: detector-check/fault-variable message-update count, total edge updates, and number of candidate corrections evaluated. For software timing, use a warmed-up monotonic wall-clock measurement on the same machine, with setup, sampling, compilation, and file I/O excluded and the timing protocol recorded. Report median, p90, p95, and p99 only when the shot count supports a stable tail; with 640 shots, label p99 as an empirical tail estimate.

Modeled Relay-BP BA2/P cycles are reported as modeled architectural work only. They must never be labeled FPGA latency and must not be compared with GARI FPGA nanoseconds. If actual FPGA timing is later measured, it is a separate result class.

## Required stop conditions

Stop before benchmark if any of these fail: original GARI reproduction; frozen-circuit byte/hash check; matrix shape/order check; no-hidden-error audit; common syndrome reconstruction; or logical observable mapping check.
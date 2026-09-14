# Canonical STIM pipeline validation

This directory contains a small correctness and information-boundary campaign,
not a performance benchmark. It tests the current canonical floating-point
Relay-BP implementation and the saved Gross memory-Z circuit. It never imports
the legacy simulators or their error-dependent priors. Historical artifacts and
decoder equations are not modified.

Run from the repository root:

```sh
.venv/bin/python -B 'Resource-Scalabe and Elastic Relay-BP Acceleration/results/stim-pipeline-validation/run_stim_pipeline_validation.py'
```

The runner writes only within this new directory. Decoder workers exchange
allowlisted arrays through temporary directories, which are removed after use.
It runs 40 bounded decoder invocations: 16 noiseless, four original, four replay,
four shuffled, four one-iteration, two under each of two trajectory seeds, and
four elevated-noise. A further four shots check sampling with a changed STIM
seed without decoding. Replay/corrupted/budget/seed panels reuse inputs and are
not independent physical trials. No result is a statistically useful LER estimate.

## Fixed settings and provenance

The original circuit is `graphs/generated/gross_circuit_level/memory_Z_r12_p0p003/circuit.stim`.
The runner reads its instructions to establish noise probability and the number
of paired noisy ancilla readouts. STIM supplies counts of qubits, measurements,
detectors and observables. The circuit DEM is independently extracted and
compared exactly against saved incidence matrices, fault probabilities and DEM.
Circuit, decoder, scorer and runner hashes and the current Git HEAD are recorded.
Code distance 12 is inherited identity, not independently proved here.

The first execution stopped at an inappropriate in-memory DEM equality check.
STIM's own `DetectorErrorModel(str(dem))` round trip changes some probabilities
by at most 4.34e-19, although its serialized text is identical. The saved NPZ
probabilities and both incidence matrices match the regenerated arrays exactly.
`attempt_001_dem_roundtrip/` preserves that runner snapshot and all failed
outputs. The current check requires exact serialized DEM equality and retains
the exact NPZ checks. No decoder ran in that first attempt. This is a corrected
serialization assertion, not a changed decoder, seed, scientific expectation or
acceptance threshold.

The normal bounded decoder has S=1, a first 80-iteration leg at gamma=0.125,
then one 60-iteration leg with per-node gamma in [-0.24,0.66]. This intentionally
truncates the canonical default R=301 to R=2 without changing equations. The
tiny-budget control has one iteration. Seed probes use S=2 and two one-iteration
legs to ensure the randomized second leg is reached even if the first converges.
Each panel uses one persistent decoder RNG, as the canonical baseline does;
replay preserves shot order. STIM seed is 20260808, decoder seed 91, changed
seeds are 20260809 and 92. No seed is selected based on a successful outcome.

## Controls and scientific meaning

| Case | Check and scientific purpose |
|---|---|
| information_boundary | A fresh worker process receives only CSR H, static DEM probabilities and syndromes. Seed/settings are explicit arguments. Runtime profiling inspects every actual `FloatRelayBPDecoder.decode` entry and validates the object, argument identities and hashes. No logical matrix, labels, realized fault IDs, expected correction or winner enters the worker payload. |
| noiseless_circuit | STIM `Circuit.without_noise()` removes stochastic channels and measurement noise from the actual circuit. Sixteen real samples must have zero detector/logical flips and decode successfully. This is not a manually supplied zero syndrome. Structural counts must remain unchanged. Unexpected nonzero samples stop dependent work. |
| logical_label_isolation | Logical labels are altered only in the scoring process after the first decode. Identical legitimate inputs are decoded again in a fresh worker. Corrections, convergence, iterations and residuals must remain identical; the actual canonical scorer must detect changed labels. |
| shuffled_syndrome_negative_control | A fixed permutation changes detector bits without permuting H. Per-shot correction, convergence, residual and score comparisons must show that the corruption is not silently equivalent. Scores against both the corrupted input and original sample are retained. |
| invalid_correction_scoring | Construct a valid reference by GF(2) elimination, then test a zero candidate on a nonzero syndrome, a one-bit perturbation on a nonempty H column, and a deterministic random candidate. All three negative candidates must be syndrome-invalid and unsuccessful. No decoder is called for this control. |
| syndrome_valid_logically_wrong | Solve the actual augmented system [H;A] for the original syndrome and a flipped logical target. Check the resulting bit vector using both scorers. If unconstructible, report WARNING and UNSATISFIED/NOT-CONSTRUCTED rather than fabricate success. |
| nonconvergence_accounting | A one-iteration budget must exercise at least one non-converged shot. Every such shot remains a scored failure in the four-shot denominator. |
| same_seed_reproducibility | Resample and re-decode the four-shot panel with identical settings. All sample bits, corrections, convergence, iterations and residuals must match. |
| changed_stim_seed | Changing only the STIM seed must produce a nonidentical panel. This does not claim that each individual shot differs. |
| changed_decoder_seed | Changing only the trajectory seed must reach the actual RNG state and sampled second-leg gamma evidence. A different final correction is not required. |
| high_noise_destructive_control | A typed instruction transformation raises each existing supported uniform noise parameter to 0.02 while preserving targets, tags, perfect final readout and noise-free circuit semantics. A new matching DEM/prior is derived. Four samples must produce detector events and at least one failure under the same bounded budget. No specific failure rate is required. |
| no_postselection_or_dropped_shots | Stage counts and saved shot IDs must agree for every decoder panel. Exceptions are retained as explicit failure rows and fail the suite. Decoder budget exhaustion remains an ordinary scored outcome. |

The independent scorer computes integer GF(2) products. It compares every score
with the five scoring assignments extracted by AST from the actual canonical
baseline script. Thus an incorrect canonical scorer is not silently bypassed
by a replacement implementation. Success requires BOTH H correction agreement
and A logical agreement. Constructed candidates and logical labels are available
only to scoring-side code, never to the decoder worker.
The runner also checks the canonical baseline's static-prior expression and
unfiltered decode comprehension through AST inspection, failing closed if they
change. Dynamic stage counts apply to this new validation, not historical jobs.

## Artifacts and failure handling

- `validation_summary.json`: provenance, cases, per-panel accounting, actual-call
  audit records, RNG evidence, candidate constructions, and scientific warnings.
- `validation_cases.csv`: one row per requested control, including failures or
  cases not executed because a prerequisite failed.
- `per_shot_results.csv`: every scheduled decoder invocation, including explicit
  exception rows. Non-convergence is never removed.
- `validation_evidence.npz`: sampled syndromes/labels, corrections, residuals,
  deterministic permutation, modified labels and constructed scoring candidates.

Output files are generated by the runner; normal subsequent execution replaces
this validation area's outputs only. A failed control exits nonzero. A required
control that cannot run fails; the explicitly permitted unconstructed logical
candidate is a warning. The suite never retries different seeds, increases
budgets, selects easier shots, or changes scientific expectations to obtain PASS.
The instruction/DEM setup is validated before expensive decoder work. There is
no wall-clock cutoff that would censor difficult successful or unsuccessful
shots; all decoder iterations are bounded in advance.

## Limits

- Isolation and profiling establish this runner's dataflow; they are not an OS
  sandbox proof against malicious decoder source that deliberately reads files.
- These controls test the current floating-point implementation, not every
  historical revision, fixed-point representation, RTL engine or N-lane arbiter.
- The original noisy static priors are deliberately retained for the noiseless
  control, avoiding a zero-fault DEM and infinite LLRs. High-noise priors instead
  match the newly derived noisy circuit.
- Shuffled syndromes are corrupted observations, not necessarily algebraically
  impossible syndromes. Their original logical labels do not define a physical
  experiment paired with the corrupted input, so their scores are diagnostic.
- A small high-noise control cannot validate threshold behavior or LER accuracy.
- Historical decoder hashes, interrupted LER batches and resource/latency claims
  remain unresolved. Passing these tests alone does not authorize scientific
  conclusions from N=4 or N×P benchmarks. Freeze a benchmark protocol and verify
  the actual fixed-point/multilane path before starting those experiments.

Read `overall_status` and individual case evidence in the generated summary for
the observed result; this README does not predeclare that the suite passes.

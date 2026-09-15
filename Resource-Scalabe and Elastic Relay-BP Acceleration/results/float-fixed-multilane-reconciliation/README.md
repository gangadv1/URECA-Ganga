# Float / fixed / N=2 reconciliation

This is a correctness and numerical-equivalence study using committed decoder
sources and saved STIM inputs. It does not generate STIM samples, run N=4 or an
N×P sweep, modify decoder mathematics, or measure hardware performance.

Run from the repository root:

```sh
.venv/bin/python -B 'Resource-Scalabe and Elastic Relay-BP Acceleration/results/float-fixed-multilane-reconciliation/run_reconciliation.py'
```

The script checks each selected source against its bytes at Git HEAD before
decoding. It records paths, hashes, signatures, defaults, alternatives, and the
reason for selecting the current N2 study in `reconciliation_summary.json`.
All writes stay in this new directory or temporary compiler directories.

## Implementations and scope

- Float: `reference/relay_bp_float.py:FloatRelayBPDecoder.decode`.
- Fixed: `reference/relay_bp_fixed.py:FixedRelayBPDecoder.decode`, configured as
  the current N2 study: b=18, g=4, M=16, S=1, R=32.
- N2: `results/n1-vs-n2-hardware-latency/run_study.py:task`, which calls the fixed
  decoder twice using seeds from `seeds(sample_seed, shot)` and gamma vectors
  from `fpga/verification/parallel_n2/gamma_rng_reference.py`.
- Actual hardware sources: `fpga/rtl/relay_bp_parallel_n2_p4.sv`, its fixed-point
  engines/controllers, and `relay_bp_first_success_arbiter_n2.sv`. The suite runs
  only the existing small arbiter test and a generated variable-node numerical
  fixture, not complete Gross RTL decoding.

The earlier `parallel-trajectory-model` uses different gamma bounds/seeds and an
iteration-based selector. The `fpga/model` implementation is a behavioral demo,
and `relay_models/parallel_lanes` re-exports legacy models. Block-floating and
separated-exponent fixed decoders are alternatives not used by the selected
hardware-seeded N2 study. They are inventoried, not silently substituted.

## Frozen panel and alignment

The previous STIM validation has four ordinary real shots, too few for this
study. Therefore the runner uses the committed
`results/circuit-level-multiseed/paired_samples.npz`: 640 available shots,
detectors shaped (5,128,1728), logical labels shaped (5,128,12).

The predeclared subset is seed 20260809 shots 0–29, plus 20260810/26 and
20260811/26. This includes the three raw-CSV-confirmed historical rescue IDs
20260809/18, 20260810/26 and 20260811/26. It is deliberately rescue-enriched and
cannot support unbiased LER or latency estimates. No shot is selected based on
its new result.

`configuration_alignment.csv` documents the comparison. Float and fixed lane0
receive identical H, static prior source, syndrome, S, R, 80/60 iteration limits
and exact realized hardware gamma vectors (encoded values divided by 16).
Internal NumPy seeds are zero and inactive because gamma arrays are explicit.
The hardware gamma-generation seed is the actual trajectory seed. This is an
explicit alignment to the existing N2 protocol, not a claim that constructor
defaults already match. Float defaults R=301; the generic fixed config defaults
to a much smaller unrelated example.

Both standalone fixed lanes run separately from the actual N2 task. A runtime
profiler observes its actual decode entries and captures each `decode_one`
return. It verifies input values, graph, numerical format and gamma schedules.
Logical labels remain scoring-only: they are available to the outer existing
wrapper but not passed into `FixedRelayBPDecoder.decode`.

The actual arbitration assignments are extracted from the frozen N2 source and
tested on 48 combinations of valid/failed lanes, completion times, ties, and
logical labels. The independent expected selector uses the earliest valid
completion, with lane0 priority on ties. Ensemble candidate validity is distinct
from logical success. A valid but wrong-logical first winner must not be replaced
by a later logically correct lane.

## Numerical evidence and classification

Stored fixed priors/messages/bias/marginal use signed 18-bit integers with zero
fractional bits; gamma uses scale16 (four fractional bits); guard sums use 22
bits. Rounding is nearest with ties away from zero, and stored values saturate.
Python temporaries are int64. `numerical_values.csv` includes ordinary values,
halfway cases and saturation boundaries; summary statistics also cover actual
DEM priors.

Every standalone fixed iteration is checked by an independent integer oracle:
segmented check-node reductions, integer `add.at` variable sums, explicit rounding
and clipping, and GF(2) residuals. The oracle does not call decoder arithmetic
helpers for its transitions. It observes but does not mutate decoder state.
Saturation deltas are recorded by shot, lane, leg and iteration. A separate
first-iteration floating-point calculation validates the numerical comparison
origin, and per-iteration hard decisions locate the first trajectory divergence.
Actual N2 calls have no callbacks, so agreement also checks that observers did
not alter the standalone result.

- `EXACT_MATCH` means matching final correction, convergence/outcome class,
  iterations and relay legs; float and integer internal messages may differ.
- `QUANTIZATION_ONLY` requires aligned inputs/configuration, independent exact
  integer transitions throughout, and an explained initial numeric difference.
- `CONVERGENCE_CLASS_CHANGE` and `LOGICAL_CLASS_CHANGE` retain the scientifically
  important outcome difference even when `numerical_origin_explained` is true.
- The logical class is NONCONVERGED, VALID_CORRECT, or VALID_LOGICAL_FAILURE.
  Incidental logical-label matches of invalid corrections are separately recorded
  but do not turn them into successful corrections.
- `IMPLEMENTATION_MISMATCH`, `PARAMETER_MISMATCH` and `UNRESOLVED` are never
  relabeled as quantization to make the suite pass.

The numerical RTL fixture deliberately exercises saturation: software subtracts
the incoming edge message from the unclipped bias-plus-sum, whereas the current
RTL subtracts it from an already clipped marginal. The suite preserves the
observed result of that comparison; these are potentially different arithmetic
semantics, not an architectural scheduling explanation. It also records whether
the difference is exercised during the real saved-shot runs.

## Historical source reconciliation

The runner searches reachable decoder blobs and unreachable Git blobs by exact
SHA-256, and preserves recovered bytes under `historical_sources/` along with
unified diffs. A recorded commit whose source differs from the manifest hash is
not silently substituted. The baseline's exact generating source was found in
an unreachable object; preserving it avoids loss during Git garbage collection.

An explicit AST normalization removes only observation hooks, added metadata and
the optional handoff switch specialized to its unchanged True default. No
decoder arithmetic is normalized. The historical comparison reports whether the
normalized default execution path is identical, separately from byte identity.

Current N2 outcomes, iteration/leg counts, winners and modeled completion are
compared against the primary archived CSV. That CSV has no raw correction bits;
the paired-equivalence CSVs provide additional correction hashes. The runner
checks their syndrome and gamma-seed identity before using them. A differing
hash is not converted into an invented Hamming count.

## Outputs and interpretation

- `reconciliation_summary.json`: source inventory, historical hashes/differences,
  alignment, numerical/arbiter/RTL results, aggregation, failure reasons, N4 gate.
- `per_shot_comparison.csv`: all 32 scheduled cases, including explicit exceptions.
- `mismatch_details.csv`: every observed float/fixed mismatch, historical mismatch
  or numerical RTL counterexample, with evidence references.
- `reconciliation_evidence.npz`: saved-input identities and float, standalone
  fixed and actual N2 corrections, plus first-iteration float numerical arrays.
- `checkpoints/`: per-shot JSON traces and NPZ evidence, written as each job
  finishes. No timeout or non-converged shot is dropped.
- `historical_current_comparison.csv`, `configuration_alignment.csv`,
  `numerical_values.csv`, `arbiter_controls.csv`, recovered historical sources,
  generated RTL fixture and RTL logs provide supporting evidence.

Three local worker processes run the bounded panel; they are not separate agents
and do not expand its size. Runtime is not a reported decoder performance metric.
The suite returns nonzero for unresolved differences or confirmed implementation
mismatches, and does not alter expectations or tune seeds/budgets after a failure.
Read the generated status: the presence of this README does not imply PASS.

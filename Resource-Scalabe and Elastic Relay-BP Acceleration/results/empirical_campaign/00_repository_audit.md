# Stage 1 Repository Audit and Empirical Campaign Plan

Status: `STAGE 1 COMPLETE — AUDIT ONLY`

This document records the repository state at commit `ecf279a9f443a0b900a6411191bcb650e3dff3d` on 2026-09-06. No expensive experiment was launched and no existing decoder, graph, RTL, or archived result was modified.

## 1. Executive audit

The repository already contains:

- canonical floating-point and fixed-point Relay-BP implementations;
- Tier-1 graph scaffolding and a Tier-2 circuit-level STIM/DEM graph pipeline;
- deterministic graph packages, syndrome/logical-observable samples, manifests, hashes, and provenance;
- archived P=4 folding, METIS, BA2, BA2-refinement, N=1/N=2, M4 memory, RTL smoke, and LER studies;
- a substantial software-model evidence base, including exact decoder-equivalence checks;
- RTL and testbench assets, but no demonstrated FPGA synthesis/timing result in the current workspace;
- GARI literature/comparison notes, but no verified local public GARI reproduction repository or matched implementation.

The main missing item is a unified `results/empirical_campaign/` orchestration and schema layer. Existing studies use different manifests, sample panels, decoder configurations, and units. They must not be concatenated as if they were one matched benchmark.

## 2. Canonical implementations

### Relay-BP decoders

- Float canonical implementation: `reference/relay_bp_float.py` (`FloatRelayBPDecoder`). It contains the paper-style default Relay configuration (`S=1`, `R=301`, first leg 80 iterations at gamma 0.125, later 60-iteration legs with per-node gamma sampled from [-0.24, 0.66]).
- Fixed-point canonical implementation: `reference/relay_bp_fixed.py` (`FixedRelayBPDecoder`). It exposes fixed precision, guard bits, gamma quantization, saturation counts, iteration callbacks, traces, and deterministic RNG state.
- Older/reference semantics and high-precision path: `reference/relay_reference.py`. This must be treated as a separate implementation until the campaign records an equivalence check against the canonical implementation.
- Fixed-point helpers and configuration: `reference/fixedpoint.py`.
- Existing directed and faithfulness checks: `reference/directed_tests.py`, `reference/faithfulness_check.py`, `reference/test_relay_bp_float.py`, and `reference/test_relay_bp_fixed.py`.

### Graph, circuit, and scoring pipeline

- Gross/Tier-1 graph construction: `graphs/bb_code.py`, `graphs/build_dem.py`, and `graphs/schedule.py`.
- Tier-2 circuit-level package construction: `graphs/build_circuit_level.py`.
- Graph loading and incidence representation: `reference/graph_loader.py`.
- Gross circuit sources and generated packages: `graphs/sources/` and `graphs/generated/`.
- Circuit-level packages preserve detector-fault incidence, fault probabilities, logical-observable incidence, deterministic samples, and provenance hashes.
- Logical correctness must use the package logical-observable masks and the repository's existing scoring convention. Non-convergence is not silently converted into success.

The archived circuit-level baseline identifies the canonical graph as Gross `[[144,12,12]]`, memory-Z, 12 noisy rounds, 1,728 detectors, 67,752 faults, 12 logical observables, and 391,320 detector-fault incidences. These values are repository evidence at the archived p=0.003 package and must be re-read from the selected manifest before any new run.

## 3. Existing experiment assets and what can be reused

### P and folding

- Driver: `results/folding-factor-sweep/run_p_sweep.py`.
- Archived outputs: `p_sweep_structural.csv`, `p_sweep_trajectory.csv`, `phase_retry_summary.csv`, `utilization_summary.csv`, `scaling_summary.json`, and `study_manifest.json`.
- `results/folding-factor-sweep/README.md` defines P as reusable processing lanes/logical banks and includes P=2, 4, and 8. It freezes BA2 parameters for the sweep and changes only the residue count.
- This is a software folding model, not RTL latency, synthesis, or FPGA timing.

### N and first-success trajectory studies

- N=1/N=2 archived study: `results/n1-vs-n2-hardware-latency/run_study.py` with `per_shot_results.csv`, `logical_performance.json`, tail summaries, and plots.
- Parallel trajectory model: `results/parallel-trajectory-model/run_parallel_model.py`.
- The archived model uses independent E0/E1 streams, first-success selection, paired samples, and a P=4 timing assumption. It is a timing model derived from canonical fixed-decoder trajectories, not a complete N=4 campaign.
- Existing hard-shot and stagnation analyses: `results/hard-shot-fixed-trajectory-analysis/`, `results/hard-shot-trajectory-analysis/`, `results/n2-stagnation-priority/`, and `results/full-dataset-stagnation-analysis/`.

### Graph partitioning and METIS

- METIS driver: `results/graph-partitioning-metis/run_metis_partitioning.py`.
- Archived artifacts include partition assignments, edge-cut metrics, balance checks, permutations, invariants, and `README.md`.
- This is explicitly a limited METIS baseline: scalar degree balancing plus deterministic post-balancing, not four independent balance constraints.
- Full decoder equivalence after graph permutation is archived under `results/graph-partitioning-relaybp-equivalence/` and `results/graph-partitioning-relaybp-equivalence-full/`.

### BA2 and folding heuristics

- BA2 driver: `results/bank-aware-folding-layout/run_bank_aware_layout.py`.
- BA2 artifacts include co-occurrence matrices, bank assignments, permutations, phase metrics, retry/utilization summaries, invariants, and a study manifest.
- Refinement driver: `results/bank-aware-folding-layout-refinement/run_fault_refinement.py`.
- The archived final software report selects BA2 over F1/F3 because BA2 has complete equivalence evidence and F3's improvement was negligible in the archived model.
- Existing BA2 generalization and decision studies: `results/ba2-generalization/` and `results/bank-aware-layout-decision/`.
- No COACCESS-GREEDY implementation was found in the audited paths. It is therefore a future implementation task, not an existing result.

### LER and circuit-level samples

- Expanded LER driver: `results/paper-ler-reproduction-expanded/run_expanded_ler.py`.
- Existing LER data: `results/paper-ler-reproduction/` and `results/paper-ler-reproduction-expanded/`.
- The expanded manifest records the intended p values 0.001 through 0.005, target 10,000 shots per p, and the canonical float `S=1`, `R=301` configuration. It also records that the run stopped early because of extreme 301-leg tails; it is not a completed 10,000-shot campaign.
- The current LER campaign must report failures/shots and uncertainty. Zero observed failures must never be reported as zero true LER.

### Operations, timing, and memory models

- Existing statistics/latency helpers: `experiments/stats.py` and `experiments/latency.py`.
- Existing M4 cycle model: `results/relaybp-memory-m4-cycle-model/`.
- Existing M4 address-level validation: `results/relaybp-memory-m4-validation/run_m4_validation.py`.
- Existing memory optimization artifacts: `results/relaybp-memory-optimization/`.
- Existing M0-M4 documentation and reports are in `results/relaybp-memory-m4-validation/`, `results/m4-memory-fabric-rtl/`, `results/m4-memory-fabric-synthesis/`, and related `fpga/` paths.
- M4 documentation states one shared immutable graph/static store plus independent dynamic state, not two complete graph copies. This must remain an explicit campaign invariant.

### RTL and FPGA

- RTL sources are under `fpga/rtl/`, including `relay_bp_folded.sv`, `relay_bp_graph_engine.sv`, and fixed-point helpers.
- M4 memory-fabric RTL/testbench assets are under `fpga/rtl/` and `fpga/testbench/m4_memory_fabric/`.
- Existing testbench entry point: `sh fpga/testbench/m4_memory_fabric/run_tests.sh`; result analysis: `python3 fpga/testbench/m4_memory_fabric/analyze_results.py`.
- Synthesis scripts/reports are under `fpga/synthesis/` and `results/m4-memory-fabric-synthesis/`; current documentation says they were prepared but not executed in the available environment.
- Current evidence supports RTL functional simulation and analytical memory capacity only. FPGA LUT/FF/BRAM/DSP/timing must remain `NOT MEASURED` unless a target device and Vivado-compatible flow actually run.

## 4. Existing measured/derived evidence versus gaps

Already available and reusable, subject to manifest/hash checks:

- P=2/4/8 structural folding-model outputs.
- P=4 original versus METIS versus BA2 retry, utilization, and modeled-cycle comparisons.
- Exact fixed-point equivalence for archived graph permutations and BA2 mappings.
- Archived N=1/N=2 first-success and tail analyses on a limited p=0.003 panel.
- M4 software/address-level validation over the archived trajectory archive.
- RTL memory-fabric directed/stress simulation artifacts if the local testbench is rerun successfully.
- Tier-2 graph provenance, detector/fault/logical dimensions, and circuit/DEM hashes.

Missing or incomplete for the requested campaign:

- One unified baseline manifest and CSV schema for all N/P/heuristic runs.
- Matched N=1, N=2, N=4 runs under one frozen sample cohort and one frozen decoder configuration.
- A complete 3x3 N-by-P factorial with correctness, iteration tails, operation counts, modeled folding metrics, and memory estimates in common units.
- A complete heuristic comparison including original, METIS node-only, METIS+edge reorder, BA2, BA2+F1, BA2+F3, plus a measured additional heuristic.
- A correlation analysis linking graph edge cut to actual bank conflicts/retries/cycles across layouts.
- At least 10,000 completed shots per requested main LER p point, or a documented resource blocker and confidence bounds for the completed subset.
- A verified matched GARI implementation/reproduction run. Existing GARI notes explicitly classify the comparison as partial and non-matched.
- Per-iteration operation instrumentation covering check, variable, min/second-min, sign, gamma, residual, comparisons, candidate weights, reads, and writes.
- A full campaign-level RTL status table and any real synthesis/timing/resource measurement.
- A unified final report with claim labels `[MEASURED]`, `[DERIVED]`, `[ANALYTICAL]`, `[REPRODUCED]`, or `[NOT YET MEASURED]`.

## 5. Dependencies and environment checks

Pinned project requirements are in `requirements.txt`: NumPy 2.2.6, SciPy 1.15.3, STIM 1.15.0, PyMatching 2.3.1, and Matplotlib 3.10.7. The archived expanded-LER manifest was produced with NumPy 2.4.5 and SciPy 1.17.1, so environment versions must be recorded and not silently treated as identical.

Additional dependency/availability checks required before Stage 2:

- selected Python interpreter and installed versions of NumPy, SciPy, STIM, PyMatching, Matplotlib;
- PyMetis availability/version for the METIS driver;
- Icarus Verilog availability for RTL tests;
- Vivado and target FPGA availability, expected to be absent until proven otherwise;
- internet/GitHub access and the exact GARI paper/repository source.

No GARI source or machine-readable reproduction package was identified in the repository audit. The local `results/gari-comparison/` and `results/gari-vs-relaybp-system/` documents are literature/system comparisons, not proof that public GARI software was run here.

## 6. Proposed frozen baseline

Before any benchmark, create `01_frozen_baseline.md` from the selected Tier-2 package manifest and current commit. It must record, without changing defaults:

- Gross `[[144,12,12]]`, memory-Z circuit and source/circuit/DEM hashes;
- noisy rounds, detectors, faults, incidences, and logical observables;
- exact float/fixed decoder class and configuration;
- fixed-point `b`, guard bits, coefficient scale `M`, saturation behavior, `S`, `R`, per-leg limits, gamma law, stopping rule, and non-convergence treatment;
- sample/noise seeds, shot counts, paired-cohort policy, and RNG algorithm/seed mapping;
- layout, P, N, graph permutations, and all operation/cycle-model calibration constants;
- Python/dependency versions, command line, runtime, and git commit.

Until this file exists, later measurements should be considered blocked by an unfrozen baseline rather than silently using an archived configuration.

## 7. Exact staged commands intended for execution

These are the planned commands, not yet executed as part of this audit.

### Stage 0 / cheap sanity and provenance

```sh
python3 -B graphs/bb_code.py
python3 -B graphs/build_dem.py
python3 -B graphs/schedule.py
python3 -B verification/graph_package_check.py
python3 -B reference/directed_tests.py
python3 -B reference/faithfulness_check.py
python3 -c 'import numpy, scipy, stim, pymatching, matplotlib; print(numpy.__version__, scipy.__version__, stim.__version__, pymatching.__version__, matplotlib.__version__)'
python3 -c 'import importlib.util; print("pymetis", bool(importlib.util.find_spec("pymetis")))'
command -v iverilog || true
command -v vivado || true
```

### Stage 1 archive checks and baseline manifest

```sh
python3 results/folding-factor-sweep/run_p_sweep.py
python3 results/graph-partitioning-metis/run_metis_partitioning.py
python3 results/bank-aware-folding-layout/run_bank_aware_layout.py
python3 results/bank-aware-folding-layout-refinement/run_fault_refinement.py
python3 results/graph-partitioning-relaybp-equivalence-full/run_full_equivalence.py
python3 results/relaybp-memory-m4-validation/run_m4_validation.py
sh fpga/testbench/m4_memory_fabric/run_tests.sh
python3 fpga/testbench/m4_memory_fabric/analyze_results.py
```

These should first be run only after confirming their output directories/checkpoint behavior, because some drivers reuse or write archived artifacts. The campaign wrapper should write new outputs under `results/empirical_campaign/` and preserve source archives.

### Stage 2 smallest sanity benchmark

Use a small fixed shot subset from an existing paired Tier-2 sample package, one p value, one graph/layout, and N=1/P=4. Validate: graph dimensions, syndrome/logical scoring, decoder trace callback equivalence, correction mapping, operation counters, and output schema. This is the first new benchmark to run after the user approves the plan.

### Stages 3-6 after sanity approval

- Stage 3: matched N/P factorial and folding heuristic model, beginning with a small cohort and then the declared cohort.
- Stage 4: larger p sweep at 0.001, 0.002, 0.003, 0.004, 0.005 with failures/shots/confidence bounds and explicit runtime stops.
- Stage 5: GARI source audit/reproduction attempt, then matched comparison only if the source, graph, noise, scoring, and settings can be aligned.
- Stage 6: generate CSVs, plots, claim-labeled summaries, and `FINAL_EMPIRICAL_REPORT.md` only from completed manifests.

## 8. GARI audit status

Current repository evidence supports these statements only:

- `[REPRODUCED]` The local comparison notes describe GARI's architecture and report values attributed to the paper.
- `[DERIVED]` Some local notes derive timing/resource interpretations from reported GARI values.
- `[NOT YET MEASURED]` A local execution of GARI software, a matched GARI-vs-Relay-BP shot cohort, and an independently verified public reproduction repository.
- `[NOT YET MEASURED]` GARI plus BA2/folding/co-access layouts.

The next GARI task is source verification from the actual paper/supplement/repository, with every number classified as paper-reported, publicly reproducible, not reproducible, or derived by this project. No GARI number should enter the matched CSV until this classification is complete.

## 9. Claim discipline for the campaign

- Decoder correctness and layout equivalence are separate from modeled folding efficiency.
- QEC circuit rounds, Relay-BP iterations, relay legs, folded service cycles, and FPGA clock cycles are distinct units.
- A lower METIS edge cut is not evidence of lower bank conflict rate until paired layout metrics demonstrate it.
- P=4 and N=2 are hypotheses to test, not conclusions to encode in the runner.
- Analytical BRAM-equivalent capacity is not measured FPGA BRAM.
- Archived 128-shot or selected hard-shot panels cannot be promoted to a strong LER claim.
- Missing experiments must be recorded as `NOT MEASURED — blocked by ...`, never filled with theoretical estimates.

## 10. Stage 1 conclusion

Repository audit is complete. The reusable foundation is strong enough for a small sanity benchmark, but a unified campaign runner, manifest schema, operation instrumentation, and frozen baseline file are still required. The next action should be the cheap environment/baseline sanity check only; no large N/P/folding/LER/GARI campaign should begin until its output and parameters are reviewed.

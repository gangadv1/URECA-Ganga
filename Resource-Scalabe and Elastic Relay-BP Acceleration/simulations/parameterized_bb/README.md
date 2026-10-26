# Parameter-driven BB circuit-level smoke pipeline

The four published BB codes are regression fixtures. The new entry point constructs a code from torus dimensions and ordered polynomial monomials; it does not select or substitute a fixture.

From the project directory:

```sh
MPLCONFIGDIR=/private/tmp/relay-param-matplotlib OPENBLAS_NUM_THREADS=1 \
  ../.venv/bin/python -B simulations/parameterized_bb/run.py \
  --config simulations/parameterized_bb/example.json \
  --output results/my_new_bb_smoke
```

The destination must not exist. `--output` overrides the configuration's `output`; external directories are supported. Existing outputs are refused. `runtime_cap_seconds` (default120, maximum600) bounds the complete child process; timed-out partial outputs are retained and marked STOPPED. No automatic retries, large sweeps or synthesis are performed. The Python `run(config,output)` helper is for controlled callers and has no process timeout; use the CLI for a hard runtime cap.

## Inputs and exact convention

`l,m` are positive integers. `A,B` are ordered lists of `[dx,dy]` integer exponent pairs: `[0,0]` is1, `[1,0]` isx, `[0,1]` isy, and `[1,2]` isxy². Signed exponents are reduced modulo l/m. Cell index is `x*m+y`; a row at(x,y) connects the column(x+dx,y+dy). Matrices use `Hx=[A B]`, `Hz=[Bᵀ Aᵀ]`, with addition over GF(2), exactly the existing `graphs/bb_code.py` convention. Order does not change the polynomial but affects the reused gate schedule.

`n=2*l*m`, `k=n−rank_GF2(Hx)−rank_GF2(Hz)`. Both ranks, CSS commutation and a logical quotient basis are checked. **Distance is not calculated:** packages store `d:null` and an explicit unknown-distance label. Published fixture distances are not transferred to a new code.

Required circuit inputs are `physical_p` and `rounds`. Decoder controls are `N,P,shots,first_limit,later_limit,R,S,sample_seed,trajectory_base_seed,engine_seeds`. Defaults are N2/P4,2 shots,2/2 iterations,R2/S1. R is the maximum number of legs, so at mostR−1 retries; S is the requested number of successful legs. The per-engine iteration cap is `first_limit+(R−1)*later_limit`. The existing fixed-point decoder remains b18/g4/M16. Derived seeds follow the existing testbench's SplitMix/xorshift schedule and do not depend on P. Optional `engine_seeds` must contain exactly N distinct uint64 seeds; retry seeds cannot be zero. An explicit seed list is reused across shots; omit it for shot-derived engine seeds.

`P=2,4,8` is supported by the software structural folding model. N is a positive count with dedicated P-lane trajectories, not a shared pool. `banking` selects `original`, `ba2` or `weighted_ba2`. Original and graph-specific BA2 are generated for every supported P; the inherited weighted optimizer is supported **only at P4**, with BA2 edges frozen. Other lane counts or weighted/P combinations are rejected. `max_data_qubits` defaults512 as an explicit dense-algebra resource guard; it can be increased by a caller, subject to the runtime cap. This is a smoke-budget guard, not a four-code whitelist.

## Generic algebra versus circuit restrictions

`graphs/parameterized_bb.construct()` accepts nonempty polynomial lists of arbitrary length. Repeated terms cancel over GF(2). The reused circuit generator has stricter requirements:

- Exactly three distinct monomials per polynomial after modulo reduction; cancellation/aliasing is rejected for this schedule.
- Positive k and memory-Z experiments only.
- `noise_model="gari_uniform_p_memory_z"`: the existing MIT-licensed GARI/Gong `build_circuit.py` schedule, with its four noise arguments all set to the supplied p; reset/measurement flips and depolarization locations follow that implementation. Final data measurements are perfect.
- STIM must produce a deterministic full hypergraph DEM with no gauge-detector allowance or graphlike substitution. Invalid extraction schedules are rejected. Noiseless detector and observable labels must be zero.

This profile is **not** the canonical pinned Relay `uniform_circuit` profile. It uses a different extraction/noise schedule and its own validated logical basis. Generic regeneration of the canonical Relay profile is unsupported and explicitly rejected; the existing pinned-source importer and all four historical packages remain available unchanged. Do not compare logical-label bit numbers across independently chosen bases or combine these smoke latencies with canonical12-round results.

## Reused implementations and outputs

The pipeline reuses `bb_code.build_block`, the existing GARI CSS/rank/logical routines and circuit schedule, `build_circuit_level.write_package` for DEM extraction/sampling/artifacts, and the configurable testbench's sparse loader, trajectory seeds, fixed decoder, scoring and ensemble selector. BA2 uses the archived capacity-constrained assignment/remapping functions; weighted BA2 reuses the validated bounded sweep.

Weighted assignment uses **maximum configured iteration/leg budgets as declared access-frequency weights**, not estimated frequencies fitted to these shots or logical labels. BA2 is an explicit candidate and edges stay fixed. The declared budget objective is checked using generated structural profiles; completion cycles for the actual smoke trajectories are reported separately. A budget-objective gain need not improve every sample's first-success completion.

Artifacts include code matrices and logical-Z basis, generated STIM circuit, full DEM, probabilities, detector/fault/observable incidence, reproducible circuit/DEM samples, package/manifest hashes, reversible storage maps, per-phase conflicts/retries/issued groups/occupancy, per-engine and ensemble CSVs, inverse-mapped iteration-state hashes, validation and provenance. DEM sampled fault labels are used only to validate mappings; the decoder receives only priors and syndrome. Observed logical labels are scoring-only.

Every remapping checks inverse H/A/probability recovery and exact gamma, prior, belief, decision, residual and edge-message states during decoding. Fault identities and check/syndrome order are preserved. Physical edge maps are separate from decoder CSR edge identity maps. First syndrome-valid completion wins with lower-index ties; all-fail waits for the final engine. A timing-dependent change of winner is allowed, while per-engine equivalence is mandatory. Nonconvergence and syndrome-valid logical errors remain distinct in the CSVs.

Cycles are **structural extrapolations**, excluding controller/RNG/cancellation/drain overhead; they are not measured RTL or FPGA timing. Issued-group occupancy is not elapsed PE utilization. Exact cancellation-aware work and measured hardware timing are unavailable. Changing l/m, polynomials, p or rounds requires circuit/DEM/graph/prior regeneration. P or banking changes require regenerated layouts/profiles. N/budgets/seeds change software execution; currently the one-shot entry point writes a complete fresh output for each configuration. No dynamic FPGA RTL reconfiguration, synthesis resource scaling or timing closure has been validated.

## Validation

```sh
MPLCONFIGDIR=/private/tmp/relay-param-matplotlib OPENBLAS_NUM_THREADS=1 \
  ../.venv/bin/python -B simulations/parameterized_bb/test_pipeline.py \
  --output results/a_fresh_parameterized_validation
```

Four regression fixtures and two new parameter sets run through the complete pipeline at N1/P2 and N2/P4 (two shots each). Further checks change p/rounds/seeds, reconstruct DEM syndromes/observables, test invalid parameters, and verify original Gross payloads. See `results/parameterized_bb_validation_final/REPORT.md` for actual results and the preserved initial test-comparison failure. Existing decoder/testbench regressions also passed, including canonical Gross N1/P4 and original folding profiles. P8/BA2 and external portable output paths were separately checked.

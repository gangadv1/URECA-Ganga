from pathlib import Path
import json,csv,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
records=json.loads((HERE/'full_pipeline_results.json').read_text())
t='''# Parameter-driven BB implementation: validation report

**PASS:** complete generic pipeline for four existing regression fixtures and two newly constructed parameter sets, each at N1/P2 and N2/P4. New codes are not fixture substitutions. Distance is unknown. Four test methods (including12 complete pipeline configurations and an additional changed-noise/rounds configuration) passed in24.75s. Seven existing configurable-testbench tests passed in10.68s, including canonical Gross N1/P4. A separate one-shot N1/P8 test passed with a portable external output.

## New code results

Both new sets use A=x+1+y and B=x+1+xy², p=.003,2 noisy rounds,2 shots, first/later2/2,R2/S1, sample seed20261011 and existing trajectory base seed7640891576956012809. Their parameters are `(l,m)=(3,6)` and `(6,3)`; both derive n36/k4, with no claimed distance. The graph sizes differ despite equal n/k.

All values below are actual model-generated results at N2/P4. “Phase pass” means one execution of each structural phase, **not ensemble completion latency**. The final column is average first-success/last-on-all-fail completion on two matched shots. No LER or statistical improvement claim follows.

| New parameters | Layout | H dimensions / edges | One-pass structural cycles | One-pass retries | Issued-group occupancy | Mean modeled completion cycles | Failures /2 |
|---|---|---|---:|---:|---:|---:|---:|
'''
for name,label in [('new_36_A','l3,m6'),('new_36_B','l6,m3')]:
 p=HERE/(name+'_N2_P4');summary=json.loads((p/'summary.json').read_text());profiles=json.loads((p/'banking_profiles.json').read_text());dims=summary['dimensions']
 for layout,profile in profiles.items():
  q=profile['all_phases_once'];s=summary['results'][layout]
  t+=f"| {label} | {layout} | {dims['detectors']}×{dims['faults']} / {dims['edges']} | {q['estimated_cycles']:,} | {q['retry_subsets']:,} | {q['mean_lane_utilization']:.2%} | {s['mean_completion_cycles']:,.1f} | {s['total_failure']} |\n"
t+='''
The short budget retained a nonconvergence for the first new code; its 1/2 failure count was unchanged across layouts. The second new code succeeded2/2. Per-phase retries/conflicts and iteration counts are in each case's banking_profiles.json and per_engine.csv. BA2 and weighted variants preserved every tested inverse-mapped decoder iteration state; changing P left trajectory0 seeds, decisions, iteration counts and outcomes unchanged. The inherited weighted optimizer kept BA2 edge maps fixed and included BA2 as a candidate. It used maximum iteration/leg budgets as weights, without reading sample/logical labels. These are structural software models, not measured RTL/FPGA timings.

## Audit and implemented scope

| Component | Existing implementation / extension |
|---|---|
| Algebra | `graphs/bb_code.py` was Gross-only. Its block generator now accepts l/m with original defaults unchanged; `graphs/parameterized_bb.py` builds generic polynomials, derives GF2 ranks/n/k and validates logical quotient bases. |
| Circuit | `graphs/build_circuit_level.py` imports pinned official sources. New generation reuses `results/gari-same-stim-adapter/official_gari/build_circuit.py` and `codes_q.py`; package export extends the existing builder without replacing legacy behavior. |
| DEM/graph | Full nondecomposed STIM DEM, existing fault extraction/CSR/edge lists/priors and sample reconstruction. Dynamic detector/fault/observable counts and portable manifests. |
| Decoder/config | `simulations/configurable_testbench/testbench.py` accepts explicit parameterized packages and validates algebra/metadata/hashes. It still accepts all four legacy fixtures. Existing fixed-point decoder, scoring and N selector are reused. |
| BA2 | Archived capacity-preserving bank assignment and reversible fault/edge mapping functions are reused with graph-derived sizes and selected P. |
| Weighted BA2 | Existing bounded multiplier sweep at P4; fixed BA2 edges; budget-derived iteration/relay weights and an explicit BA2 candidate. No logical-label tuning. |
| N/P | Dedicated P-lane trajectory model; arbitrary positive N under runtime/resource guards; software P2/4/8. No shared-pool contention or verified dynamic FPGA RTL. |

Generic algebra accepts arbitrary nonempty monomial lists; the reused circuit profile requires three distinct modulo-torus monomials per polynomial, k>0 and memoryZ. All constructed schedules must pass STIM deterministic detector/observable checks and noiseless memory-label checks. Signed exponents are reduced modulo dimensions. Unsupported polynomial/circuit/noise/P combinations fail clearly.

The new noise profile is explicitly named `gari_uniform_p_memory_z`, with all four existing noise arguments set to p. It is **not the canonical Relay pinned uniform_circuit schedule**. Generic generation of that exact Relay schedule, other memory bases, distance determination, custom noise models, P other than2/4/8, and weighted BA2 outsideP4 remain unsupported. The four fixture construction tests validate n/k and pipeline correctness under this generic profile, not equality to their pinned canonical circuits. Legacy-source loading and Gross historical payload preservation are checked separately.

## Regression evidence and initial negative test

Initial suite:12 generic pipeline cases and changed-p/rounds tests passed, but the Gross metadata equality assertion failed because the historical package lacks the `code_parameters` field added by the previously committed generalized builder. This was a test assumption, not a payload mismatch. The initial failure remains in `results/parameterized_bb_validation/validation.json`; the corrected review is in regression_review.json. No failed output was deleted or overwritten.

The final test compares every historical package field and validates the additive n144/k12/d12 metadata. Original Gross hx/hz arrays, fault probabilities/incidence, edge lists, circuit/DEM samples and coordinate arrays match exactly; circuit.stim, DEM text and incidence.csv hashes match. Circuit/sampling/schema manifest fields and all graph fields except the pre-existing display-name change match. Known pre-existing differences are the additive code_parameters, graph display `BB [[144,12,12]]` versus historical `gross [[144,12,12]]`, and provenance/output paths/current commit/artifact-package hashes. This implementation introduces **no additional legacy payload/field difference**. The Gross package identifier/default destination remain unchanged.

Existing seven-test regression includes canonical Gross N1/P4 (one17-iteration archived case), all four original packages, deterministic label separation, ties/all-fail selection, P folding and original Gross folding regression. Its report is `results/parameterized_bb_validation/existing_testbench_regression.json`; outputs are in the new `simulations/configurable_testbench/runs/parameterized-regression-8cpa5ev4/` directory.

## Paths, commands and reproducibility

Implementation files:
- Modified `graphs/bb_code.py`, `graphs/build_circuit_level.py`, `simulations/configurable_testbench/testbench.py`.
- New `graphs/parameterized_bb.py`, `simulations/parameterized_bb/{run.py,test_pipeline.py,example.json,README.md}`.
- Existing reference decoder, folding/banking research scripts, circuit generator and all source/packages/archives were preserved.

Each new case has configuration.json, code_matrices.npz, generated_source.stim, package/, reversible storage-map NPZs, banking_profiles.json, bank_optimization.json, per_engine.csv, per_shot.csv, decoder_equivalence.json, summary.json, validation.json and provenance.json with source/artifact hashes. Primary outputs: `results/parameterized_bb_validation_final/`; initial test and example outputs remain separately in `results/parameterized_bb_validation/` and `results/parameterized_bb_smoke/example/`.

Commands executed from the project directory:
```sh
MPLCONFIGDIR=/private/tmp/relay-param-matplotlib OPENBLAS_NUM_THREADS=1 ../.venv/bin/python -B simulations/parameterized_bb/run.py --config simulations/parameterized_bb/example.json
MPLCONFIGDIR=/private/tmp/relay-param-matplotlib OPENBLAS_NUM_THREADS=1 ../.venv/bin/python -B simulations/parameterized_bb/test_pipeline.py
MPLCONFIGDIR=/private/tmp/relay-param-matplotlib OPENBLAS_NUM_THREADS=1 ../.venv/bin/python -B simulations/parameterized_bb/test_pipeline.py --output results/parameterized_bb_validation_final
MPLCONFIGDIR=/private/tmp/relay-param-matplotlib OPENBLAS_NUM_THREADS=1 ../.venv/bin/python -B simulations/parameterized_bb/run.py --config results/parameterized_bb_validation_final/portable_P8_config.json
```

The original testbench suite was run through unittest with only its output setup redirected to the fresh directory above; test/decoder code was not changed. Exact portable output path is in portable_P8_validation.json. A single extra case tests p=.007,3 rounds and explicit trajectory seeds123/456; its54→72 detector-count change and DEM syndrome/logical reconstruction passed. Each generated configuration uses a60s cap; no large decoding campaign or synthesis ran. The example ran in approximately0.5s and each full-pipeline regression used two shots.

## Next action

Use the parameter-driven entry point with a fresh destination for a chosen new three-term BB construction. First inspect rank-derived k and schedule validity, then increase bounded smoke budgets if correctness investigation needs more convergence. To reproduce **canonical Relay noise** for arbitrary polynomials, the next distinct task is to integrate that upstream schedule with an explicit equivalence test; do not relabel the current GARI profile. No FPGA dynamic reconfiguration or hardware resource/timing claim is made.
'''
(HERE/'REPORT.md').write_text(t)
# Recheck every pre-existing protected result/source/graph/reference file.
protected=json.loads((HERE/'protected_hashes.json').read_text())
assert all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in protected.items())
validation=json.loads((HERE/'validation.json').read_text())
review=json.loads((ROOT/'results/parameterized_bb_validation/existing_testbench_regression.json').read_text());assert review['status']=='PASS'
portable=json.loads((HERE/'portable_P8_validation.json').read_text());assert portable['status']=='PASS'
(HERE/'final_checks.json').write_text(json.dumps(dict(status='PASS',protected_files_unchanged=len(protected),full_pipeline_configurations=12,existing_testbench_tests=review['tests'],portable_P8='PASS',statistical_claims=False,code_distance_claimed=False),indent=2)+'\n')
print('PASS: report generated; '+str(len(protected))+' pre-existing protected files unchanged.')

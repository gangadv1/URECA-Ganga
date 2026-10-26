# First paired external decoder benchmark

**Real paired benchmark completed on 58 of the 128 canonical samples.** Standard BP stopped at its 90-second cap; BP-OSD was then restricted to the exact completed BP sample IDs. This is a runtime-limited prefix, not a full 128-shot external result or an unbiased Monte Carlo LER estimate.

## Matched problem and invariants

Gross [[144,12,12]], memory Z, physical p=.003, 12 noisy rounds and final perfect measurement. The exact canonical circuit-level package has 1,728 detectors, 67,752 DEM fault columns, 391,320 detector edges and 12 logical observables. No code-capacity matrix, graphlike decomposition, merged fault IDs, uniform substitute priors or fault permutation was used.

Inputs: `graphs/generated/gross_circuit_level/memory_Z_r12_p0p003/{circuit.stim,detector_error_model.dem,faults.npz,edge_lists.npz,manifest.json,package.json}`, `results/circuit-level-multiseed/paired_samples.npz`, and `results/n-scaling-canonical/{per_shot_results.csv,manifest.json,aggregate_summary.json}`. All 128 canonical rows were joined by actual sample_seed/shot, not assumed NPZ flattening. Each packed syndrome/logical hash matches the canonical row. The archive contains 640 samples, but only the exact canonical 128 were eligible. They use seeds 20260809–20260812 with 32 rows each. The completed paired subset is indices 0–57: all 32 from seed 20260809 plus the first 26 from 20260810. Exact IDs are in paired_indices.json.

The original preflight diagnosed a text DEM probability round-trip difference ≤4.34e−19 in 36,288 entries. Detector/observable targets were exact. The unchanged source circuit produces an in-memory DEM whose probabilities exactly equal faults.npz. Both external decoders receive those original binary priors, and their internal channel vectors were checked bit-exact. No probabilities were altered to accommodate the text representation.

External inputs are H and the DEM prior vector at initialization, followed only by the detector syndrome for decode. Observed logical labels and A are held in the parent scoring process, inaccessible through the decoder interface. Score predicted fault vector e using H e mod2 = observed detectors and A e mod2 = observed logical observables. Total failure = syndrome-invalid/nonconvergence + syndrome-valid logical error. Source DEM columns, H and A connectivity/ordering all match. Persisted external predictions were independently rescored. BP and BP-OSD BP-stage iteration counts and convergence flags match on every pair, and BP-converged final predictions are identical.

Relay-BP was **not rerun**. Its canonical CSV stores scored outcomes/winners, iterations and cycle estimates, not raw fault predictions. We reuse those verified archived outcomes after sample-hash matching; independent fault-vector re-scoring for Relay is unavailable. Relay_archived_records.json preserves selected subset engine iterations/legs/seeds and winners. This distinction is explicit rather than fabricating missing predictions.

## Compatibility matrix

Detailed matrix: compatibility_matrix.csv/json.

| Decoder | Same DEM/prior/noise possible now? | Budget and observable support | Availability / blocker |
|---|---|---|---|
| Standard BP | Yes, exact H, binary priors, archived circuit syndromes | 1,940 parallel min-sum iterations; A maps predictions to observables | Installed ldpc 2.4.1 BpDecoder; executed |
| Standard BP-OSD0 | Yes, same H/prior/syndromes | Same BP cap plus OSD_0/order0 elimination; observable map unchanged | Installed ldpc 2.4.1 BpOsdDecoder; executed; not higher-order OSD |
| Astra | Exact circuit DEM not validated; published code-capacity problem differs | Pauli-class outputs/features and trained model need DEM-fault mapping; budget not matched | Author code available; no compatible circuit checkpoint identified; Torch absent; not executed |
| Local preprocessing BP-OSD | Paper explicitly targets circuit noise, but exact event/prior-hint adapter unavailable | Need check/data/time/gate neighborhood mapping and merged DEM-event correspondence; paper budget differs | No runnable author implementation identified in paper/targeted search; not executed |
| Sequential BP | Binary-H adaptation conceivable, but published independent-X setup not matched | Need exact SCNS/SVNS/SBPGD schedule and decimation semantics; sweep costs differ | No runnable author implementation identified; stock library serial BP is not relabeled as this method |
| Relay N1/N2/N4/N8 | Exact canonical H, priors and samples | Per engine R32, first/later80/60, S1; archived A-scoring | Local reference decoder/runner; archived scores only, measured software runtime unavailable |

Astra author [repository](https://github.com/arshpreetmaan/astra) and [paper](https://arxiv.org/html/2408.07038v1) were inspected. bb_test.py uses Pauli classes/PanQEC graphs, a trained_models checkpoint path, Torch and a custom LDPC fork. A validated binary circuit-fault feature/prior adapter and compatible trained weights are missing; no retraining or dependency replacement was attempted.

The [preprocessing paper](https://arxiv.org/html/2509.01892v1) uses local time/check/data-qubit patterns to modify fault probabilities. Canonical merged DEM columns can represent multiple gate events, so event-to-column hints and boundary/round/check labels require validation. Ordinary BP-OSD is not this method. The [sequential paper](https://arxiv.org/abs/2602.13420) defines sequential schedules/decimation for independent-X benchmarks; an author implementation and circuit adapter were not found in the inspected sources. This is a search limitation, not a claim that no code exists anywhere. Published accuracy/timing numbers were not copied into the benchmark.

The standard [BP-OSD repository](https://github.com/quantumgizmos/bp_osd) points to the [LDPC implementation/documentation](https://software.roffe.eu/ldpc/quantum_decoder.html). The installed Cython/C++-backed API was used, not a new approximation of OSD. Exact inspected URLs/searches are in research_references.json.

## Paired results (58 identical samples)

| Decoder | Logical successes | Total failures | Nonconvergence | Valid-syndrome logical error | Failure Wilson 95% | Mean BP / selected Relay iterations | Measured mean decode seconds | Modeled mean cycles |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| BP | 45/58 | 13 | 13 | 0 | [13.59%, 34.66%] | 755.31 | 1.538 | unavailable |
| BP_OSD0 | 57/58 | 1 | 0 | 1 | [0.31%, 9.14%] | 755.31 | 1.471 | unavailable |
| Relay_N1 | 57/58 | 1 | 1 | 0 | [0.31%, 9.14%] | 181.26 | unavailable | 690,067,925.40 |
| Relay_N2 | 58/58 | 0 | 0 | 0 | [0.00%, 6.21%] | 112.36 | unavailable | 427,838,492.86 |
| Relay_N4 | 58/58 | 0 | 0 | 0 | [0.00%, 6.21%] | 98.62 | unavailable | 375,536,284.36 |
| Relay_N8 | 58/58 | 0 | 0 | 0 | [0.00%, 6.21%] | 76.48 | unavailable | 291,274,286.72 |

BP-OSD invokes OSD0 on 13 BP failures; all become syndrome-valid, and 12 become logically correct. Its remaining logical failure is index36; Relay N1 fails by nonconvergence on index18. Thus BP-OSD0 and Relay N1 have equal total failure counts on different samples, not identical predictions. N2/N4/N8 have no failures on this subset; zero/58 leaves a Wilson upper failure bound of 6.21%. No significance, universal superiority or general LER claim follows.

Configurations: minimum_sum, scaling1.0, parallel schedule, one OpenMP thread, input_vector_type=syndrome, exact per-fault probabilities. External random serial schedules are disabled; random_schedule_seed=1 is irrelevant to deterministic parallel updates. BP-OSD requires a Python probability list and rejects random_serial_schedule as a keyword; conversion is lossless and the inherited false default applies. API initialization failures were preserved in attempts.json and STOPPED.json, then corrected before OSD decoding. A tiny sparse syndrome API test and two real canonical smoke samples (indices0,18) passed; smoke outcomes are included once in the final sample set.

External cap 1,940 = 80 + 31×60 matches the maximum count of one Relay trajectory, not equal total computation. Relay has first gamma .125, later seeded gamma, fixed-point 18-bit messages/M16 and N independent trajectories; external plain BP is floating point and has no relay resets/gamma. OSD adds Gaussian elimination, while Relay N2/N4/N8 multiply aggregate trajectory budgets. The reported Relay iteration mean is winner iterations (max engine iterations on all-fail), not total ensemble executed work. Resource, budget and precision matching are therefore partial. This is a fair data/model/scoring comparison, not an equal-compute performance contest.

## Timing and limits

BP measured decode total 89.213s (mean1.538s, empirical p994.272s). BP-OSD0 measured decode total85.296s (mean1.471s, empirical p994.013s), including OSD. Timers bracket decoder.decode only: initialization, sparse loading, scoring, IPC and plotting are excluded and documented separately in timing.json/per-shot records. CPU platform/version is recorded in provenance.json. BLAS/OpenMP environment requested one thread.

These are single unrandomized, non-interleaved software runs. BP-OSD happened to measure slightly faster despite added work; CPU load, caching and run-order variability prevent interpreting that as a speed advantage. No isolated OSD stage timer was available. No runtime conversion to FPGA cycles, Fmax, measured RTL/FPGA latency or cross-domain speedup is made. Relay timing columns are archived modeled architectural cycles only. Plot2 deliberately separates timing domains.

Limits: decoder initialization10s, each decode ≤10s, each method≤90s, planned decoding cap180s. BP completed indices0–57, then the next request was cut off by remaining method time; that timed-out/uncompleted sample is not counted as a decoding failure. OSD ran only the same58, taking about85s decode time, without rerunning BP. Initial OSD errors occurred before decoding. The other70 samples remain unbenchmarked; there was no attempt to bypass caps. This prefix has only two of the four canonical seeds, and runtime censoring/order can bias accuracy and tail timing. Exact missing coverage is reported rather than treating58 as128.

## Defensible Relay candidate

Recommend **N2 at P4** if the priority is the smallest ensemble with no failures observed in the full canonical archive and moderate lane provisioning (eight lanes). Full archived128: N1 succeeds125/128, N2/N4/N8 succeed128/128. N2 reduces modeled mean by35.15% and p99 by70.09% versusN1 in that full archive. N4 trades16 lanes for another20.30% mean reduction versusN2; N8 uses32 lanes for61.84% lower p99 versusN4. Choose N8 only under a tail-latency priority that warrants added resources. No synthesized area/Fmax evidence or external FPGA speed comparison supports declaring an overall optimal decoder. The58-pair benchmark does not establish N2 statistically better than BP-OSD0.

## Reproduction and outputs

Dependencies: {'ldpc': '2.4.1', 'numpy': '2.2.6', 'scipy': '1.15.3', 'stim': '1.15.0'}. Python/platform and local LDPC source hashes are in provenance.json; bposd distribution and Torch are not installed. No dependencies were installed, removed or upgraded. The installed ldpc supplies BpOsdDecoder directly.

Exact command from project directory:
```sh
MPLCONFIGDIR=/private/tmp/relay-external-matplotlib OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ../.venv/bin/python -B results/external_decoder_benchmark/run_benchmark.py
```

Runner reuses BP_results.json when present; no decoding of cached BP is repeated. Keep a fresh output directory for a new run; it refuses to overwrite completed validation.json. configurations/limits are in configuration.json and commands.json. Graph1 shows failure composition and Wilson intervals for58 common pairs. Graph2 shows measured external software mean/p99 and modeled Relay mean/p99 in separate panels.

Files: run_benchmark.py, plot_results.py, validate_outputs.py, compatibility_matrix.csv/json, research_references.json, preflight.json, DEM_roundtrip_diagnostic.json, attempts.json, smoke.json, BP/BP_OSD0_progress.jsonl, BP/BP_OSD0_results.json, BP/BP_OSD0_predictions.npz, paired_indices.json, per_shot_external.json, Relay_archived_records.json, comparison.csv/json, configuration.json, timing.json, two high-resolution PNG/PDF graphs, validation.json, protected_hashes.json, provenance.json and this report. No existing experiments were modified; nothing was deleted, staged, committed or pushed.

Next benchmark task: complete the remaining70 canonical samples in separately bounded batches with this frozen configuration, then aggregate all128 pairs and interleave repeated CPU timing measurements. Author-specific circuit adapters/checkpoints are separate work; do not claim those methods are benchmarked here.

Plotting and read-only validation commands (no decoding):
```sh
MPLCONFIGDIR=/private/tmp/relay-external-matplotlib ../.venv/bin/python -B results/external_decoder_benchmark/plot_results.py
MPLCONFIGDIR=/private/tmp/relay-external-matplotlib ../.venv/bin/python -B results/external_decoder_benchmark/validate_outputs.py
```

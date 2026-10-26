# Paired decoder failure investigation

58 canonical samples audited; **BP: 13 failures, BP-OSD0: 1, Relay N1: 1; Relay N2/N4/N8: 0**. All BP failures and the Relay N1 failure are nonconvergence. The sole BP-OSD0 failure is syndrome-valid but logically incorrect. This runtime-limited prefix is not an unbiased LER estimate.

## Exact failure IDs

Canonical indices and shot IDs are zero-based. BP failures:
- seed **20260809**, shots **9, 10, 12, 15, 24, 27, 29**;
- seed **20260810**, shots **3, 4, 7, 9, 21, 24**.

BP-OSD0: seed **20260810**, shot **4**, canonical index **36**.
Relay N1: seed **20260809**, shot **18**, canonical index **18**.
Only index36 fails multiple decoders (BP and BP-OSD0). Relay N1's failure is distinct; BP and BP-OSD0 succeed on index18. OSD0 fixes 12 of the 13 BP failures.

| Index | Seed:shot | Syndrome weight | BP outcome / iterations | BP-OSD0 outcome / BP iterations | Relay N1 outcome / iterations (legs) | Shared final failure |
|---:|---|---:|---|---|---|---|
| 9 | 20260809:9 | 195 | nonconv. / 1940 | success / 1940 | success / 117 (2) | none |
| 10 | 20260809:10 | 174 | nonconv. / 1940 | success / 1940 | success / 53 (1) | none |
| 12 | 20260809:12 | 204 | nonconv. / 1940 | success / 1940 | success / 60 (1) | none |
| 15 | 20260809:15 | 177 | nonconv. / 1940 | success / 1940 | success / 165 (3) | none |
| 18 | 20260809:18 | 232 | success / 256 | success / 256 | nonconv. / 1940 (32) | none |
| 24 | 20260809:24 | 144 | nonconv. / 1940 | success / 1940 | success / 127 (2) | none |
| 27 | 20260809:27 | 137 | nonconv. / 1940 | success / 1940 | success / 230 (4) | none |
| 29 | 20260809:29 | 168 | nonconv. / 1940 | success / 1940 | success / 551 (9) | none |
| 35 | 20260810:3 | 184 | nonconv. / 1940 | success / 1940 | success / 110 (2) | none |
| 36 | 20260810:4 | 178 | nonconv. / 1940 | logical error / 1940 | success / 967 (16) | BP;BP_OSD0 |
| 39 | 20260810:7 | 179 | nonconv. / 1940 | success / 1940 | success / 190 (3) | none |
| 41 | 20260810:9 | 213 | nonconv. / 1940 | success / 1940 | success / 1430 (24) | none |
| 53 | 20260810:21 | 163 | nonconv. / 1940 | success / 1940 | success / 104 (2) | none |
| 56 | 20260810:24 | 181 | nonconv. / 1940 | success / 1940 | success / 66 (1) | none |

`sample_comparison.csv` and `.json` contain **all 58 rows**, all four Relay N values, per-engine iterations/legs, winner, failure overlap, exact syndrome one-indices, dimension1728, weight and canonical packed-bit SHA256. All other detector positions are zero. These describe observed detector syndromes, not true fault labels. Relay raw fault predictions are unavailable; its scored outcomes are reused from the canonical archive.

## Configuration and stopping differences

| Aspect | Standard BP / BP-OSD0 | Canonical Relay-BP |
|---|---|---|
| Problem | Exact same circuit-level H, fault ordering and probabilities; Gross Z, p=.003, 12 noisy rounds | Same source package; probability-derived LLRs subsequently quantized |
| BP | LDPC2.4.1 minimum-sum, scale1, parallel, one OpenMP thread, floating point | Fixed-point b18/g4/M16, separate scaling; gamma-biased updates |
| Budget | One uninterrupted BP run, at most1940 iterations; early syndrome-valid stop | First leg80, then31 legs of60:1940 maximum **per engine**; R32/S1 |
| Retry/handoff | No relay legs; BP-OSD0 calls OSD only after failed BP | Each leg resets edge messages to physical priors, carries previous leg final marginals; first gamma.125, later seeded xorshift64 per-fault gamma /16 |
| Fallback | OSD_0, order0, reliability-guided GF2 solve using final BP log-probability ratios; no higher-order search | Up to32 relay legs per engine; N independent seeded trajectories |
| Stop | Return BP prediction if converged, otherwise one OSD0 result; no logical-label check or retry | S1 stops at first syndrome-valid solution; ensemble selects earliest modeled success, lowest engine index on ties; all-fail waits for last engine |
| Aggregate work |1940 BP iterations plus variable OSD elimination cost | Up to N×1940 independent iterations; winning iteration count is not ensemble work or cancellation-aware executed work |

Exact external kwargs: `error_channel=probabilities.tolist(), max_iter=1940, bp_method="minimum_sum", ms_scaling_factor=1., schedule="parallel", omp_thread_count=1, random_schedule_seed=1, input_vector_type="syndrome"`. Standard BP explicitly sets `random_serial_schedule=False`; BpOsdDecoder rejects that keyword and inherits the false default. BP-OSD0 additionally sets `osd_method="OSD_0", osd_order=0`. Parallel scheduling makes the random schedule seed immaterial. Binary package priors are preserved exactly, avoiding rounded DEM-text probabilities.

`decoder.converge` describes **BP-stage** convergence, not OSD's final validity. Saved scoring correctly recomputes H·e mod2. OSD's zero-syndrome shortcut returns zero; all audited syndromes are nonzero. Neither decoder receives observed logical labels. Logical scoring is A·e mod2 against the archived observables, performed outside decoding.

## Single OSD0 failure: reproduced without changes

Index36 (seed20260810, shot4) reaches the1940 BP cap, then OSD0 returns a syndrome-valid vector. Syndrome residual weight is **0**, but logical bits **0,2,3,5,6** differ (zero-based):
- observed: `[1,0,0,1,0,0,0,1,0,1,0,0]`;
- predicted: `[0,0,1,0,0,1,1,1,0,1,0,0]`.

A fresh decoder instance reran **only this sample**, with unchanged configuration and exact priors. It reproduced the full archived fault vector bit-for-bit, SHA256 `9a89fe4480dfd888b72d25ea6433511a3dc26b2b9589a152257db61542ddb7ff`; BP iterations and flags also match. Initialization0.489s; decode3.788s (archived3.763s). Initialization and decode each had a10s cap. No Relay or other external sample was decoded. This establishes local deterministic reproducibility, not platform-independent reproducibility or a unique physical explanation. OSD0 solves the syndrome but its chosen coset representative has the wrong observable action; the saved data do not establish that a higher OSD order would correct it.

## What is fair

**Fair now:** paired problem/sample/prior mapping and final syndrome/logical scoring; standard BP versus BP-OSD0 isolates the fallback under identical BP settings. Their BP iteration counts and convergence flags agree on all58; BP-converged predictions agree exactly. Relay's accuracy comparison uses verified archived scores, with raw-prediction rescoring unavailable.

**Not matched:** floating versus fixed precision, gamma/restarts, aggregate N-trajectory work, OSD GF2 cost, and hardware resources. Matching1940 iterations per trajectory does not match N2's total budget. Equal-compute claims need message-update/phase work accounting plus OSD operations, or a common measured software execution budget with equivalent implementations and overhead policy. Merely doubling BP's cap does not equalize OSD cost. Relay cancellation/drain work cannot be inferred from winner iterations.

External times are measured software wall time; Relay cycles are modeled architectural timing, not measured FPGA latency. Existing single, non-interleaved CPU measurements cannot establish a speed advantage. Runtime truncation excluded70 canonical samples; the unfinished request is not a decoder failure.

N2 versus OSD0 has just **one discordant pair** (N2 correct, OSD0 wrong). Exact two-sided paired McNemar/binomial p=1 with one discordance: no evidence of statistical superiority. Zero failures in58 still permits a Wilson95% upper bound about6.21%. N1 and OSD0 each fail once on different samples, so equal counts hide different failure modes.

## Smallest useful next experiment

Freeze this OSD0 configuration and run **only BP-OSD0 on the next8 untouched canonical indices58–65**, with the archived Relay N2 outcomes and identical seed/shot join. Use a new directory,10s per decode and a60s batch cap; report incomplete requests separately and do not select samples by logical labels. This is the smallest practical additional paired batch; it may not resolve the comparison. Continue bounded, predeclared batches through the remaining70 to finish the existing128-sample comparison before making an accuracy claim. No Relay rerun or new STIM generation is needed. Avoid tuning OSD against index36 and then treating it as held-out evidence. A matched-work comparison is a separate experiment requiring the accounting above.

## Inputs, verification and reproduction

Paths relative to project root:
- `results/external_decoder_benchmark/{REPORT.md,configuration.json,run_benchmark.py,BP_results.json,BP_OSD0_results.json,BP_predictions.npz,BP_OSD0_predictions.npz,Relay_archived_records.json,paired_indices.json,provenance.json}`;
- `results/n-scaling-canonical/{per_shot_results.csv,manifest.json,run_study.py}`;
- `results/circuit-level-multiseed/paired_samples.npz`;
- `graphs/generated/gross_circuit_level/memory_Z_r12_p0p003/`;
- `reference/relay_bp_fixed.py` (decode leg/handoff/stopping), `fpga/verification/parallel_n2/gamma_rng_reference.py`;
- installed `../.venv/lib/python3.13/site-packages/ldpc/bposd_decoder/_bposd_decoder.pyx`, decode method, and BP base configuration source.

Dependencies unchanged: LDPC2.4.1, NumPy2.2.6, SciPy1.15.3, STIM1.15.0. Validation independently rescored116 saved external predictions, verified58 canonical syndrome/logical hashes and the single-sample repeat. All pre-existing benchmark and548 protected archive files passed unchanged SHA256 checks; see `validation.json` and `provenance.json` for exact counts/hashes. No archive edits, deletion, staging, commits or pushes.

Executed from project directory:
```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ../.venv/bin/python -B results/external_decoder_benchmark/failure_analysis/analyze.py
../.venv/bin/python -B results/external_decoder_benchmark/failure_analysis/write_report.py
```
The analysis script performs the single repeat; do not run it merely to read outputs. Report generation does not decode. New outputs: `REPORT.md`, `sample_comparison.csv`, `sample_comparison.json`, `single_sample_reproduction.json`, `validation.json`, `provenance.json`, `analyze.py`, `write_report.py`.

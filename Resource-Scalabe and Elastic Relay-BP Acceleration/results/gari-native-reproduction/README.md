# Official GARI native reproduction — PASS_WITH_WARNINGS

## Decision

**YES — the unchanged single-member native implementation completed the official experiment in Python 3.11, passed input-boundary inspection, and produced a statistically compatible logical rate. Proceeding to an adapter is justified with the native semantics below preserved.**

This report validates only the audited native configuration. No same-STIM adapter or matched benchmark was created. Relay-BP was not changed or run. The prior matched-audit file manifest is unchanged.

## Frozen implementation and environment

- URECA commit: `c4dc34e560c7af78b7e6397e506ba6d27f3e7eb7` (current committed tree; existing untracked audit/run artifacts retained).
- Official GARI commit: `6380d52e76d8c9cb0b4eedf3e8d2429b24cef78d` from https://github.com/astra-decoders/gari-nms.git.
- Python: 3.11.2 (v3.11.2:878ead1ac1, Feb  7 2023, 10:02:41) [Clang 13.0.0 (clang-1300.0.29.30)]; Stim 1.16.0.
- Runtime imports: ldpc 2.4.1, stim 1.16.0, sinter 1.16.0, numpy 2.4.6, scipy 1.17.1, networkx 3.6.1, matplotlib 3.11.2, pymatching 2.4.0. README explicitly requests Python 3.11 and `pip install ldpc stim sinter`; transitive/runtime imports and full freeze are recorded.
- Native `my_decoders/hbp_decoder_v2.c` built by unchanged Makefile with Apple Clang and Homebrew libomp. Exit 0; six unused-code warnings retained in build_stderr.txt. Checked-in shared binary was rebuilt for this machine.
- Sources and circuit match the pinned commit byte-for-byte (source_verification.json). No GARI parameter or source was changed.
- Prior dependency/build/redirection failures and the pre-existing Python 3.13 attempt are retained in dependency_and_attempt_history.md and prior_python313/. The prior attempt processed 901,120 shots with 100 logical errors; it is supplementary because it used Python 3.13.

## Exact circuit

`data/circuits/BB_n144_k12_d12_CL_both_0.002.stim`

SHA256: `7111886835770e6489b6a59be0c5bfbfaade69a0c87c10b68301cc868decffcb`

[[144,12,12]] BB memory-Z experiment; 288 circuit qubits (144 data plus ancillas), 1,728 detectors, 12 observables, 12 rounds, p=0.002. CL both-basis noise: p1=p2=p3=p4=p (after Clifford depolarization, reset flips, pre-measurement flips, before-round data depolarization). The checked-in circuit contains an initial round followed by `REPEAT 11`; the command loads this exact existing file, so fallback generation is not needed. Flattened noise instructions have argument 0.002.

## Execution

```sh
python3 stim_batched_data_v2.py 12 0.002 400 0.96875 1 0 2 16 100 0 i 4
```

Working directory `/tmp/gari-native-6380d52`; `/tmp/gari-native-py311/bin` prepended to PATH. Four OpenMP threads, schedule seed 1, normalized min-sum alpha 0.96875, schedule 2, prior type 0, iteration limit 400, CLI ens=0 maps to one member. Stim sampling seed is unspecified, as in the official driver. No outcome-driven parameter changes or repeated search for a successful run.

`observer/sitecustomize.py` is a read-only Python trace: saves already-returned iterations and predicted/observed logical bits after each decoder timing interval. It does not alter decoder inputs, control flow, RNG, or outputs. Total wall time includes trace-dispatch and output-capture overhead; native timed intervals exclude NPZ writes but include any trace-dispatch overhead in the Python wrapper. The C decoder is unchanged and uninstrumented. Both official source and observer are available for inspection.

- Exit: 0; completed 56 batches, **917,504 shots**.
- **102 logical errors**, rate **0.0001111711775** per shot; Sinter pieces=12/values=12 rate 9.26477621e-06.
- **917,402 native converged; 102 native nonconverged/rejected**.
- Nonconverged with logical error: 102; nonconverged without logical error: 0; union (logical error or native rejection): 102.
- Discards: 0. Incomplete shots: 0. Every complete batch and rejection retained. Stop condition >=100 logical errors evaluated only after a full batch.
- Returned iteration-index mean **3.35192544**, median 3, p95 6, p99 10, range 0–400. Mean among native accepted shots 3.30782470. CSV rounded-batch-mean statistic 3.
- Native decoder timed intervals total **1521.066540 seconds**; generated CSV rounded sum 1522 seconds; full process wall time **2265.152860 seconds**.
- Raw stdout and stderr are preserved verbatim. The driver's final `ERROR: ... has ... errors now, printing stats` is its normal error-target termination message, not a runtime failure.

## Cross-environment diagnostic

The Python 3.11 / Stim 1.16 run and preserved Python 3.13 / Stim 1.15 attempt produce identical DEM text hashes (`bf04909de351a8198bc8a2e7a6b5ae1a9b93377132dd6600084d3c2bafdea13d`) and equal values in every generated static matrix/adjacency field. Their rebuilt C libraries are also byte-identical. See cross_environment_static_graph_comparison.json and each attempt's dem_fingerprint.json. This check uses no sampling or decoding and does not substitute the prior attempt for the primary result.

## Official comparison

Exact matching decoder name and strong_id found in `data/final/BB_final_data_combined.csv` line 172: **1,048,576 shots, 100 errors, 0 discards, 567 seconds**, custom_counts `avg_itr=48, base=16` ⇒ rounded batch-mean statistic **3**. Full source CSV and extracted row preserved. This is the closest checked-in configuration match; the row does not encode circuit hash, dependency versions, hardware, thread count, or sampling seed, so exact historical provenance cannot be proved from it alone.

| metric | official/check-in value | reproduced value | difference | interpretation |
|---|---:|---:|---:|---|
| ensemble_size | 1 | 1 | 0 | Decoder name without en suffix and CLI ens=0 map to one member |
| requested_iteration_limit | 400 | 400 | 0 | Unchanged; zero-based inclusive C-loop semantics documented separately |
| normalization_alpha | 0.96875 | 0.96875 | 0 | Exact decoder-name/configuration match |
| shots | 1048576 | 917504 | -131072 | Outcome-stopped experiment; total shots need not match |
| logical_errors | 100 | 102 | 2 | Stop at >=100 errors after a complete 16384-shot batch; overshoot retained |
| discards | 0 | 0 | 0 | Every completed shot retained, including native nonconvergence |
| shot_logical_failure_rate | 9.5367431640625e-05 | 0.00011117117745535714 | 1.580374581473214e-05 | Compatible under approximate rare-event rate-ratio 95% interval |
| sinter_per_round_any_observable_rate | 7.947662318152915e-06 | 9.264776210327064e-06 | 1.3171138921741488e-06 | Same Sinter transformation: pieces=12, values=12; per-round failure of any observable under its independent-piece model |
| avg_itr_div_base_rounded_batch_means | 3.0 | 3.0 | 0.0 | Comparable coarse statistic; official raw avg_itr=48 and base=16; batch sizes not proven identical |
| exact_iteration_index_mean | not available | 3.3519254411969865 | not identifiable | Preserved from native per-shot return arrays |
| native_converged | not available | 917402 | not identifiable | Native selected B/dz block acceptance only |
| native_nonconverged | not available | 102 | not identifiable | 400 sentinel, includes index-400 convergence rejected by batch wrapper |
| logical_or_nonconvergence | not available | 102 | not identifiable | Supplementary accounting; does not replace official logical scoring |
| software_decoder_seconds_csv | 567.0 | 1522.0 | 955.0 | Hardware/environment not matched; different shot count and batch-level rounding; no performance equality requirement |
| software_decoder_seconds_high_precision | not available | 1521.0665397644043 | not identifiable | Native driver timed interval; passive post-call capture excluded |
| software_total_wall_seconds | not available | 2265.152859917027 | not identifiable | Includes graph setup, sampling, passive capture and process startup; concurrent prior run overlaps |

Logical-rate ratio reproduced/official = **1.165714**, approximate 95% interval **[0.884715, 1.535963]**; compatibility = True. We use a rare-event log-rate-ratio interval (SE sqrt(1/e_reproduced+1/e_official)) as a descriptive check. Because each experiment stops on error counts at batch boundaries, this is not an exact fixed-shot equivalence test. The Sinter per-round value is a model-based conversion for failure of any of the 12 observables, not a directly measured per-round event rate or a per-observable rate. No bit-identical stochastic outcome is required: the official Stim sampler has no fixed seed. Matching rounded iteration summaries is weak precision evidence, not exact work equivalence. Runtime differences are reported without using them as fidelity failures or comparing to FPGA nanoseconds/Relay-BP cycles.

## Information boundary and iteration semantics

**PASS: no sampled physical-error or true logical-label input to decoding was found.** Detector/syndrome bits, circuit-derived graph/prior information, and static logical operators are the decoder inputs. Actual observable labels are used only after decoding for scoring and aggregate stopping. See information_boundary.md for source locations and complete limitations.

A sweep visits all expanded-graph check rows serially, in bottom/A/B order with separate A/B schedule permutations, updates normalized min-sum messages and variable LLRs, then checks the B/dz syndrome block. Native returned k<400 is a zero-based sweep index (k+1 completed sweeps). The inclusive loop permits up to 401 sweeps. The batched wrapper maps all nonaccepted outcomes to 400, including convergence at index 400; 400 is a rejection sentinel. Therefore native convergence is not a proof that every expanded constraint is satisfied, and the integer is not an exact universal work count. **It must not automatically be equated with one Relay-BP iteration. No GARI cycle count is invented.**

Native nonconvergence returns zero logical correction. Such shots can match the observed logical bits and be absent from the official logical-error count (none did in this run); the separate counts above expose this instead of discarding or relabeling them. General multi-member iteration selection also has a source caveat documented in information_boundary.md; it is inactive for this one-member reproduction.

## Status rationale

PASS_WITH_WARNINGS: native build/import/run and batch accounting passed; no hidden-information path found; observed logical-rate difference is compatible with sampling variation. Warnings remain for unpinned official environment/provenance, coarse reference iteration metrics, native selected-block/sentinel semantics, passive capture overhead, and overlapping prior-run runtime.

## Saved artifacts

Required files: README.md, environment.json, command.txt, run_stdout.txt, run_stderr.txt, reproduction_summary.json, official_vs_reproduced.csv, native_metrics.csv.

Additional evidence: build logs, dependency history, requirements-freeze.txt, official_source/, source_verification.json, official_reference.json, raw circuit and checked-in results, raw/native_generated/ (CSV, native matrix caches, rebuilt C library), python311/chunk_*.npz (every shot's returned iteration index and predicted/observed observables), chunks.jsonl (batch metrics), completion.json, iteration_histogram.csv, observer source, launch/analysis scripts, prior_python313/ logs and CSV, and prior-audit hash manifest. Shot indices are zero-based and ordered by batch then NPZ row. Per-shot runtime is not emitted; only batch decoder timing is available. No physical error vector is captured. The temporary venv/checkout are not required to interpret the saved raw results.

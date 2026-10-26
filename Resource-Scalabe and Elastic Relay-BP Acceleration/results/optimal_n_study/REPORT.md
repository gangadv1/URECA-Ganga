# Optimal-N decision study

**Primary result: no statistically certified optimum across the full hypothetical deadline grid.** The 128 paired canonical shots support conditional choices for an individually fixed deadline, but not a true physical optimal N. No numerical physical QEC deadline, application reliability target, target clock/Fmax or measured FPGA area was found in the inspected project documents/reports. The 95% target comes from this request.

## Decisions at a 95% success-by-deadline target

Provisioning cost is N×P with P4: N1/2/4/8/16 provision4/8/16/32/64 lanes. It is **not FPGA area**. Deadlines below are hypothetical architectural cycles, **not measured FPGA time**.

| Hypothetical deadline (billion cycles) | Empirical minimum N | Fixed-deadline supported minimum N¹ | Full-grid supported minimum N² |
|---:|---:|---:|---|
| 0.3 | none | none | no statistically certified optimum |
| 0.5 | 8 | none | no statistically certified optimum |
| 0.75 | 8 | 8 | no statistically certified optimum |
| 1 | 8 | 8 | no statistically certified optimum |
| 1.1 | 4 | 8 | no statistically certified optimum |
| 1.5 | 4 | 8 | no statistically certified optimum |
| 2 | 2 | 8 | no statistically certified optimum |
| 4 | 1 | 4 | no statistically certified optimum |
| 8 | 1 | 2 | no statistically certified optimum |

¹ One-sided exact95% lower bounds with Bonferroni alpha=.05/5 protect selection among five N for **one deadline fixed independently of this grid search**. These are conditional examples, not the primary full-grid conclusion.
² Bonferroni alpha=.05/45 protects all five N × nine deadlines simultaneously at95% family confidence. Even128/128 successes gives lower bound **94.824%**, below95%; hence no candidate qualifies. Correcting for only five N gives96.466% with128/128. Correlated/nested deadlines make the45-test correction conservative, but it is valid without assuming independent configurations. We also supply pointwise exact intervals and one-sided bounds, clearly separated in the CSV.

“Supported minimum” means the least provisioned candidate **certified by this bound**, not proof that every smaller N truly fails the population target. Failing to certify is not evidence of infeasibility. There is no statistical guarantee independent of the sampling/timing assumptions.

## Latency and provisioning

All completed shots, including failures, contribute to latency statistics. All-fail waits for the last engine. Percentiles use NumPy linear interpolation; p99 depends on approximately the two largest of128 observations.

| N | Provisioned lanes | Correct /128 | Mean cycles (billion) | p95 cycles (billion) | p99 cycles (billion) |
|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 125 | 0.7267 | 2.2580 | 7.3843 |
| 2 | 8 | 128 | 0.4713 | 1.4557 | 2.2087 |
| 4 | 16 | 128 | 0.3756 | 1.0470 | 1.6985 |
| 8 | 32 | 128 | 0.3013 | 0.4931 | 0.6482 |
| 16 | 64 | 128 | 0.2945 | 0.4302 | 0.5908 |

N1 has3 nonconvergences; N2/N4/N8/N16 have none. No syndrome-valid logical errors occur in this128-shot archive. All five points are Pareto nondominated for mean/lanes and p99/lanes; lower latency alone does not select an optimum. N16 wins absolute observed mean/p95/p99, while doubling N8 provisioning buys just2.25% lower mean and8.85% lower p99. Dedicated P4 resources per trajectory are assumed by the model; cancellation/quiescence, shared-resource contention, FPGA routing/clock scaling and timing closure are not measured here. No historical active_work column is used as executed work.

## Reuse, scoring and invariants

Reuse the complete canonical128 rows at Gross[[144,12,12]], memoryZ, p=.003,12 noisy rounds, final perfect measurement, P4. Four STIM seeds20260809–20260812 contribute32 shots each. The640-sample NPZ is joined by seed/shot, not flattened; canonical eligibility remains exactly128. N trajectories are nested prefixes of the same16 archived engines. The unchanged canonical budgets are first80/later60, R32/S1, maximum1940 iterations per engine, first gamma.125 and seeded later gamma, b18/g4/M16.

For each engine, canonical scoring uses H·e mod2 against detectors and A·e mod2 against observed logicals. `reference/relay_bp_fixed.py` receives only priors and syndrome; labels are used after decoding in `run_study.py`. First syndrome-valid engine wins by result cycles, lowest engine index on ties; logical labels do not choose winners. A wrong-logical winner remains a failure even if another engine would be logically correct. All-fail completion uses maximum engine result cycles. This study verified all640 archived ensemble choices/cycles,2048 derived trajectory seeds,128 detector/logical hashes, aggregate mean/p95/p99, and N1–N8 historical archive equality. Raw Relay fault predictions are absent; we verify/reuse scored outcomes rather than claim independent prediction rescoring.

Successful-by-deadline indicator for shot i: **logical_correct(i,N) AND completion_cycles(i,N) ≤ D**. Nonconvergence, logical errors and misses all fail. CSV partitions failures into nonconvergence, logical errors, and correct-but-late (disjoint); per-shot indicators preserve sample IDs and every outcome. A late nonconvergent shot is counted once.

## Statistical method and paired evidence

For k successful shots of n128, the two-sided95% exact Clopper–Pearson interval is [Beta⁻¹(.025;k,n−k+1), Beta⁻¹(.975;k+1,n−k)], with0/1 boundary conventions. One-sided selection lower bounds replace.025 with.05, .05/5 or.05/45 as labeled. Smallest qualifying N minimizes the provisioning proxy among candidates whose appropriate bound≥.95.

The analysis plan was frozen in methodology.json before this script calculated results, **after the original data and resource report existed**. This is retrospective, not a prospective preregistration or independent held-out selection study. Exact binomial confidence statements assume independent sampled shots from the fixed noise model and fixed decoder/RNG policy; N engines and N configurations are not treated as independent observations. Four sample seeds do not establish device/noise-model variability. No confidence bound covers timing-model error or physical deployment shifts.

N2/N4/N8 comparisons use exact two-sided discordant-pair McNemar/binomial tests, followed by Holm correction over27 tests (three pairs ×nine deadlines), retaining overlapping paired samples. Seven deadline comparisons pass the adjusted.05 threshold:
- at.5 billion: N4 vsN2 gains11/128, adjusted p=.02148; N8 vsN2 gains25/128, p=.00000161; N8 vsN4 gains14/128, p=.00305;
- at.75 billion: N8 vsN2 gains17/128, p=.000397; N8 vsN4 gains10/128, p=.04102;
- at1 billion: N8 vsN2 gains14/128, p=.00305;
- at1.1 billion: N8 vsN2 gains12/128, p=.01123.
These are sample-dependent deadline coverage differences under the model, not evidence that one N meets a physical reliability requirement. Other grid comparisons do not pass this family correction. Without deadlines, N2/N4/N8 have identical128/128 correctness, so the archive cannot distinguish their logical reliability. Paired results include both directions; no monotonic-success assumption is used.

## BP-OSD0 comparison

Reused58 matching archived samples (indices0–57), not compared to Relay's full128 as if matched. BP-OSD0 succeeds57/58; Relay N1 also57/58 on a different failed shot; Relay N2/N4/N8/N16 succeed58/58. N2 versusOSD0 has one discordance and exact two-sided p=1: no superiority evidence. The independently investigated OSD0 index36 failure is syndrome-valid/logically wrong and reproduced with unchanged settings.

Both use exact canonical H/fault priors and sample IDs; OSD0 uses LDPC2.4.1 parallel floating minimum-sum, max1940 iterations, scale1, one thread, followed by OSD order0 on BP failure. Relay has gamma, fixed precision, relay handoffs and N×1940 maximum aggregate iteration budgets. Thus data/scoring are matched; computation is not. OSD elimination cost has no matched Relay budget. No additional decoding was run. External mean CPU decode time1.4706 seconds is reported separately from Relay modeled cycles in BP_OSD0_paired_comparison.csv; no cross-domain deadline or speedup is calculated. CPU runs were non-interleaved and prefix/runtime limited. A fair joint hardware-deadline comparison requires an external hardware timing/resource model or common measured implementation and work budget.

## Additional experiment decision and runtime gate

**No new decoding was necessary or launched:** all requested N have complete paired canonical data. This study executes the selection analysis, not a redundant decoding campaign. There is no pilot-derived additional-decoding runtime estimate; none is invented from modeled hardware cycles or LDPC CPU times. Analysis runtime is in validation.json (seconds, not decoding time).

For a new confirmatory study, first choose one physically justified deadline/target and freeze the configuration; then use fresh samples or unused NPZ shots with disjoint seed/shot IDs. Any decoding pilot should use one new syndrome through16 nested engines, cap60s, project total wall time before continuation, and stop if projected runtime exceeds600s. No proposed large run was started. Budget/seed list and stopping policy must be frozen before seeing outcomes; ordinary fixed-n intervals cannot be repeatedly inspected for optional early success without a sequentially valid method.

For planning only, all-success sample requirements are90 shots for a five-N fixed-deadline bound and133 for the45-test full-grid bound. Thus128 can never meet the primary grid criterion;133 total would be enough **only if every shot succeeds** at that candidate/deadline. Adding five adaptively after seeing this result and claiming ordinary fixed-n certification would need a valid preregistered continuation/sequential analysis; it is not automatic independent confirmation. Fresh selection validation is preferable. The low-deadline failures need substantial additional evidence or performance changes, not merely five samples.

## Hardware evidence and exact input paths

- `results/n-scaling-canonical/{per_shot_results.csv,aggregate_summary.json,manifest.json,run_study.py}`; `results/n-scaling-canonical-n8-complete/per_shot_results.csv`;
- `results/circuit-level-multiseed/paired_samples.npz`;
- `graphs/generated/gross_circuit_level/memory_Z_r12_p0p003/`; `reference/relay_bp_fixed.py`; `fpga/verification/parallel_n2/gamma_rng_reference.py`;
- `results/resource_tradeoff_analysis/{REPORT.md,comparison.csv,hypothetical_deadlines.csv}`;
- `results/external_decoder_benchmark/{REPORT.md,configuration.json,BP_OSD0_results.json,paired_indices.json,Relay_archived_records.json,failure_analysis/REPORT.md}`;
- `results/m4-memory-fabric-synthesis/{final_synthesis_report.md,full_fabric_resources.csv,timing_summary.csv}` says BLOCKED BEFORE SYNTHESIS / NOT EXECUTED;
- `results/vivado-n1-baseline/summary.md` identifies absent target/toolchain/clock; `fpga/reports/README.md` is a placeholder;
- `results/gari-vs-relaybp-system/relaybp_memory_summary.json` gives analytical storage capacity, not measured LUT/FF/BRAM/DSP. Its original replicated engine model is32,342,676 bits/engine and900 banked BRAM36 capacity equivalents; that is not actual FPGA area. Alternative M4 sharing models cannot be mixed with canonical dedicated-engine latency without contention/timing validation;
- `docs/research_proposal/relay_bp_fpga_research_proposal.md` and `docs/architecture/parallel_relay_bp_fpga_architecture.md` motivate real-time decoding but do not specify a numerical physical deadline. Repository text/report search found no documented numerical physical target for this setup. Literature/design placeholders are not implemented hardware measurements.

Actual FPGA area-delay product and physical deadline feasibility remain **unavailable**. Full-model cycle calibration against limited RTL tests does not establish measured full-size FPGA time.

## Outputs and final objective-specific choices

- `minimum_N_by_deadline.csv`, `deadline_metrics.csv`: empirical, pointwise and adjusted confidence rules for all45 cases.
- `per_shot_deadline_indicators.csv`, `paired_deadline_tests.csv`: paired outcomes and exact/Holm tests.
- `latency_resource_summary.csv`, `BP_OSD0_paired_comparison.csv`.
- `deadline_minimum_N.png/.pdf`, `latency_provisioning_pareto.png/.pdf`: presentation-ready,320dpi PNGs and vector PDFs.
- `methodology.json`, `analysis_summary.json`, `validation.json`, `provenance.json`, `analyze.py`, `write_report.py`, `test_analysis.py`, `REPORT.md`.

**Objective-specific answers:** N1 minimizes provisioning without a certified reliability/deadline constraint. N16 minimizes observed mean/p95/p99 without a resource penalty. All five are Pareto nondominated. Under empirical95% criteria, the table selects N1/N2/N4/N8 depending on deadline; N16 is never the smallest empirical qualifier on this grid. Under the independently fixed-deadline five-N rule, N8 qualifies at.75–2 billion, N4 at4 billion and N2 at8 billion; none qualifies at.3/.5 billion. Under the primary full-grid rule, **no statistically certified optimum at any deadline**. No true physical optimum can be asserted until physical deadline/target, hardware resource counts/Fmax and independent validation are supplied.

Reproduction from project directory (analysis only):
```sh
MPLCONFIGDIR=/private/tmp/relay-optimal-matplotlib OPENBLAS_NUM_THREADS=1 ../.venv/bin/python -B results/optimal_n_study/analyze.py
../.venv/bin/python -B results/optimal_n_study/write_report.py
MPLCONFIGDIR=/private/tmp/relay-optimal-matplotlib ../.venv/bin/python -B results/optimal_n_study/test_analysis.py
```

Validation: PASS; 594 protected files unchanged. No decoding, synthesis, deletion, staging, commits or pushes. Exact input hashes and script/methodology hashes are in provenance.json.

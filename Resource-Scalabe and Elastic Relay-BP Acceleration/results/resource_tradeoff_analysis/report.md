# Resource-aware canonical N-scaling analysis

Only archived results were analyzed. Gross [[144,12,12]], physical p=.003, P4, 128 paired shots, four sample seeds; R32, first/later 80/60, S1. Modeled architectural cycles preserve archived first-success/last-engine-on-all-fail semantics. Phase costs have RTL calibration evidence; complete FPGA timing is not measured.

| N | Lanes | Mean cycles | p99 cycles | Mean × lanes | p99 × lanes | Success / failure | Mean gain vs N1 / previous | p99 gain vs N1 / previous |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 726,676,462.74 | 7,384,342,292.90 | 2,906,705,850.97 | 29,537,369,171.60 | 125 / 3 | 0.00% / — | 0.00% / — |
| 2 | 8 | 471,284,891.68 | 2,208,714,916.37 | 3,770,279,133.44 | 17,669,719,330.96 | 128 / 0 | 35.15% / 35.15% | 70.09% / 70.09% |
| 4 | 16 | 375,628,783.02 | 1,698,536,134.99 | 6,010,060,528.25 | 27,176,578,159.84 | 128 / 0 | 48.31% / 20.30% | 77.00% / 23.10% |
| 8 | 32 | 301,304,127.66 | 648,150,995.70 | 9,641,732,085.25 | 20,740,831,862.40 | 128 / 0 | 58.54% / 19.79% | 91.22% / 61.84% |
| 16 | 64 | 294,525,755.52 | 590,788,735.09 | 18,849,648,353.50 | 37,810,479,045.76 | 128 / 0 | 59.47% / 2.25% | 92.00% / 8.85% |

Products are provisioned lane-cycle proxies: elapsed completion cycles × N × P. They are neither busy executed work nor actual FPGA area-delay product and do not model cancellation/drain utilization. No historical active_work is used. N1 has three nonconvergences; all other N have zero failures. No syndrome-valid logical errors were observed. Zero failures in 128 shots still has Wilson 95% upper bound about 2.91%.

Pareto rule: a point is dominated only if another uses no more lanes and has no greater latency, with at least one strict improvement. All five configurations are nondominated for both mean and p99: latency falls as provisioning rises. No point is uniquely optimal without a budget or utility. N16 is best for absolute observed mean/p99 but doubles N8 lanes for just 2.25% mean and 8.85% p99 gain. N1 minimizes mean lane-cycle product; N2 minimizes p99 lane-cycle product. These proxy minima do not establish minimum area-delay or energy.

Recommendations under explicit priorities:

- Minimum hardware provisioning: N1 (four lanes) is the true minimum. If requiring at least two trajectories or eliminating the three observed N1 failures, N2 (eight lanes) is the smallest ensemble; actual FPGA fit remains unverified.
- Average-latency compromise: N4 (16 lanes) reduces mean by 48.31% vs N1 and 20.30% vs N2. Choose it only if that gain justifies doubling N2 provisioning. N16 wins absolute mean, not resource efficiency.
- Tail-latency priority: N8 (32 lanes) cuts p99 by 61.84% vs N4 and 91.22% vs N1. It is a practical tail-focused compromise; N16 cuts a further 8.85% for twice the lanes. N2 is the best observed p99×lanes proxy if provisioning dominates.
- Deadline satisfaction: select the smallest N meeting a declared target, using success-by-deadline rather than completion alone when correctness is required. The examples below are explicitly hypothetical, chosen to illustrate priorities rather than assert a real deadline.
  - At 2 billion cycles and a hypothetical ≥95% successful-by-deadline target, smallest observed qualifying N is 2: 125/128 (97.66%).
  - At 1.1 billion cycles and a hypothetical ≥95% successful-by-deadline target, smallest observed qualifying N is 4: 124/128 (96.88%).
  - At 0.75 billion cycles and a hypothetical ≥95% successful-by-deadline target, smallest observed qualifying N is 8: 128/128 (100.00%).

Deadline formulas: completion fraction = count(completion_cycles ≤ D)/128; successful fraction additionally requires archived logical_correct=1. Grid: 0.3, 0.5, 0.75, 1, 1.1, 1.5, 2, 4, 8 billion hypothetical cycles. Graph is an empirical completion CDF; CSV contains both completion and success counts. Outcomes are paired across N. No true application deadline or clock is invented.

Resource evidence: results/m4-memory-fabric-synthesis/final_synthesis_report.md says BLOCKED BEFORE SYNTHESIS; full_fabric_resources.csv and timing_summary.csv contain NOT EXECUTED entries. results/m4-memory-fabric-rtl/synthesis_summary.csv likewise contains no inferred counts. results/vivado-n1-baseline/summary.md reports missing target/toolchain. No actual Relay-BP LUT/FF/BRAM/DSP/Fmax or area-delay product is available; literature GARI figures are a different design.

A defensible architecture-specific capacity model exists in results/gari-vs-relaybp-system/relaybp_memory_summary.json: one original P4 engine has 15,407,678 static bits + 16,934,998 input/dynamic bits = 32,342,676 bits, 900 per-array/four-bank BRAM36 capacity equivalents. Current N2 duplicates full fabrics: 64,685,352 bits / 1,800 banked capacity equivalents. Conditional full replication would give 32,342,676×N bits and 900×N capacity equivalents, but N4/8/16 implementation, routing, clocks and packing are not verified. M4 sharing/aliasing has different analytical estimates and cannot be mixed with this original replication model. All such counts are analytical storage capacity, not actual resource utilization or area. Sharing may require port replication and contention; no performance benefit is assumed.

Limitations: 128 samples constrain tail estimates (p99 depends on roughly the largest two observations) and failure conclusions. Hypothetical deadline coverage is empirical, not a guaranteed service level or a statistically significant comparison. Modeled N trajectories assume dedicated P-lane engines; FPGA timing closure, shared-resource stalls, cancellation effects and clock scaling are not characterized by these plots. No decoding, synthesis, commit or push was run.

Inputs (exact paths relative to project root):
- `results/n-scaling-canonical/per_shot_results.csv`
- `results/n-scaling-canonical/aggregate_summary.json`
- `results/n-scaling-canonical/manifest.json`
- `results/n-scaling-canonical-n8-complete/per_shot_results.csv`
- `results/m4-memory-fabric-synthesis/final_synthesis_report.md`
- `results/m4-memory-fabric-synthesis/full_fabric_resources.csv`
- `results/m4-memory-fabric-synthesis/timing_summary.csv`
- `results/m4-memory-fabric-rtl/synthesis_summary.csv`
- `results/vivado-n1-baseline/summary.md`
- `results/gari-vs-relaybp-system/relaybp_memory_summary.json`
- `results/relaybp-memory-optimization/final_memory_report.md`

Outputs: comparison.csv, hypothetical_deadlines.csv, report.md, three 3840×2240 PNGs and vector PDFs, analyze.py, validation.json and provenance.json. All calculations are plotting/analysis only. Mean = arithmetic mean; p99 = NumPy linear percentile rank 0.99×127; improvement = 100×(1−new/old).

Command from project directory:
```sh
MPLCONFIGDIR=/private/tmp/relay-resource-matplotlib ../.venv/bin/python -B results/resource_tradeoff_analysis/analyze.py
```

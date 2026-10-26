# Paired four-code pilot

Four shots/code; p=0.003; N=1,2; P=2,4; first/later limits=2/2; R=2; S=1. Maximum four iterations/engine. Sample seed=20261010; trajectory base seed=7640891576956012809. Every configuration uses folding_original; all timings, including Gross P4, are structural extrapolations rather than RTL-calibrated latency.

All 16 configurations completed. N1 and N2 results are identical in this bounded pilot; the following rows apply to each N.

| Code | P | Failure/4 | Nonconvergence | Logical errors | Mean engine iterations | Mean cycles (M) | Mean critical retries | Issue-group occupancy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 18_4_3 | 2 | 2/4 | 2 | 0 | 2.5 | 0.379 | 14,862 | 78.8% |
| 18_4_3 | 4 | 2/4 | 2 | 0 | 2.5 | 0.255 | 16,075 | 58.4% |
| 72_12_6 | 2 | 4/4 | 4 | 0 | 4.0 | 5.957 | 262,890 | 78.2% |
| 72_12_6 | 4 | 4/4 | 4 | 0 | 4.0 | 3.993 | 279,364 | 58.0% |
| 144_12_12 | 2 | 4/4 | 4 | 0 | 4.0 | 25.401 | 1,103,946 | 78.6% |
| 144_12_12 | 4 | 4/4 | 4 | 0 | 4.0 | 17.095 | 1,220,314 | 58.1% |
| 288_12_18 | 2 | 4/4 | 4 | 0 | 4.0 | 78.026 | 3,465,524 | 78.4% |
| 288_12_18 | 4 | 4/4 | 4 | 0 | 4.0 | 52.470 | 3,789,178 | 58.0% |

Validation: 248 pairing/regression assertions passed; 1919 protected files hash-unchanged. Run/check time 49.4s before plotting. No P-driven changes in engine decisions, scoring, iterations, legs, RNG words or seeds; no P winner changes or N first-success changes.

Failure Wilson 95% intervals: 2/4 = [15.0%,85.0%]; 4/4 = [51.0%,100%]. Zero logical errors in four shots has an upper Wilson bound of 49.0%. These tiny-budget results are not code-performance/LER trends. Larger codes hit the four-iteration budget on every shot.

Winner mean iterations: BB18=1 on two successful shots; other codes unavailable (no successful winners). Per-engine and per-shot statistics are in each run. Bank conflict events and retry subsets use the same archived counter convention. Occupancy is weighted over issue groups on the natural critical trajectory (winner, or last engine if all fail), not total N-engine executed work or elapsed PE utilization. Cancellation acknowledgement/drain and exact executed useful work are unavailable.

Increasing P reduced structural cycles, but increased retry-subset counts and reduced issue-group occupancy. This is modeled scheduling behavior, not a decoder anomaly or hardware measurement.

Exact execution from workspace root:
```sh
.venv/bin/python -B 'Resource-Scalabe and Elastic Relay-BP Acceleration/simulations/configurable_testbench/pilots/paired_bb_4shot_20261010/run_pilot.py'
MPLCONFIGDIR=/private/tmp/relay-pilot-matplotlib .venv/bin/python -B 'Resource-Scalabe and Elastic Relay-BP Acceleration/simulations/configurable_testbench/pilots/paired_bb_4shot_20261010/plot_pilot.py'
```
The driver refuses existing configs/runs; reproduce in a fresh sibling pilot directory. commands.json contains all 16 exact testbench subprocess commands; configs/ contains their complete configurations. Pilot/run manifests record input, implementation and output hashes, versions and base commit.

Next heuristic experiment: compare original versus graph-specific frozen BA2 residue assignments at fixed P4 across these four graphs. Preserve mathematical fault order and gamma correspondence, validate decoder equivalence, and measure bank retries/issue-group occupancy before raising decoder budgets.

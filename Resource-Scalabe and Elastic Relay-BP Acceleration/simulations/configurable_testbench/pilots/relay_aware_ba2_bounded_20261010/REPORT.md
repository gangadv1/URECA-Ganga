# Relay-aware fault banking at P4

PASS: same validated four-code/four-shot pilot, N1/2, physical p=.003, sample seed 20261010, trajectory base seed 7640891576956012809, first/later budgets 2/2, R2/S1. All cycles below are structural extrapolations, not measured RTL or FPGA timing.

The heuristic freezes existing BA2 edge maps, builds relay fault co-access groups in physical remapped edge order, seeds fault residues with capacity-constrained relay-only greedy coloring, then uses exact relay retry-reducing bank swaps. Greedy seed is retained only if its exact retry objective improves on BA2. Refinement is bounded to the first 512 faults ordered by weighted co-access degree/identity, two passes, at most eight deterministic partners per other bank. Swaps preserve address-residue capacities exactly. Duplicate fault references remain separate accesses; no broadcast is assumed.

| Code | Layout | Variable retries | Relay-init retries | Convergence retries | Total retries/conflicts | Structural cycles | Group occupancy | Mean completion cycles | Mean engine iterations | Failures |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 18_4_3 | original | 4,470 | 1,260 | 1,204 | 6,934 | 110,735 | 59.52% | 255,232.5 | 2.5 | 2/4 |
| 18_4_3 | BA2 | 0 | 2,097 | 1,128 | 3,225 | 101,843 | 64.67% | 230,491.5 | 2.5 | 2/4 |
| 18_4_3 | BA2_relay | 0 | 1,238 | 2,016 | 3,254 | 101,930 | 64.63% | 233,286.0 | 2.5 | 2/4 |
| 72_12_6 | original | 48,384 | 14,526 | 14,194 | 77,104 | 1,111,228 | 60.19% | 3,993,290.0 | 4.0 | 4/4 |
| 72_12_6 | BA2 | 0 | 21,836 | 10,609 | 32,445 | 1,001,443 | 66.60% | 3,510,290.0 | 4.0 | 4/4 |
| 72_12_6 | BA2_relay | 0 | 13,787 | 20,423 | 34,210 | 1,006,738 | 66.32% | 3,579,764.0 | 4.0 | 4/4 |
| 144_12_12 | original | 212,136 | 62,425 | 61,730 | 336,291 | 4,758,697 | 60.27% | 17,094,956.0 | 4.0 | 4/4 |
| 144_12_12 | BA2 | 0 | 95,438 | 47,128 | 142,566 | 4,283,590 | 66.78% | 14,996,450.0 | 4.0 | 4/4 |
| 144_12_12 | BA2_relay | 0 | 60,039 | 88,894 | 148,933 | 4,302,691 | 66.55% | 15,285,248.0 | 4.0 | 4/4 |
| 288_12_18 | original | 661,498 | 192,833 | 189,380 | 1,043,711 | 14,607,524 | 60.23% | 52,469,832.0 | 4.0 | 4/4 |
| 288_12_18 | BA2 | 0 | 316,775 | 144,175 | 460,950 | 13,189,990 | 66.59% | 46,056,044.0 | 4.0 | 4/4 |
| 288_12_18 | BA2_relay | 0 | 189,210 | 297,204 | 486,414 | 13,266,382 | 66.29% | 47,127,002.0 | 4.0 | 4/4 |

Structural profiles describe one full iteration plus one relay initialization. Mean completion cycles weight actual per-engine iterations and legs; N1/N2 share outcomes and means on this panel. All failures are nonconvergence; no syndrome-valid logical errors. BB18 engines have iteration counts [1,4,4,1] per shot for each engine; all other engines have four iterations. Small samples/tiny budgets do not establish LER trends.

Relay retries improve versus BA2 for every code, and fall below original-layout counts. Convergence retries regress for every code: total one-iteration-plus-relay cycles regress versus BA2 by 0.09%, 0.53%, 0.45%, and 0.58% respectively. Actual pilot completion costs regress more because convergence runs each iteration while relay initialization runs each leg. Occupancy likewise regresses slightly versus BA2. This is a relay-specific objective, not a total-runtime improvement.

Validation before profiling: 32 paired decoder trajectories / 64 calls, 116 exact inverse-mapped iteration states; graph H, logical-action A, fault probabilities/priors, gamma, decisions/beliefs/messages/residuals, syndrome order, logical scoring, iteration counts, and RNG schedules preserved. Original and existing BA2 phase profiles reproduce the archived comparison exactly. Existing BA2 edge maps remain fixed. No winner/outcome changes; all-fail waits for the last engine. Two deterministic heuristic unit tests passed (duplicate/partial groups; capacities, inverse identity, determinism and nonregressing relay objective). 2,075 protected files remained unchanged. Bounded panel runtime: 41.2 seconds.

Limitations: four-shot/R2/S1 equivalence is not a universal proof. Physical maps are modeled separately from decoder CSR ordering. No integrated RTL calibration, measured utilization, shared-trajectory contention, exact cancellation work or drain timing is inferred. Issued-group occupancy is a structural service-group measure. The earlier full-sweep attempt is preserved separately in ../relay_aware_ba2_20261010/; its largest-code subprocess hit the 180-second timeout and produced no performance result. The completed bounded implementation is in this directory.

Next experiment: keep validated BA2 edge placement and optimize a budget-weighted combination of convergence and relay retries, using actual access groups after edge remapping and a bounded Pareto sweep. Revalidate exact traces before selecting a scheduling baseline. Current BA2 remains the better total-runtime baseline on this panel.

New files: compare_relay.py, test_relay_assignment.py, comparison.csv/json, structural_comparison.png, phase_retries.png, validation.json, provenance.json, protected_hashes.json, commands.json and per-code maps, objectives, exact trace hashes, invariants, profiles and selection records. See commands.json for exact subprocess commands.

Commands from the project directory:

```sh
MPLCONFIGDIR=/private/tmp/relay-ba2-matplotlib ../.venv/bin/python -B simulations/configurable_testbench/pilots/relay_aware_ba2_bounded_20261010/compare_relay.py
../.venv/bin/python -B -m unittest discover -s simulations/configurable_testbench/pilots/relay_aware_ba2_bounded_20261010 -p test_relay_assignment.py -v
```

No existing files were modified, deleted, staged, committed or pushed.

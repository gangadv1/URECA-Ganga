# Graph-specific BA2 controlled comparison

PASS: all four validated circuit-level BB packages support explicit BA2 storage maps at P=4. Fault identity is preserved with recorded forward/inverse maps; priors, gamma, decisions, decoder edge messages and logical-action columns are mapped consistently. No decoder mathematics or historical files were changed.

Matched completed pilot: four shots per code, physical p=0.003, sample seed 20261010, trajectory base seed 7640891576956012809, N=1/2, P=4, first/later budgets 2/2, R=2, S=1. Logical labels are used only after decoding.

| Code | Structural cycles original → BA2 | Reduction | Retries/conflicts original → BA2 | Issued-group occupancy | Mean completion cycles original → BA2 | Failures original/BA2 |
|---|---:|---:|---:|---:|---:|---:|
| 18_4_3 | 110,735 → 101,843 | 8.03% | 6,934 → 3,225 | 59.52% → 64.67% | 255,232.5 → 230,491.5 | 2/4 / 2/4 |
| 72_12_6 | 1,111,228 → 1,001,443 | 9.88% | 77,104 → 32,445 | 60.19% → 66.60% | 3,993,290.0 → 3,510,290.0 | 4/4 / 4/4 |
| 144_12_12 | 4,758,697 → 4,283,590 | 9.98% | 336,291 → 142,566 | 60.27% → 66.78% | 17,094,956.0 → 14,996,450.0 | 4/4 / 4/4 |
| 288_12_18 | 14,607,524 → 13,189,990 | 9.70% | 1,043,711 → 460,950 | 60.23% → 66.59% | 52,469,832.0 → 46,056,044.0 | 4/4 / 4/4 |

Structural cycles, retries and occupancy above describe one full iteration plus relay initialization. Mean completion cycles use the observed per-shot iteration/leg counts. N1 and N2 have identical outcomes and mean completion cycles on this bounded panel. All failures are nonconvergence; syndrome-valid logical errors are zero. Wilson 95% failure intervals are [0.150, 0.850] for BB18 and [0.510, 1] for the other codes. Four shots and tiny budgets do not establish LER trends.

All timings, including Gross here, use the same structural folding model and are not integrated RTL-calibrated latency. Occupancy is issued-group lane occupancy, not measured PE utilization. Retry subsets/conflict events are model-generated counts, not hardware counters. No shared-trajectory contention, exact cancellation work or cancellation/drain timing is inferred.

Validation: 32 paired engine trajectories (64 decoder calls), 116 exact paired iteration states, all graph/prior/gamma/logical invariants, original pilot reproduction and archived Gross BA2 map equality passed. First-success/tie decisions were unchanged; all-fail completion waits for the last engine. 2,034 protected files remained hash-identical. Decoding/comparison wall time was 39.5 seconds.

Variable-phase retries became zero for every code. Relay-initialization retries increased: BB18 1,260 → 2,097; BB72 14,526 → 21,836; Gross 62,425 → 95,438; BB288 192,833 → 316,775. These regressions are retained. The inherited fault objective uses relay groups before edge remapping, so it does not optimize the final relay access pattern.

BA2 is a valid controlled software baseline for new P4 scheduling heuristics on these graphs and this panel. This bounded equivalence check does not prove universal decoder equivalence or a hardware speedup. Next experiment: freeze the validated BA2 edge map and optimize fault-bank assignments against actual relay co-access groups after edge remapping, using capacity-preserving swaps; rerun inverse-mapped trace checks and the same paired panel before broadening budgets.

Outputs: comparison.csv/json, structural_comparison.png, validation.json, provenance.json, protected_hashes.json and commands.json. Each code directory contains storage_maps.npz, invariants.json, decoder_equivalence.json, phase_profiles.json, bank_assignment_statistics.json, per_shot_selection.json and provenance.json. Maps distinguish physical edge placement from decoder CSR edge ordering.

Exact driver command, run from the workspace root:

```sh
MPLCONFIGDIR=/private/tmp/relay-ba2-matplotlib .venv/bin/python -B 'Resource-Scalabe and Elastic Relay-BP Acceleration/simulations/configurable_testbench/pilots/ba2_graph_specific_20261010/compare_ba2.py'
```

Exact per-code subprocess commands are recorded in commands.json; input/output hashes and inherited configuration are recorded in provenance files. No files were staged, committed, pushed or deleted.

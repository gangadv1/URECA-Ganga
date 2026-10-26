# Frozen weighted BA2 held-out validation

PASS for all four supported BB codes: four paired shots per code, N1/2, P4, first/later 8/8, R2/S1, circuit sampling at p=.003. No layouts or multipliers were retuned or selected using held-out data. BA2 and weighted fault maps were loaded from existing archives; reconstruction from their stored residues was checked against every stored forward/inverse map. Edge maps are identical and frozen.

Held-out STIM seed: 2026101101. Trajectory base seed: 11400714819323198485. These differ from training sample seed 20261010 and trajectory base seed 7640891576956012809; all eight per-code held-out engine seeds are explicitly checked disjoint from the eight tuning engine seeds. Source circuit and package selection are unchanged. Source and layout hashes, selected multipliers, actual seed lists and sample hashes are recorded.

The initial launch stopped before decoding because Config is immutable; that preflight attempt is preserved in ../weighted_ba2_heldout_20261010. The completed implementation uses dataclass replacement.

## Held-out completion results

All cycles are structural model extrapolations, not measured RTL/FPGA timing. Completion estimates combine the frozen phase service profiles with observed held-out iteration/leg counts. First-success chooses the earliest converged engine, with lowest-index ties; all-fail waits for the last engine. Logical validity is scored only after decoding. No exact cancellation/drain work or timing is modeled.

| Code | N | Shots | Mean engine iterations | BA2 mean completion cycles | Weighted mean completion cycles | Reduction | Failures both | Failure Wilson 95% |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 18_4_3 | 1 | 4 | 7.250 | 599,694.8 | 597,102.0 | 0.432% | 1/4 | [0.046, 0.699] |
| 18_4_3 | 2 | 4 | 7.750 | 599,694.8 | 597,102.0 | 0.432% | 0/4 | [0.000, 0.490] |
| 72_12_6 | 1 | 4 | 15.750 | 12,366,288.5 | 12,317,868.5 | 0.392% | 3/4 | [0.301, 0.954] |
| 72_12_6 | 2 | 4 | 15.875 | 12,366,288.5 | 12,317,868.5 | 0.392% | 3/4 | [0.301, 0.954] |
| 144_12_12 | 1 | 4 | 16.000 | 53,572,070.0 | 53,369,978.0 | 0.377% | 4/4 | [0.510, 1.000] |
| 144_12_12 | 2 | 4 | 16.000 | 53,572,070.0 | 53,369,978.0 | 0.377% | 4/4 | [0.510, 1.000] |
| 288_12_18 | 1 | 4 | 16.000 | 164,112,428.0 | 163,480,700.0 | 0.385% | 4/4 | [0.510, 1.000] |
| 288_12_18 | 2 | 4 | 16.000 | 164,112,428.0 | 163,480,700.0 | 0.385% | 4/4 | [0.510, 1.000] |

All observed failures are nonconvergence; syndrome-valid logical errors are zero. Zero errors in four shots has Wilson 95% upper bound about 0.490, so it does not establish a low logical-error rate. BB18 N2 rescues the N1 failure; this legitimate ensemble change appears equally in both layouts. Mean engine iterations includes every engine, not just the winner. Full per-engine iterations/legs and per-shot winners are retained. See comparison.csv for sample-weighted critical-path occupancy and retries.

## Frozen structural profiles (not independent held-out evidence)

These profiles are layout/graph/P dependent and independent of sample seeds or iteration limits. They are reused exactly from weighted_ba2_validated_20261010, with protected hashes; repeated numbers below are contextual schedule data, not newly measured evidence. Values describe one iteration plus one relay initialization.

| Code | Layout | Variable retries | Convergence retries | Relay retries | Total retries/conflicts | Structural cycles | Issued-group occupancy |
|---|---|---:|---:|---:|---:|---:|---:|
| 18_4_3 | BA2 | 0 | 1,128 | 2,097 | 3,225 | 101,843 | 64.67% |
| 18_4_3 | weighted | 0 | 1,093 | 1,690 | 2,783 | 100,517 | 65.34% |
| 72_12_6 | BA2 | 0 | 10,609 | 21,836 | 32,445 | 1,001,443 | 66.60% |
| 72_12_6 | weighted | 0 | 9,873 | 19,562 | 29,435 | 992,413 | 67.08% |
| 144_12_12 | BA2 | 0 | 47,128 | 95,438 | 142,566 | 4,283,590 | 66.78% |
| 144_12_12 | weighted | 0 | 44,156 | 85,532 | 129,688 | 4,244,956 | 67.27% |
| 288_12_18 | BA2 | 0 | 144,175 | 316,775 | 460,950 | 13,189,990 | 66.59% |
| 288_12_18 | weighted | 0 | 135,523 | 280,703 | 416,226 | 13,055,818 | 67.14% |

Validation: 32 engine trajectories; each run in original-ID, BA2-mapped and weighted-mapped decoders (96 calls), with 445 exact iteration states per mapping comparison. BA2 and weighted hashes are each compared to original-ID states, preserving gamma, integer/float priors/state, beliefs, decisions, messages, residuals, saturation counts, convergence flags and iteration indices. Frozen graph H/logical action A, probabilities, identity maps and syndrome order are invariant. Logical labels never enter decoder inputs. One four-code unit test checks frozen capacities/identity/edge maps and seed disjointness. No layout-to-layout winner/outcome changes.

Runtime: 48.1 seconds, all 16 requested shots completed. Per-code policy permits four shots initially and stops before another full shot when elapsed plus prior maximum shot duration would exceed 60 seconds. Subprocess hard cap is 75 seconds, clipped to the remaining 180-second total decoding/comparison budget. Runtime scope reduction was unnecessary. 2166 protected files remained hash-identical.

Verdict: the frozen weighted improvement generalizes to this small held-out 8/8 panel within the structural model. All four paired completion costs improve for each code/N. The magnitude is smaller than in tuning because iteration/relay frequencies changed. Since the selected layouts lower both convergence and relay retries with fixed variable cost, positive modeled savings are expected at any positive phase frequency; held-out testing primarily validates decoder equivalence and the realized savings magnitude. This does not prove hardware gains, universal decoder equivalence or statistical generalization to broad workloads. Four samples give wide failure intervals and no reliable LER trend.

No measured PE utilization, shared-engine contention, top-level/RNG overhead or FPGA calibration is claimed. Structural occupancy is service-group lane occupancy. Next: a separate modest held-out panel across physical error rates/budgets, followed by RTL-level cancellation/banking validation if hardware timing claims are needed; keep these assignments frozen.

## Commands and output

Commands from the project directory:

```sh
MPLCONFIGDIR=/private/tmp/relay-ba2-matplotlib ../.venv/bin/python -B simulations/configurable_testbench/pilots/weighted_ba2_heldout_checked_20261010/validate_heldout.py
../.venv/bin/python -B -m unittest discover -s simulations/configurable_testbench/pilots/weighted_ba2_heldout_checked_20261010 -p test_heldout.py -v
```

commands.json contains exact subprocess commands. comparison.csv/json, completion_summary.json, structural_comparison.png (plots held-out completion costs/retries), validation.json, protected_hashes.json, provenance.json and per-code requested configuration, frozen-layout hashes, sample hashes, engine iterations, exact trace hashes, invariants, reused phase profiles, per-shot selections, progress and provenance are saved here. No archives were overwritten; no files were deleted, staged, committed or pushed.

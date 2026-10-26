# Budget-weighted P4 fault banking

PASS: existing BA2 physical edge maps remain fixed. Fault banks are selected by a deterministic three-weight greedy sweep with exact capacity constraints and BA2 as an explicit candidate/fallback. Logical labels are never inputs to assignment or decoding.

## Objective and controls

For a fixed edge map, check cycles, base phase service, variable access counts and variable retries remain constant under fault placement. Variable cycles are 14V + 8qv + 5*(variable_retries/2) + 1. Convergence cycles are 8C + 6qc + 3*Rc + 1; relay initialization cycles are 8qe + 3*Rr + 1. Therefore expected completion cost differs only by 3*(Ibar*Rc + Lbar*Rr). Ibar and Lbar come exclusively from iteration/leg counts in the completed paired pilot, averaged across engines/shots. BB18 uses 2.5 iterations / 1.5 legs; other codes use 4 / 2. This is an in-sample frequency model, not a hardware cancellation model.

Seed objectives use Ibar*convergence co-access + multiplier*Lbar*relay co-access, with multipliers 0.5, 1, 2. Relay groups use BA2 physical edge order; convergence groups retain check-neighborhood access order. Weighted-degree/identity ordering and deterministic bank tie-breaking are inherited. Greedy assignment preserves exact modulo-4 bank capacities. Seeds are ranked by exact retry counts at the actual frequency ratio, with BA2 winning ties. Unselected seeds have capacity/objective checks only; the selected map receives full inverse-mapped decoder checks before profiling. They are not claimed as decoder-validated performance candidates.

Runtime caps: 45-second optimization guard per code, 90-second subprocess hard timeout, subprocess budget clipped to a 240-second total decoding/comparison deadline, plus projection stop at 240 seconds. Four codes, four paired shots, N1/2, P4, p=.003, sample seed 20261010, trajectory base seed 7640891576956012809, first/later budgets 2/2, R2/S1. No decoding math or RNG changes.

## Actual structural model results

All cycles are structural extrapolations, not measured RTL/FPGA timing. Profiles below describe one iteration plus one relay initialization. Occupancy is issued-group lane occupancy, not hardware PE utilization. Mean completion cycles use actual verified iteration/leg counts and first-success selection, lowest-index ties, or last-engine completion on all-fail. N1/N2 have identical means/outcomes on this panel.

| Code | Layout | Variable retries | Convergence retries | Relay retries | Total retries/conflicts | Structural cycles | Occupancy | Mean completion cycles | Iterations | Failures |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 18_4_3 | original | 4,470 | 1,204 | 1,260 | 6,934 | 110,735 | 59.52% | 255,232.5 | 2.5 | 2/4 |
| 18_4_3 | BA2 | 0 | 1,128 | 2,097 | 3,225 | 101,843 | 64.67% | 230,491.5 | 2.5 | 2/4 |
| 18_4_3 | relay_only | 0 | 2,016 | 1,238 | 3,254 | 101,930 | 64.63% | 233,286.0 | 2.5 | 2/4 |
| 18_4_3 | weighted | 0 | 1,093 | 1,690 | 2,783 | 100,517 | 65.34% | 228,397.5 | 2.5 | 2/4 |
| 72_12_6 | original | 48,384 | 14,194 | 14,526 | 77,104 | 1,111,228 | 60.19% | 3,993,290.0 | 4.0 | 4/4 |
| 72_12_6 | BA2 | 0 | 10,609 | 21,836 | 32,445 | 1,001,443 | 66.60% | 3,510,290.0 | 4.0 | 4/4 |
| 72_12_6 | relay_only | 0 | 20,423 | 13,787 | 34,210 | 1,006,738 | 66.32% | 3,579,764.0 | 4.0 | 4/4 |
| 72_12_6 | weighted | 0 | 9,873 | 19,562 | 29,435 | 992,413 | 67.08% | 3,487,814.0 | 4.0 | 4/4 |
| 144_12_12 | original | 212,136 | 61,730 | 62,425 | 336,291 | 4,758,697 | 60.27% | 17,094,956.0 | 4.0 | 4/4 |
| 144_12_12 | BA2 | 0 | 47,128 | 95,438 | 142,566 | 4,283,590 | 66.78% | 14,996,450.0 | 4.0 | 4/4 |
| 144_12_12 | relay_only | 0 | 88,894 | 60,039 | 148,933 | 4,302,691 | 66.55% | 15,285,248.0 | 4.0 | 4/4 |
| 144_12_12 | weighted | 0 | 44,156 | 85,532 | 129,688 | 4,244,956 | 67.27% | 14,901,350.0 | 4.0 | 4/4 |
| 288_12_18 | original | 661,498 | 189,380 | 192,833 | 1,043,711 | 14,607,524 | 60.23% | 52,469,832.0 | 4.0 | 4/4 |
| 288_12_18 | BA2 | 0 | 144,175 | 316,775 | 460,950 | 13,189,990 | 66.59% | 46,056,044.0 | 4.0 | 4/4 |
| 288_12_18 | relay_only | 0 | 297,204 | 189,210 | 486,414 | 13,266,382 | 66.29% | 47,127,002.0 | 4.0 | 4/4 |
| 288_12_18 | weighted | 0 | 135,523 | 280,703 | 416,226 | 13,055,818 | 67.14% | 45,735,788.0 | 4.0 | 4/4 |

Selected weights and verified improvements versus BA2:

- 18_4_3: weight_1; structural cycles −1.302%; mean completion cycles −0.908%.
- 72_12_6: weight_0.5; structural cycles −0.902%; mean completion cycles −0.640%.
- 144_12_12: weight_0.5; structural cycles −0.902%; mean completion cycles −0.634%.
- 288_12_18: weight_0.5; structural cycles −1.017%; mean completion cycles −0.695%.

Negative results: the inherited relay-only candidate regresses convergence and total cycles versus BA2 for all codes. Higher relay weight can also increase convergence conflicts; all three seed objectives are retained in weight_sweep.json rather than suppressing rejected seeds. This limited sweep is not a proof of optimality.

Validation: 32 paired trajectories / 64 decoder calls, 116 exact iteration states; inverse mappings preserve fault identity, priors/probabilities, gamma, H/A connectivity, check/syndrome order, decoded decisions/beliefs/messages/residuals, saturations, scoring and iteration/leg counts. Existing original/BA2/relay-only profiles reproduce archived profiles exactly; prior baseline equivalence reports are protected inputs. Outcomes/winners remain unchanged; no syndrome-valid logical errors. BB18 failures 2/4, other codes 4/4, all nonconvergence. Two unit tests passed (capacity/determinism/exact objective and BA2 tie fallback).

Elapsed comparison 47.9s; 2118 protected historical files hash-identical. No cancellation/drain timing, exact busy work, shared-pool contention or measured FPGA timing is inferred. Four shots with tiny budgets do not establish logical-error trends. The frequency model must be validated on a held-out larger-budget panel before generalizing.

The first attempt in ../weighted_ba2_20261010 stopped after largest-code equivalence on a reporting-variable shadowing error. It is preserved, with no performance claim. This completed attempt fixes that bookkeeping.

## Commands and outputs

From the project directory:

```sh
MPLCONFIGDIR=/private/tmp/relay-ba2-matplotlib ../.venv/bin/python -B simulations/configurable_testbench/pilots/weighted_ba2_validated_20261010/compare_weighted.py
../.venv/bin/python -B -m unittest discover -s simulations/configurable_testbench/pilots/weighted_ba2_validated_20261010 -p test_weighted.py -v
```

Exact per-code commands are in commands.json. comparison.csv/json, phase_profiles, per-shot selections, weight_sweep objectives, maps, decoder traces, invariants, validation and input/output hashes are retained. Plots use actual generated profiles only. No existing files were deleted, modified, staged, committed or pushed.

Next experiment: freeze these selected assignments and test held-out seeds with moderately larger iteration budgets before extending scheduling optimization. Compare observed phase frequencies against the tuning frequencies; retain BA2 fallback and equivalence checks.

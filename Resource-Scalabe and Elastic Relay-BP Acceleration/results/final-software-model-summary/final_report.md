# Consolidated Relay-BP graph-layout software-model report

## Scope

This report consolidates existing validated software results for the Gross [[144,12,12]] memory-Z circuit-level decoding graph at p=0.003. It introduces no new layout, decoder run, synthesis result, or FPGA-speedup claim.

## Research pipeline

The STIM memory circuit produces a Detector Error Model that is converted into a connected bipartite graph of detector/check nodes and fault-variable nodes. Its detector-fault incidence matrix `H`, logical-action matrix `A`, fault probabilities, and syndrome define the Relay-BP mathematical problem. The fixed-point Relay-BP decoder generates fault-indexed decisions and edge-indexed messages; graph permutations are valid only when all mathematical identities, probabilities, syndromes, gamma values, corrections, and logical conventions are mapped consistently.

The original folded model time-multiplexes graph accesses through four lanes and maps an address to bank `address % 4`. METIS subsequently partitions and reorders the graph for generic locality. BA2 is different: it uses actual P=4 co-access groups to choose reversible fault and message address residues that directly reduce same-bank conflicts. The stagnation experiment is separate again: it changes the modeled service order between two already fixed N=2 trajectories and does not change their graph or decoder equations.

## Original graph and layout

The canonical graph has 1,728 checks, 67,752 fault variables, 391,320 detector-fault incidences, and 12 logical observables. It contains 69,480 bipartite vertices, is fully connected, and has density 0.00334246.

The original P=4 layout produced 336,291 retry subsets, 2.410877 mean active lanes, 60.2719% lane utilization, and 4,758,697 structural modeled cycles. Across the archived 128-shot E0 panel its modeled mean was 726,388,133 cycles, P95 was 2,257,054,018, and P99 was 7,381,272,452.

## METIS locality experiment

The selected limited METIS direct k-way run used k=4 and seed 2. It enforced exact counts of 432 checks and 16,938 faults per partition after deterministic typed rebalancing. Its balanced edge cut was 40,882, or 10.4472%, compared with 74.9532% for random balanced and 54.3698% for the simple greedy control. Boundary fractions were 78.4722% for checks and 34.5849% for faults. All H, A, probability, incidence, and permutation invariants passed.

The mapped fixed-point decoder then reproduced all 256 E0/E1 trajectories exactly. Nevertheless, METIS node-only ordering increased retry subsets by 2.222%, structural cycles by 0.471%, and the trajectory-weighted mean by 0.318%. This negative result is diagnostic: edge-cut locality is not the same objective as avoiding collisions under `logical_address % 4`.

## Selected BA2 bank-aware layout

BA2 builds static co-occurrence weights from requests that the exact folded access model groups together. Fault and message identities that frequently co-occur are greedily assigned different modulo-4 residues while exact capacities and workload balance are enforced. Deterministic forward/inverse permutations convert those residues into addresses; graph connectivity and Relay-BP mathematics remain unchanged.

BA2 reduced retry subsets from 336,291 to 142,566, a 57.606% reduction. Variable MU and NU retries each fell from 106,068 to zero. Mean active lanes increased from 2.410877 to 2.671397 and utilization increased from 60.2719% to 66.7849%. Structural modeled cycles fell from 4,758,697 to 4,283,590, or 9.984%.

Trajectory weighting gives a modeled mean of 617,117,727 cycles, P95 of 1,917,397,629, and P99 of 6,270,598,460. These are respectively 15.043%, 15.049%, and 15.047% below original.

Decoder equivalence is exact: 128/128 E0 and 128/128 E1 trajectories match, totaling 47,736/47,736 mapped iterations. All 33 E1 wins and all three E1 rescue cases match. There are no trace mismatches, invalid mappings, outcome changes, or logical regressions.

## BA2 refinement decision

The relay-init regression was traced to fault co-occurrence being evaluated before the final BA2 edge order even though relay init groups consecutive final edge IDs. F1 and F3 corrected that representation. F1 improved one-pass structural cost but increased the archived trajectory mean by 0.628% versus BA2. F3 was consistently lower than BA2 but by only 0.0243% in the mean. Because this gain is negligible and BA2 already has complete equivalence evidence, the declared final selection is **BA2**.

## Optional stagnation-priority result

Stagnation identifies some low-value relay behavior, but productive flagged legs and late convergence make hard stopping unsafe. A non-destructive shared-resource model therefore tested a frozen 2:1 service priority while both trajectories remained eligible and continued to natural completion.

At p=0.003 it preserved 128/128 successes, all 48 late recoveries, and produced no logical regression or starvation. Mean modeled time to first success decreased by 0.392% and P95 by 3.474%; seven shots improved, 117 were unchanged, and four worsened. The p=0.002 and p=0.004 archives have no paired E1 seeds or trajectories, so cross-p validation cannot be claimed. Stagnation priority remains optional and is not part of the selected main layout.

## Final comparison

| Layout | Locality edge-cut ratio | Structural retry change | Structural cycle change | Trajectory mean change | Equivalence |
|---|---:|---:|---:|---:|---|
| Original | N/A | 0% | 0% | 0% | Reference |
| METIS node-only | 10.4472% | +2.222% | +0.471% | +0.318% | 256/256 exact after mapping |
| BA2 | N/A | -57.606% | -9.984% | -15.043% | 256/256; 47,736 iterations exact |

## Conclusions

1. The decoding graph has strong partitionable locality.
2. Generic METIS locality alone does not improve the current P=4 bank mapping.
3. The direct bottleneck is simultaneous same-bank access under address modulo four.
4. BA2 targets that bottleneck and is substantially more effective than generic partition ordering.
5. BA2 preserves the complete tested fixed-point Relay-BP behavior while reducing modeled folding cost.
6. Stagnation is unsafe for work termination and remains only an optional scheduling signal.

## Prioritized next tasks

1. Test frozen BA2 on additional graph/code instances.
2. Sweep folding factor P, beginning with P=2, 4, and 8 where practical.
3. Compare BA2-based folding with GARI using the same workload and cost definitions.
4. Consider RTL/HLS mapping only after the broader software-model result is stable.

## Plain-English meeting summary

We decoded the circuit-level graph for the Gross [[144,12,12]] memory-Z experiment, containing 1,728 checks and 67,752 fault variables. METIS showed strong graph locality, but that locality alone did not help the four-bank folding model because bank conflicts depend on address modulo four. BA2 instead placed faults and messages according to which values the folded decoder accesses together. It reduced modeled structural retries by 57.6% and trajectory-weighted modeled cycles by about 15%. All 256 archived decoder trajectories remained exact after mapping, including every known E1 win and rescue. Stagnation-based priority remains optional because its mean benefit is small and cross-error-rate validation is incomplete. The next step is to validate BA2 on other graphs and folding factors before considering hardware implementation.

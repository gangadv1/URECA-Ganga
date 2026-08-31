# GARI-relative novelty analysis

## Direct answers

**A. Does GARI explicitly optimize simultaneous modulo-bank co-access conflicts?** No evidence of that objective appears in arXiv:2605.01035v1. GARI constrains variables sharing a check to different tile memories and heuristically maps variables/checks to tiles, but its reported routing uses tags, crossbars, queues, and back-pressure rather than `address % 4` residues and retry-subset minimization.

**B. Does GARI assign graph objects to banks from co-access statistics?** Not as reported. The serial mapping uses check independence; the `U,V` placement is degree-guided; timing is refined by cycle-accurate simulation. Pair/group co-occurrence weights are not described.

**C. Does GARI use a similar graph-partition/layout heuristic?** Only at a broad “map graph objects to finite memories/tiles” level. Its guided/greedy placements are code-specific architectural mappings of a GARI-transformed graph. BA2 greedily colors fault and incidence objects into four address residues using exact P=4 access-group co-occurrence and workload balance. METIS is also fundamentally different from GARI: it partitions an existing graph for locality, whereas GARI changes the inference factorization to improve BP.

**D. Is BA2 distinct?** Yes, against the mechanisms disclosed in this paper:

- BA2 preserves connectivity, while GARI augments/rewires the factor graph.
- BA2 preserves Relay-BP equations and verified trajectories, while GARI applies normalized min-sum to a changed variable/check representation.
- BA2 is a reversible storage/message-address layout, not an inference transform.
- BA2 directly minimizes weighted modulo-four co-access conflicts and balances bank work.

This supports a distinction, not a superiority or universal novelty claim. A broader literature search and the earlier GARI algorithm paper [20] would still be required for a formal novelty claim.

## Strongest defensible technical story

GARI demonstrates that correlated-error decoding can be made hardware-scalable by changing the detector-model factorization and matching specialized serial/parallel units to the resulting `D_X,D_Z,U,V` blocks. The repository addresses a different gap: after fixing Relay-BP and an existing P=4 folded issuer, generic graph locality does not predict modulo-bank contention. BA2 therefore preserves the mathematical decoder and assigns fault/message storage residues from the issuer's actual co-access groups, reducing modeled retry and cycle cost while retaining exact tested trajectories. It is best described as **bank-aware folded memory/layout optimization for Relay-BP**, complementary to rather than a replacement for GARI.

## GARI baseline classification

| Baseline category | Use? | Reason |
|---|---:|---|
| Decoder accuracy | PARTIAL | Relevant correlated-BP reference, but this architecture paper provides no matched logical-error table and uses a different decoder/graph. |
| Correlated-error decoding | YES | GARI's central purpose is joint inference over X/Y/Z correlated errors. |
| Architecture/resource reuse | YES | The paper implements and measures explicit serial/parallel block reuse. |
| Folding | PARTIAL | It time-reuses units, but not the same P=4 lane/bank folding model. |
| Latency | PARTIAL | It is an important external hardware target, but no direct ranking is valid until BA2 is implemented and benchmarked equivalently. |
| Multi-core ensemble | YES | It is a primary multi-core capacity/reference architecture, with caveats about unreported diversity/arbitration. |
| Memory organization | YES | It provides concrete tile-memory, FIFO, ROM, and crossbar organization. |
| BA2-style bank conflicts | NO | It does not report the modulo-four co-access objective or retry scheduler BA2 optimizes. |

## Claims to avoid

- BA2 beats 596 ns/round.
- BA2 uses fewer resources than GARI.
- GARI's three cores are equivalent to Relay-BP N=2.
- The two `[[144,12,12]]` studies use the same DEM/workload.
- GARI's “sixfold” statement means every resource count fell sixfold; it is an eight-versus-48 FPGA/device comparison for 24 cores.

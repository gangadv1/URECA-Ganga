# Concurrent Relay-BP trajectory architecture assessment

## Engine definition

One engine is one complete canonical b18 Relay-BP trajectory with P=4, S=1, R=32, first gamma 0.125, and later gamma interval [-0.12, 0.54]. All engines decode the same syndrome using the same graph, physical priors, iteration limits, fixed arithmetic, and convergence rule. Engines differ only in persistent RNG seed, later-leg per-node gamma vectors, and all state derived from that trajectory. They are not individual relay legs.

Because first gamma is uniform, all engines intentionally execute the same first leg. Diversity starts only at the first disordered later leg. This preserves the approved algorithm configuration and prevents artificial first-leg diversity.

## Ideal identical-engine timing model

The model used the same five deterministic Tier-2 seeds and 640 shots as the fixed-point lock study. Each shot was decoded by four independent canonical b18 trajectories. Timing is in decoder iterations and assumes identical P=4 engines with no shared-memory stalls.

| Engines | Success | Avg | p50 | p90 | p99 | Max | Avg reduction | p99 reduction | Corrections different from engine 0 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 640/640 | 110.84 | 72.5 | 194.1 | 705.92 | 1485 | - | - | 0 |
| 2 | 640/640 | 88.27 | 72.5 | 127.3 | 407.54 | 1274 | 20.4% | 42.3% | 159 |
| 4 | 639/640 | 77.38 | 72.5 | 115.0 | 210.47 | 421 | 30.2% | 70.2% | 225 |

N=4 selected one syndrome-valid logical error. On that shot the winning wrong candidate completed at iteration 131 with weight 473.32; a correct engine completed at 300 with weight 474.64. Therefore weight selection cannot distinguish the logical error.

## Selection policies for N=4

| Policy | Success | Avg | p99 | Max | Avg weight |
|---|---:|---:|---:|---:|---:|
| First success | 639/640 | 77.38 | 210.47 | 421 | 342.80 |
| 60-iteration window, lowest weight | 639/640 | 137.38 | 270.47 | 481 | 340.19 |
| 120-iteration window, lowest weight | 639/640 | 197.38 | 330.47 | 541 | 339.96 |
| First 2 candidates, lowest weight | 639/640 | 87.78 | 349.54 | 1274 | 340.72 |
| First 3 candidates, lowest weight | 639/640 | 107.85 | 567.96 | 1274 | 339.94 |
| All 4 candidates, lowest weight | 639/640 | 148.48 | 1099.18 | 1759 | 339.71 |

These policies approximate cross-engine candidate collection; they do not reproduce sequential Relay-BP-S RNG ordering. None repaired the logical error. A bounded weight window is therefore not justified for the first implementation.

## Storage scaling

Ideal packed sizes from the I/O study:

- Shared dual-traversal graph: 1,925,960 bytes.
- Shared prior plus syndrome: 152,658 bytes.
- Private state per complete engine: 2,125,107 bytes.

With one logically shared graph:

| N | Shared graph/prior/syndrome | Private state | Total |
|---:|---:|---:|---:|
| 1 | 2,078,618 B | 2,125,107 B | 4,203,725 B (4.009 MiB) |
| 2 | 2,078,618 B | 4,250,214 B | 6,328,832 B (6.036 MiB) |
| 4 | 2,078,618 B | 8,500,428 B | 10,579,046 B (10.089 MiB) |

If graph tables are replicated per engine to guarantee independent P=4 reads, total packed storage becomes approximately 4.009 MiB, 7.873 MiB, and 15.60 MiB for N=1, 2, and 4 respectively. Physical priors and syndrome remain shared/broadcast.

## Graph memory strategy

- Fully shared graph: lowest capacity, but needs N simultaneous P=4-equivalent reads or arbitration. A single-port-equivalent memory serializes engines and destroys the modeled latency benefit.
- Fully replicated graph: N times graph capacity, no arbitration, deterministic independent progress, and the cleanest experiment isolating spatial parallelism.
- Banked shared graph: intermediate capacity and possible concurrent reads, but engines are synchronized through their identical first leg and are likely to request the same banks simultaneously. Multiported replication or broadcast of identical addresses helps during leg 1; later trajectories diverge and create conflicts.

For the first N=2 FPGA experiment, replicate the read-only graph traversal memories per engine unless target-device capacity rules this out. This keeps graph bandwidth from confounding the research hypothesis. Later work can compare shared/banked graph storage explicitly.

## Controller and cancellation

The global controller broadcasts request ID, syndrome, configuration, and start. Each engine receives a distinct seed and advances independently after synchronization. Engines report candidate-valid, completion cycle, weight, correction-buffer ownership, and failure.

First-success arbitration latches the first syndrome-valid notification. Same-cycle ties use lowest engine ID for deterministic behavior. The winner's correction buffer is committed to the output descriptor. Losing engines receive cancel, stop issuing new graph/message operations at a defined phase-safe boundary, invalidate pending writes, and acknowledge quiescence before their private memories are reused.

If one engine fails, it becomes inactive while others continue. If all fail, global failure is returned after the last failure. A winner does not permit immediate destructive reset of a loser that still has writes in flight; cancellation must drain or invalidate those transactions. New-shot admission waits for all engines to be quiescent unless double-buffered request contexts are later introduced.

With synchronous early-stop, non-winning work before the winner is inherent: 50% of active engine-cycles for N=2 and 75% for N=4. Immediate cancellation prevents additional post-winner work. If engines instead run to natural completion, the measured mean fraction of total counterfactual work occurring after the winner is 7.65% for N=2 and 11.77% for N=4.

## Recommendation

Implement N=2 complete P=4 engines with first-success arbitration, separate RNG/gamma/state, replicated read-only graph memories, shared/broadcast priors and syndrome, private full-buffered mu/nu/marginal/gamma/candidate state, and phase-safe immediate cancellation. N=2 is the stronger first experiment because it delivers a 42.3% p99 reduction and 20.4% mean reduction with unchanged 640/640 logical success, while N=4 doubles private/graph capacity and bandwidth again and exposed a one-shot logical-performance concern that needs broader software validation.

Before any N=4 RTL, run a larger independent-seed panel and additional physical-error points to estimate whether the observed logical difference is random or systematic. Also convert iteration counts into schedule-aware P=4 cycle traces, including relay initialization and cancellation boundaries, and validate a bit-exact multi-engine arbitration model.

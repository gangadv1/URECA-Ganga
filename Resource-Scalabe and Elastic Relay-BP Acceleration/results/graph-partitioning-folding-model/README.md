# Graph-partitioning P=4 folding/access model

Software-only comparison of the canonical Tier-2 graph in three layouts: original, METIS node IDs with original edge/message IDs, and a deterministic partition-aware edge-ID reorder. No RTL, decoder equations, graph incidences, or validated trajectories are changed.

The model mirrors the current controllers: groups contain up to four consecutive traversal entries; bank is `logical_address % 4`; conflicts are retried using the stable first-pending-lane-per-bank subset. Its original-layout phase-cycle equations reproduce all four phase counters in the Tier-2 RTL verification summary exactly.

Node-only reordering deliberately retains old edge/message IDs. The separate edge variant sorts incidences by `(new check ID, new fault ID, old edge ID)` and assigns consecutive edge IDs. This is an access-layout experiment only; Relay-BP was not rerun with the new edge order.

## Full-graph result

| Layout | Retry subsets | Mean active lanes | Full-4 fraction | One-iteration-plus-init cycles |
|---|---:|---:|---:|---:|
| Original | 336,291 | 2.410877 | 37.271008% | 4,758,697 |
| METIS nodes only | 343,765 | 2.401840 | 36.818006% | 4,781,119 |
| METIS + edge reorder | 331,574 | 2.416616 | 37.304568% | 4,749,357 |

Node-only changes retries by +2.222% and modeled cycles by +0.471%. The edge-reordered variant changes retries by -1.403% and modeled cycles by -0.196%. These are software-model effects, not FPGA speedup measurements.

Run with `../.venv/bin/python results/graph-partitioning-folding-model/run_folding_layout_comparison.py`.

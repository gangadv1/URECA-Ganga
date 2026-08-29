# Unpartitioned Tier-2 graph baseline

This folder profiles the canonical gross `[[144,12,12]]` memory-Z circuit-level
decoding graph at `p=0.003`. It performs no partitioning, reordering, Relay-BP
decode, or RTL operation.

Run from the project root with:

```bash
python3 results/graph-partitioning-baseline/run_graph_baseline.py
```

## Baseline summary

- Checks/detectors: 1,728
- Fault variables: 67,752
- Detector-fault incidences: 391,320
- Connected components: 1
- Largest component: 69,480 total nodes
- Isolated nodes: 0
- Check degree: min 51, max 242, mean 226.458333, median 242.0
- Fault degree: min 1, max 9, mean 5.775770, median 6.0
- Bipartite density: 0.00334245975519
- Invariance checks: all passed

Detailed statistics and percentiles are in `graph_stats.json`; degree histograms
are in `degree_stats.csv`.

## Future k=4 formulation definitions (not implemented)

### A. Partition fault-variable nodes only

Each fault receives one of four labels. A detector-fault incidence is cross-partition
only in the derived sense that a check touches faults with different labels; checks
themselves have no partition label. Relabelling/permuting fault columns preserves the
Relay-BP equations when `H`, `A`, probabilities, state vectors, and output corrections
are permuted consistently. This is sensible for studying fault-indexed storage and
logical-output permutation, but it does not directly assign checks or edge-message IDs.

### B. Partition detector/check nodes only

Each check receives one of four labels. A fault may then touch checks in several
partitions. Relabelling/permuting rows preserves Relay-BP when the syndrome and all
check-indexed data move with the rows. It can model check-work balance, but it is less
directly aligned with fault-indexed priors, decisions, and logical actions.

### C. Partition the full bipartite graph

Both checks and faults receive labels. An incidence is cross-partition when its two
endpoints have different labels. This formulation can jointly express balance and
locality for both node types, but cuts do not automatically equal P=4 bank conflicts,
and preserving neighborhoods requires explicit edge and inverse-permutation metadata.
Pure relabelling still preserves Relay-BP if every associated row, column, syndrome,
prior, logical-action, message, and correction mapping is updated consistently.

No partitioning algorithm or partition assignment is present in this folder.

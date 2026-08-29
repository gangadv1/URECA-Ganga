# METIS graph-partitioning experiment

## Current status

Partition execution is blocked because this environment contains no installed
METIS-compatible Python interface or command-line executable. No package was
installed, no substitute was presented as METIS, and no partition assignment was
created.

The preflight entry point is:

```bash
python3 results/graph-partitioning-metis/run_metis_partitioning.py
```

It audits `pymetis`, `metis`, `networkit`, `nxmetis`, and the `gpmetis`,
`mpmetis`, and `ndmetis` executables. It also validates the canonical Tier-2
graph and records the planned combined-index convention and four conceptual
balance channels. Until a compatible interface is available, it exits with code
2 before partition execution.

## Graph convention

- Check `Ci`: combined vertex ID `i`, for `0 <= i < 1728`.
- Fault `Vj`: combined vertex ID `1728 + j`, for `0 <= j < 67752`.
- Every `[fault_id, detector_id]` row in `edge_lists.npz::detector_edges`
  becomes one undirected bipartite edge.

The preflight requires 69,480 vertices, 391,320 undirected incidences, valid ID
ranges, and no duplicate detector-fault incidence.

## Planned balance channels

The intended multi-constraint model has four conceptual vertex-weight channels:

1. check indicator;
2. fault indicator;
3. check degree workload;
4. fault degree workload.

Whether these can be enforced simultaneously must be decided from the API of the
eventually available interface. The current experiment makes no support claim.

## Intentionally absent outputs

`metis_runs.csv`, selected membership, permutations, invariance results, control
comparisons, and the small-graph METIS result are not emitted because no METIS run
occurred. Creating those files with placeholder partition results would make the
experiment appear completed when it is not.

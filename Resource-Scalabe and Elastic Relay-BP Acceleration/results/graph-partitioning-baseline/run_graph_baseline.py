#!/usr/bin/env python3
"""Profile the canonical Tier-2 decoding graph without partitioning or reordering."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import connected_components


OUT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = OUT_DIR.parents[1]
GRAPH_DIR = PROJECT_ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
EXISTING_BASELINE = PROJECT_ROOT / "results/circuit-level-baseline/run_circuit_level_baseline.py"
PERCENTILES = (1, 5, 25, 50, 75, 95, 99)


def sha256_array(array: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(array)
    digest = hashlib.sha256()
    digest.update(str(contiguous.dtype).encode("ascii"))
    digest.update(str(contiguous.shape).encode("ascii"))
    digest.update(contiguous.tobytes())
    return digest.hexdigest()


def matrix_from_edges(edges: np.ndarray, rows: int, columns: int) -> sparse.csr_matrix:
    matrix = sparse.csr_matrix(
        (np.ones(len(edges), dtype=np.uint8), (edges[:, 1], edges[:, 0])),
        shape=(rows, columns),
        dtype=np.uint8,
    )
    matrix.data &= 1
    matrix.eliminate_zeros()
    matrix.sort_indices()
    return matrix


def edge_array_from_fault_csr(indptr: np.ndarray, indices: np.ndarray) -> np.ndarray:
    faults = np.repeat(np.arange(len(indptr) - 1, dtype=np.int32), np.diff(indptr))
    return np.column_stack((faults, indices.astype(np.int32, copy=False)))


def canonical_edge_set(edges: np.ndarray) -> np.ndarray:
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    return np.asarray(edges[order], dtype=np.int32)


def load_existing_baseline_matrices() -> tuple[sparse.csr_matrix, sparse.csr_matrix, np.ndarray]:
    """Call the existing Tier-2 baseline's own graph-construction function."""
    spec = importlib.util.spec_from_file_location("existing_circuit_level_baseline", EXISTING_BASELINE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import existing baseline from {EXISTING_BASELINE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_matrices()


def degree_summary(degrees: np.ndarray) -> dict[str, object]:
    values = np.percentile(degrees, PERCENTILES)
    return {
        "min": int(degrees.min()),
        "max": int(degrees.max()),
        "mean": float(degrees.mean()),
        "median": float(np.median(degrees)),
        "percentiles": {str(p): float(v) for p, v in zip(PERCENTILES, values)},
    }


def histogram(degrees: np.ndarray) -> dict[int, int]:
    counts = np.bincount(degrees)
    return {degree: int(count) for degree, count in enumerate(counts) if count}


def write_degree_csv(check_degrees: np.ndarray, fault_degrees: np.ndarray) -> None:
    rows: list[dict[str, int | str]] = []
    for node_type, degrees in (("check", check_degrees), ("fault", fault_degrees)):
        for degree, count in histogram(degrees).items():
            rows.append({"node_type": node_type, "degree": degree, "node_count": count})
    with (OUT_DIR / "degree_stats.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=("node_type", "degree", "node_count"))
        writer.writeheader()
        writer.writerows(rows)


def write_small_graph() -> None:
    h_small = np.asarray(
        [[1, 1, 1, 0], [0, 1, 1, 1], [1, 0, 1, 1]], dtype=np.uint8
    )
    check_names = [f"C{i}" for i in range(h_small.shape[0])]
    variable_names = [f"V{i}" for i in range(h_small.shape[1])]
    edges = [
        {"check": check_names[c], "variable": variable_names[v]}
        for c, v in zip(*np.nonzero(h_small))
    ]
    check_adjacency = {
        check_names[c]: [variable_names[v] for v in np.flatnonzero(h_small[c])]
        for c in range(h_small.shape[0])
    }
    variable_adjacency = {
        variable_names[v]: [check_names[c] for c in np.flatnonzero(h_small[:, v])]
        for v in range(h_small.shape[1])
    }
    record = {
        "source": "fpga/verification/small_graph_b18/generate_small_graph_vectors.py",
        "H": h_small.tolist(),
        "check_nodes": check_names,
        "fault_variable_nodes": variable_names,
        "edges": edges,
        "check_to_variable": check_adjacency,
        "variable_to_check": variable_adjacency,
    }
    (OUT_DIR / "small_graph_adjacency.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    lines = ["Check-to-variable adjacency:"]
    lines.extend(f"{node} -> {', '.join(neighbors)}" for node, neighbors in check_adjacency.items())
    lines.append("")
    lines.append("Variable-to-check adjacency:")
    lines.extend(f"{node} -> {', '.join(neighbors)}" for node, neighbors in variable_adjacency.items())
    lines.append("")
    lines.append("Explicit edges:")
    lines.extend(f"{edge['check']} -- {edge['variable']}" for edge in edges)
    (OUT_DIR / "small_graph_adjacency.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(stats: dict[str, object]) -> None:
    checks = stats["nodes"]["checks"]
    faults = stats["nodes"]["faults"]
    incidences = stats["incidences"]["detector_fault"]
    components = stats["connectivity"]
    check_degree = stats["degree_statistics"]["checks"]
    fault_degree = stats["degree_statistics"]["faults"]
    text = f"""# Unpartitioned Tier-2 graph baseline

This folder profiles the canonical gross `[[144,12,12]]` memory-Z circuit-level
decoding graph at `p=0.003`. It performs no partitioning, reordering, Relay-BP
decode, or RTL operation.

Run from the project root with:

```bash
python3 results/graph-partitioning-baseline/run_graph_baseline.py
```

## Baseline summary

- Checks/detectors: {checks:,}
- Fault variables: {faults:,}
- Detector-fault incidences: {incidences:,}
- Connected components: {components['component_count']:,}
- Largest component: {components['largest_component_nodes']:,} total nodes
- Isolated nodes: {components['isolated_nodes_total']:,}
- Check degree: min {check_degree['min']}, max {check_degree['max']}, mean {check_degree['mean']:.6f}, median {check_degree['median']:.1f}
- Fault degree: min {fault_degree['min']}, max {fault_degree['max']}, mean {fault_degree['mean']:.6f}, median {fault_degree['median']:.1f}
- Bipartite density: {stats['sparsity']['bipartite_density']:.12g}
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
"""
    (OUT_DIR / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    package = json.loads((GRAPH_DIR / "package.json").read_text(encoding="utf-8"))
    check_count = int(package["detector_count"])
    fault_count = int(package["fault_count"])
    observable_count = int(package["observable_count"])

    with np.load(GRAPH_DIR / "edge_lists.npz") as data:
        detector_edges = np.asarray(data["detector_edges"], dtype=np.int32)
        observable_edges = np.asarray(data["observable_edges"], dtype=np.int32)
    with np.load(GRAPH_DIR / "faults.npz") as data:
        probabilities = np.asarray(data["probabilities"], dtype=np.float64)
        detector_indptr = np.asarray(data["detector_indptr"], dtype=np.int64)
        detector_indices = np.asarray(data["detector_indices"], dtype=np.int32)
        observable_indptr = np.asarray(data["observable_indptr"], dtype=np.int64)
        observable_indices = np.asarray(data["observable_indices"], dtype=np.int32)
    incidence_fault_ids: list[int] = []
    incidence_probabilities: list[float] = []
    with (GRAPH_DIR / "incidence.csv").open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            incidence_fault_ids.append(int(row["fault_index"]))
            incidence_probabilities.append(float(row["probability"]))

    # This is the same edge-list construction used by the existing Tier-2 baseline.
    h_matrix = matrix_from_edges(detector_edges, check_count, fault_count)
    action_matrix = matrix_from_edges(observable_edges, observable_count, fault_count)

    # Independent reconstruction from the fault-major CSR arrays written by the graph builder.
    csr_detector_edges = edge_array_from_fault_csr(detector_indptr, detector_indices)
    csr_observable_edges = edge_array_from_fault_csr(observable_indptr, observable_indices)
    h_from_fault_records = matrix_from_edges(csr_detector_edges, check_count, fault_count)
    a_from_fault_records = matrix_from_edges(csr_observable_edges, observable_count, fault_count)
    baseline_h, baseline_a, baseline_probabilities = load_existing_baseline_matrices()

    checks = {
        "H_exact": bool((h_matrix != h_from_fault_records).nnz == 0),
        "A_exact": bool((action_matrix != a_from_fault_records).nnz == 0),
        "H_exact_vs_existing_tier2_baseline": bool((h_matrix != baseline_h).nnz == 0),
        "A_exact_vs_existing_tier2_baseline": bool((action_matrix != baseline_a).nnz == 0),
        "detector_fault_incidence_set_exact": bool(
            np.array_equal(canonical_edge_set(detector_edges), canonical_edge_set(csr_detector_edges))
        ),
        "observable_fault_incidence_set_exact": bool(
            np.array_equal(canonical_edge_set(observable_edges), canonical_edge_set(csr_observable_edges))
        ),
        "fault_probability_order_exact": bool(
            incidence_fault_ids == list(range(fault_count))
            and np.array_equal(probabilities, np.asarray(incidence_probabilities, dtype=np.float64))
        ),
        "fault_probability_order_exact_vs_existing_tier2_baseline": bool(
            np.array_equal(probabilities, baseline_probabilities)
        ),
        "node_ids_unchanged": True,
        "permutation_applied": False,
    }
    if not all(value for key, value in checks.items() if key != "permutation_applied"):
        raise RuntimeError(f"Graph invariance failure: {checks}")
    if h_matrix.nnz != len(detector_edges) or action_matrix.nnz != len(observable_edges):
        raise RuntimeError("Duplicate/cancelling edge records prevent exact incidence preservation")

    check_degrees = np.asarray(h_matrix.getnnz(axis=1), dtype=np.int64)
    fault_degrees = np.asarray(h_matrix.getnnz(axis=0), dtype=np.int64)
    isolated_checks = int(np.count_nonzero(check_degrees == 0))
    isolated_faults = int(np.count_nonzero(fault_degrees == 0))

    bipartite_adjacency = sparse.bmat(
        [[None, h_matrix], [h_matrix.transpose(), None]], format="csr", dtype=np.uint8
    )
    component_count, labels = connected_components(bipartite_adjacency, directed=False)
    component_sizes = np.bincount(labels, minlength=component_count)

    stats = {
        "baseline": "unpartitioned",
        "partition_count": None,
        "permutation_applied": False,
        "source": {
            "package": str(GRAPH_DIR.relative_to(PROJECT_ROOT)),
            "tier": package["tier"],
            "code": package["code"],
            "memory_basis": package["memory_basis"],
            "physical_error_probability": package["physical_error_probability"],
        },
        "nodes": {
            "checks": check_count,
            "faults": fault_count,
            "logical_observables": observable_count,
            "bipartite_total": check_count + fault_count,
        },
        "incidences": {
            "detector_fault": int(h_matrix.nnz),
            "observable_fault": int(action_matrix.nnz),
        },
        "degree_statistics": {
            "checks": degree_summary(check_degrees),
            "faults": degree_summary(fault_degrees),
        },
        "degree_histograms": {
            "checks": {str(k): v for k, v in histogram(check_degrees).items()},
            "faults": {str(k): v for k, v in histogram(fault_degrees).items()},
        },
        "connectivity": {
            "component_count": int(component_count),
            "largest_component_nodes": int(component_sizes.max(initial=0)),
            "largest_component_fraction": float(component_sizes.max(initial=0) / (check_count + fault_count)),
            "isolated_check_nodes": isolated_checks,
            "isolated_fault_nodes": isolated_faults,
            "isolated_nodes_total": isolated_checks + isolated_faults,
            "component_size_histogram": {
                str(size): int(count)
                for size, count in zip(*np.unique(component_sizes, return_counts=True))
            },
        },
        "sparsity": {
            "possible_detector_fault_pairs": check_count * fault_count,
            "bipartite_density": float(h_matrix.nnz / (check_count * fault_count)),
            "matrix_sparsity_fraction": float(1.0 - h_matrix.nnz / (check_count * fault_count)),
            "mean_degree_all_bipartite_nodes": float(2 * h_matrix.nnz / (check_count + fault_count)),
        },
        "array_hashes": {
            "detector_edges": sha256_array(detector_edges),
            "observable_edges": sha256_array(observable_edges),
            "fault_probabilities": sha256_array(probabilities),
            "H_indptr": sha256_array(h_matrix.indptr),
            "H_indices": sha256_array(h_matrix.indices),
            "A_indptr": sha256_array(action_matrix.indptr),
            "A_indices": sha256_array(action_matrix.indices),
        },
        "invariance_checks": checks,
    }

    (OUT_DIR / "graph_stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    write_degree_csv(check_degrees, fault_degrees)
    write_small_graph()
    write_readme(stats)
    print(json.dumps({
        "checks": check_count,
        "faults": fault_count,
        "incidences": int(h_matrix.nnz),
        "components": int(component_count),
        "largest_component": int(component_sizes.max(initial=0)),
        "invariance_checks": checks,
    }, indent=2))


if __name__ == "__main__":
    main()

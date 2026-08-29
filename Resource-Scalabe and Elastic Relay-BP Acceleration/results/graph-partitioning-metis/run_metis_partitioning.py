#!/usr/bin/env python3
"""Preflight the reversible METIS experiment and stop if METIS is unavailable.

This entry point deliberately does not substitute another algorithm for METIS.
Partition execution, control assignments, permutations, and selected-run artifacts
will be added only after a METIS-compatible interface is present and audited.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import numpy as np


OUT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = OUT_DIR.parents[1]
GRAPH_DIR = PROJECT_ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
BASELINE_DIR = PROJECT_ROOT / "results/graph-partitioning-baseline"
PYTHON_INTERFACES = ("pymetis", "metis", "networkit", "nxmetis")
METIS_EXECUTABLES = ("gpmetis", "mpmetis", "ndmetis")
EXPECTED = {"checks": 1728, "faults": 67752, "incidences": 391320, "observables": 12}


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def audit_interfaces() -> dict[str, object]:
    python = {
        name: {
            "importable": importlib.util.find_spec(name) is not None,
            "version": package_version(name),
        }
        for name in PYTHON_INTERFACES
    }
    executables = {name: shutil.which(name) for name in METIS_EXECUTABLES}
    available_python = [name for name, record in python.items() if record["importable"]]
    available_executables = [name for name, path in executables.items() if path]
    return {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "python_interfaces": python,
        "metis_executables": executables,
        "available_python_interfaces": available_python,
        "available_metis_executables": available_executables,
        "metis_compatible_interface_available": bool(available_python or available_executables),
        "packages_installed_by_experiment": [],
    }


def graph_preflight() -> dict[str, object]:
    package = json.loads((GRAPH_DIR / "package.json").read_text(encoding="utf-8"))
    with np.load(GRAPH_DIR / "edge_lists.npz") as arrays:
        detector_edges = np.asarray(arrays["detector_edges"], dtype=np.int32)
        observable_edges = np.asarray(arrays["observable_edges"], dtype=np.int32)
    with np.load(GRAPH_DIR / "faults.npz") as arrays:
        probabilities = np.asarray(arrays["probabilities"], dtype=np.float64)

    checks = int(package["detector_count"])
    faults = int(package["fault_count"])
    observables = int(package["observable_count"])
    if detector_edges.ndim != 2 or detector_edges.shape[1] != 2:
        raise RuntimeError("detector_edges must contain [fault_id, detector_id] rows")
    if observable_edges.ndim != 2 or observable_edges.shape[1] != 2:
        raise RuntimeError("observable_edges must contain [fault_id, observable_id] rows")

    sorted_detector_edges = detector_edges[np.lexsort((detector_edges[:, 1], detector_edges[:, 0]))]
    duplicate_detector_edges = int(
        np.count_nonzero(np.all(sorted_detector_edges[1:] == sorted_detector_edges[:-1], axis=1))
    )
    values = {
        "checks": checks,
        "faults": faults,
        "incidences": int(len(detector_edges)),
        "observables": observables,
    }
    validation = {
        "dimensions_match_expected": values == EXPECTED,
        "fault_ids_in_range": bool(np.all((detector_edges[:, 0] >= 0) & (detector_edges[:, 0] < faults))),
        "detector_ids_in_range": bool(np.all((detector_edges[:, 1] >= 0) & (detector_edges[:, 1] < checks))),
        "observable_fault_ids_in_range": bool(
            np.all((observable_edges[:, 0] >= 0) & (observable_edges[:, 0] < faults))
        ),
        "observable_ids_in_range": bool(
            np.all((observable_edges[:, 1] >= 0) & (observable_edges[:, 1] < observables))
        ),
        "probability_shape_exact": probabilities.shape == (faults,),
        "duplicate_detector_fault_incidences": duplicate_detector_edges,
        "no_detector_fault_incidence_duplicates": duplicate_detector_edges == 0,
    }
    if not all(value is True or key == "duplicate_detector_fault_incidences" for key, value in validation.items()):
        raise RuntimeError(f"Canonical graph preflight failed: {validation}")

    check_degrees = np.bincount(detector_edges[:, 1], minlength=checks)
    fault_degrees = np.bincount(detector_edges[:, 0], minlength=faults)
    return {
        "source": str(GRAPH_DIR.relative_to(PROJECT_ROOT)),
        "baseline_artifacts": str(BASELINE_DIR.relative_to(PROJECT_ROOT)),
        "combined_vertex_indexing": {
            "check": "combined_id = detector_id, range 0..1727",
            "fault": "combined_id = 1728 + fault_id, range 1728..69479",
        },
        "dimensions": {
            **values,
            "combined_vertices": checks + faults,
            "undirected_edges": int(len(detector_edges)),
            "observable_fault_incidences": int(len(observable_edges)),
        },
        "balance_targets_k4": {
            "checks_per_partition": checks / 4,
            "faults_per_partition": faults / 4,
            "check_degree_work_per_partition": int(check_degrees.sum()) / 4,
            "fault_degree_work_per_partition": int(fault_degrees.sum()) / 4,
        },
        "conceptual_vertex_weight_channels": {
            "check_indicator": "1 for check vertices, 0 for fault vertices",
            "fault_indicator": "0 for check vertices, 1 for fault vertices",
            "check_degree": "detector-fault degree for checks, 0 for faults",
            "fault_degree": "0 for checks, detector-fault degree for faults",
        },
        "validation": validation,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dependency = audit_interfaces()
    preflight = graph_preflight()
    status = {
        "experiment_status": "blocked_before_partition_execution",
        "reason": "No installed METIS-compatible Python interface or executable was found.",
        "metis_run_count": 0,
        "partition_assignments_created": False,
        "control_assignments_created": False,
        "permutations_created": False,
        "relay_bp_run": False,
        "rtl_modified": False,
        "multi_constraint_support": "not assessable until an interface is available",
    }
    (OUT_DIR / "dependency_report.json").write_text(
        json.dumps({**dependency, **status}, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "graph_preflight.json").write_text(
        json.dumps(preflight, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({**status, "available_interfaces": dependency["available_python_interfaces"]}, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Load the common graph-package contract into the reference decoder."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class GraphPackage:
    h_matrix: np.ndarray
    priors: np.ndarray
    metadata: dict


def validate_graph_package(metadata: dict, rows: list[dict[str, str]], package_path: Path) -> None:
    required_keys = {"tier", "source_graph_hash", "detector_count", "fault_count", "edge_count", "files"}
    missing_keys = sorted(required_keys.difference(metadata))
    if missing_keys:
        raise ValueError(f"Graph package is missing keys: {missing_keys}")
    if not isinstance(metadata["files"], dict) or "incidence" not in metadata["files"]:
        raise ValueError("Graph package must name an incidence file")
    incidence_path = package_path.parent / metadata["files"]["incidence"]
    if not incidence_path.exists():
        raise FileNotFoundError(f"Missing incidence file: {incidence_path}")
    detector_count = int(metadata["detector_count"])
    fault_count = int(metadata["fault_count"])
    edge_count = int(metadata["edge_count"])
    if len(rows) != fault_count:
        raise ValueError(f"Expected {fault_count} fault rows, found {len(rows)}")
    seen_faults: set[int] = set()
    observed_edges = 0
    for row in rows:
        fault_index = int(row["fault_index"])
        if fault_index in seen_faults:
            raise ValueError(f"Duplicate fault index: {fault_index}")
        seen_faults.add(fault_index)
        for detector_text in row["detectors"].split():
            detector = int(detector_text)
            if detector < 0 or detector >= detector_count:
                raise ValueError(f"Detector index out of range: {detector}")
        observed_edges += len(row["detectors"].split())
    if len(seen_faults) != fault_count:
        raise ValueError(f"Expected fault indices 0..{fault_count - 1}")
    if observed_edges != edge_count:
        raise ValueError(f"Expected {edge_count} edges, found {observed_edges}")


def load_graph_package(package_path: Path) -> GraphPackage:
    metadata = json.loads(package_path.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    with (package_path.parent / metadata["files"]["incidence"]).open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    validate_graph_package(metadata, rows, package_path)
    h_matrix = np.zeros((int(metadata["detector_count"]), int(metadata["fault_count"])), dtype=np.uint8)
    priors = np.zeros(int(metadata["fault_count"]), dtype=float)
    for row in rows:
        fault = int(row["fault_index"])
        priors[fault] = float(row["prior"])
        for detector in row["detectors"].split():
            h_matrix[int(detector), fault] = 1
    return GraphPackage(h_matrix=h_matrix, priors=priors, metadata=metadata)

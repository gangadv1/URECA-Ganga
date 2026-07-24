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


def load_graph_package(package_path: Path) -> GraphPackage:
    metadata = json.loads(package_path.read_text(encoding="utf-8"))
    rows: list[dict[str, str]] = []
    with (package_path.parent / metadata["files"]["incidence"]).open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    h_matrix = np.zeros((int(metadata["detector_count"]), int(metadata["fault_count"])), dtype=np.uint8)
    priors = np.zeros(int(metadata["fault_count"]), dtype=float)
    for row in rows:
        fault = int(row["fault_index"])
        priors[fault] = float(row["prior"])
        for detector in row["detectors"].split():
            h_matrix[int(detector), fault] = 1
    return GraphPackage(h_matrix=h_matrix, priors=priors, metadata=metadata)

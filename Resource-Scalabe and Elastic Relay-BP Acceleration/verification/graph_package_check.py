"""Basic structural checks for the Tier-1 gross-code graph package."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
for path in (PROJECT_ROOT / "graphs", PROJECT_ROOT / "reference", PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bb_code import build_matrices, summarize  # noqa: E402
from graph_loader import load_graph_package  # noqa: E402


def load_csv_matrix(path: Path) -> np.ndarray:
    return np.loadtxt(path, delimiter=",", dtype=np.uint8)


def check_gross_code(gross_dir: Path) -> None:
    hx, hz = build_matrices()
    summary = summarize(hx, hz)
    loaded_hx = load_csv_matrix(gross_dir / "hx.csv")
    loaded_hz = load_csv_matrix(gross_dir / "hz.csv")
    loaded_summary = json.loads((gross_dir / "summary.json").read_text(encoding="utf-8"))
    logical_masks = json.loads((gross_dir / "logical_masks.json").read_text(encoding="utf-8"))
    if loaded_summary["hx_shape"] != [72, 144] or loaded_summary["hz_shape"] != [72, 144]:
        raise RuntimeError("Unexpected gross-code matrix shapes")
    if loaded_summary["content_hash"] != summary.content_hash:
        raise RuntimeError("Gross-code summary hash mismatch")
    if not np.array_equal(loaded_hx, hx) or not np.array_equal(loaded_hz, hz):
        raise RuntimeError("Saved gross-code matrices differ from the builder output")
    if logical_masks.get("status") != "placeholder":
        raise RuntimeError("Logical masks should still be scaffold placeholders")


def check_capacity_package(package_dir: Path) -> None:
    package_path = package_dir / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    graph = load_graph_package(package_path)
    incidence_path = package_dir / package["files"]["incidence"]
    with incidence_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    if graph.h_matrix.shape != (package["detector_count"], package["fault_count"]):
        raise RuntimeError("Loaded graph package has the wrong matrix shape")
    if int(package["edge_count"]) != int(graph.h_matrix.sum()):
        raise RuntimeError("Edge count does not match loaded incidence matrix")
    if len(rows) != package["fault_count"]:
        raise RuntimeError("Fault count does not match incidence rows")
    schedule_dir = package_dir / "schedule_pc8_pv8"
    schedule = json.loads((schedule_dir / "schedule.json").read_text(encoding="utf-8"))
    if schedule["edge_count"] != package["edge_count"]:
        raise RuntimeError("Schedule edge count does not match the package")
    if schedule["detector_count"] != package["detector_count"]:
        raise RuntimeError("Schedule detector count does not match the package")
    if schedule["fault_count"] != package["fault_count"]:
        raise RuntimeError("Schedule fault count does not match the package")
    if not (schedule_dir / "schedule.csv").exists() or not (schedule_dir / "gross_code_tier1_graph_pkg.sv").exists():
        raise RuntimeError("Missing generated schedule artifacts")


def check_vectors() -> None:
    vectors_dir = PROJECT_ROOT / "verification" / "vectors"
    manifest = json.loads((vectors_dir / "manifest.json").read_text(encoding="utf-8"))
    for artifact in (vectors_dir / "directed_vectors.csv", vectors_dir / "memory_mix_vectors.svh"):
        if not artifact.exists():
            raise RuntimeError(f"Missing vector artifact: {artifact}")
    if len(manifest.get("provenance", {}).get("artifact_hashes", {})) < 2:
        raise RuntimeError("Vector manifest is missing artifact hashes")


def main() -> None:
    check_gross_code(PROJECT_ROOT / "graphs" / "generated" / "gross_code")
    check_capacity_package(PROJECT_ROOT / "graphs" / "generated" / "gross_code_capacity")
    check_vectors()
    print("Tier-1 graph package checks passed")


if __name__ == "__main__":
    main()
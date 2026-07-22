"""Build a small code-capacity DEM package from the gross code."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
for path in (CURRENT_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bb_code import build_matrices, content_hash, summarize  # noqa: E402
from configs.manifest import ManifestConfig, write_manifest  # noqa: E402


def detector_terms(matrix: np.ndarray, offset: int = 0) -> list[list[int]]:
    terms: list[list[int]] = []
    for col in range(matrix.shape[1]):
        detectors = [int(row + offset) for row in np.flatnonzero(matrix[:, col])]
        terms.append(detectors)
    return terms


def dem_line(probability: float, detectors: list[int]) -> str:
    det_text = " ".join(f"D{detector}" for detector in detectors)
    return f"error({probability:.12g}) {det_text}".rstrip()


def write_dem_package(out_dir: Path, probability: float) -> Path:
    """Write a tier-1 graph package and return the package path."""
    hx, hz = build_matrices()
    summary = summarize(hx, hz)
    out_dir.mkdir(parents=True, exist_ok=True)

    z_faults = detector_terms(hx, offset=0)
    x_faults = detector_terms(hz, offset=hx.shape[0])
    all_faults = [("z", idx, detectors) for idx, detectors in enumerate(z_faults)]
    all_faults += [("x", idx, detectors) for idx, detectors in enumerate(x_faults)]

    dem_path = out_dir / "code_capacity.dem"
    dem_text = "\n".join(dem_line(probability, detectors) for _, _, detectors in all_faults) + "\n"
    dem_path.write_text(dem_text, encoding="utf-8")

    incidence_path = out_dir / "incidence.csv"
    with incidence_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["fault_index", "basis", "qubit", "detectors", "prior"])
        writer.writeheader()
        for fault_index, (basis, qubit, detectors) in enumerate(all_faults):
            writer.writerow(
                {
                    "fault_index": fault_index,
                    "basis": basis,
                    "qubit": qubit,
                    "detectors": " ".join(str(value) for value in detectors),
                    "prior": probability,
                }
            )

    package = {
        "tier": "tier-1-code-capacity",
        "headline_ready": False,
        "note": "This package is for early software and RTL testing only.",
        "loader_contract_version": 1,
        "detector_count": int(hx.shape[0] + hz.shape[0]),
        "fault_count": len(all_faults),
        "edge_count": int(sum(len(detectors) for _, _, detectors in all_faults)),
        "source_graph_hash": content_hash(hx, hz),
        "hx_shape": list(hx.shape),
        "hz_shape": list(hz.shape),
        "files": {
            "dem": dem_path.name,
            "incidence": incidence_path.name,
        },
        "gross_code": asdict(summary),
    }
    package_path = out_dir / "package.json"
    package_path.write_text(json.dumps(package, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    validate_dem(dem_path)
    write_manifest(
        ManifestConfig(
            graph={
                "code": "gross",
                "tier": "tier-1-code-capacity",
                "detector_count": package["detector_count"],
                "fault_count": package["fault_count"],
                "edge_count": package["edge_count"],
                "graph_hash": package["source_graph_hash"],
            },
            circuit={"kind": "code-capacity", "headline_ready": False},
            experiment={"purpose": "early graph package"},
            notes=["Tier-1 dimensions are provisional. Circuit-level artifacts must be regenerated."],
        ),
        out_dir,
        artifact_paths=[dem_path, incidence_path, package_path],
    )
    return package_path


def validate_dem(path: Path) -> None:
    import stim

    stim.DetectorErrorModel(path.read_text(encoding="utf-8"))


def load_package(package_path: Path) -> dict:
    return json.loads(package_path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a tier-1 gross-code DEM package")
    parser.add_argument("--out-dir", type=Path, default=CURRENT_DIR / "generated" / "gross_code_capacity")
    parser.add_argument("--probability", type=float, default=0.001)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    package_path = write_dem_package(args.out_dir, args.probability)
    package = load_package(package_path)
    print(f"Wrote DEM package to {package_path}")
    print(f"Detectors: {package['detector_count']}")
    print(f"Faults: {package['fault_count']}")
    print("Headline ready: no")


if __name__ == "__main__":
    main()


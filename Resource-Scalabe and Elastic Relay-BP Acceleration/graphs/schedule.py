"""Generate a deterministic, conflict-free folded schedule for a graph package.

The schedule is deliberately graph-package based: both software and RTL use
the same detector/fault numbering from ``incidence.csv``.  A slot contains at
most one operation per tile, so single-ported per-tile memories need no
same-cycle arbitration.  This is the tier-1 scheduling contract; regenerate
it when a tier-2 package replaces the graph.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configs.manifest import ManifestConfig, write_manifest  # noqa: E402


def read_incidence(path: Path) -> tuple[int, int, list[tuple[int, int]]]:
    """Return detector count, fault count, and sorted (detector, fault) edges."""
    edges: list[tuple[int, int]] = []
    faults = 0
    detectors: set[int] = set()
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            fault = int(row["fault_index"])
            faults = max(faults, fault + 1)
            for detector in row["detectors"].split():
                detectors.add(int(detector))
                edges.append((int(detector), fault))
    return (max(detectors) + 1 if detectors else 0), faults, sorted(edges)


def schedule_edges(edges: list[tuple[int, int]], p_c: int, p_v: int) -> list[dict[str, int]]:
    """Colour edges into slots without check or variable conflicts.

    Each slot can issue up to ``min(p_c, p_v)`` edges.  Greedy placement is
    deterministic and preserves a stable edge order for Python/RTL traces.
    """
    if p_c < 1 or p_v < 1:
        raise ValueError("p_c and p_v must be positive")
    slots: list[dict[str, object]] = []
    width = min(p_c, p_v)
    for edge_id, (check, variable) in enumerate(edges):
        for slot_id, slot in enumerate(slots):
            ops = slot["ops"]
            assert isinstance(ops, list)
            checks = {op["check"] for op in ops}
            variables = {op["variable"] for op in ops}
            if len(ops) < width and check not in checks and variable not in variables:
                ops.append({"edge": edge_id, "check": check, "variable": variable})
                break
        else:
            slots.append({"ops": [{"edge": edge_id, "check": check, "variable": variable}]})
    rows: list[dict[str, int]] = []
    for slot_id, slot in enumerate(slots):
        for tile, operation in enumerate(slot["ops"]):
            rows.append({"phase_slot": slot_id, "tile": tile, **operation})
    return rows


def write_schedule(package_path: Path, out_dir: Path, p_c: int, p_v: int) -> Path:
    package = json.loads(package_path.read_text(encoding="utf-8"))
    incidence = package_path.parent / package["files"]["incidence"]
    detector_count, fault_count, edges = read_incidence(incidence)
    rows = schedule_edges(edges, p_c, p_v)
    phase_slots = max((row["phase_slot"] for row in rows), default=-1) + 1
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "schedule.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=["phase_slot", "tile", "edge", "check", "variable"])
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schedule_version": 1,
        "graph_tier": package.get("tier"),
        "source_graph_hash": package.get("source_graph_hash"),
        "detector_count": detector_count,
        "fault_count": fault_count,
        "edge_count": len(edges),
        "P_C": p_c,
        "P_V": p_v,
        "parallel_edges_per_slot": min(p_c, p_v),
        "check_phase_cycles": phase_slots,
        "variable_phase_cycles": phase_slots,
        "minimum_cycles_per_iteration": 2 * phase_slots + 2,
        "note": "Tier-1 only; regenerate for circuit-level DEM.",
    }
    summary_path = out_dir / "schedule.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sv_path = out_dir / "gross_code_tier1_graph_pkg.sv"
    check_cases = "\n".join(f"      {index}: check_of_edge = {check};" for index, (check, _) in enumerate(edges))
    variable_cases = "\n".join(f"      {index}: variable_of_edge = {variable};" for index, (_, variable) in enumerate(edges))
    sv_path.write_text(
        "// Generated from incidence.csv; do not hand-edit.\n"
        "package gross_code_tier1_graph_pkg;\n"
        f"  localparam int CHECKS = {detector_count};\n"
        f"  localparam int VARIABLES = {fault_count};\n"
        f"  localparam int EDGES = {len(edges)};\n"
        "  function automatic int check_of_edge(input int index);\n"
        "    case (index)\n"
        f"{check_cases}\n"
        "      default: check_of_edge = 0;\n"
        "    endcase\n  endfunction\n"
        "  function automatic int variable_of_edge(input int index);\n"
        "    case (index)\n"
        f"{variable_cases}\n"
        "      default: variable_of_edge = 0;\n"
        "    endcase\n  endfunction\n"
        "endpackage\n",
        encoding="utf-8",
    )
    write_manifest(
        ManifestConfig(
            graph={"tier": package.get("tier"), "graph_hash": package.get("source_graph_hash"), "edge_count": len(edges)},
            architecture={"P_C": p_c, "P_V": p_v, "schedule_version": 1},
            experiment={"purpose": "conflict-free folded tier-1 schedule"},
            notes=["Regenerate this schedule for a circuit-level graph package."],
        ),
        out_dir,
        [csv_path, summary_path, sv_path],
    )
    return csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a folded graph schedule")
    parser.add_argument("--package", type=Path, default=Path(__file__).parent / "generated/gross_code_capacity/package.json")
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).parent / "generated/gross_code_capacity/schedule_pc8_pv8")
    parser.add_argument("--pc", type=int, default=8)
    parser.add_argument("--pv", type=int, default=8)
    args = parser.parse_args()
    output = write_schedule(args.package, args.out_dir, args.pc, args.pv)
    print(output)


if __name__ == "__main__":
    main()

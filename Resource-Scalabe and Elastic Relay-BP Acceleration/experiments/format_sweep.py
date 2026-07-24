"""Deterministic paired fixed-point format sweep for the tier-1 graph.

This is intentionally an early-screening tool, not a circuit-level headline
experiment.  Each format replays exactly the same deterministic syndrome set.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
for path in (PROJECT_ROOT / "reference", PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from configs.manifest import ManifestConfig, write_manifest  # noqa: E402
from graph_loader import load_graph_package  # noqa: E402
from fixedpoint import FixedConfig  # noqa: E402
from relay_bp_fixed import FixedRelayBPDecoder, FixedRelayConfig, FixedRelayLegConfig  # noqa: E402
from relay_bp_float import FloatRelayBPDecoder  # noqa: E402


def deterministic_cases(checks: int, shots: int, seed: int) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    cases = [np.zeros(checks, dtype=np.uint8)]
    cases.extend(rng.integers(0, 2, size=checks, dtype=np.uint8) for _ in range(shots - 1))
    return cases


def run_sweep(package_path: Path, out_dir: Path, shots: int = 32, seed: int = 20260724) -> Path:
    graph = load_graph_package(package_path)
    cases = deterministic_cases(graph.h_matrix.shape[0], shots, seed)
    prior = np.full(graph.h_matrix.shape[1], 3, dtype=int)
    rows: list[dict[str, int | str]] = []
    float_outcomes = [FloatRelayBPDecoder(graph.h_matrix, max_iterations=3).decode(prior, syndrome) for syndrome in cases]
    rows.append({
        "family": "float_baseline", "b": 0, "g": 0, "M": 0, "separate_scale": 0,
        "shots": shots, "converged": sum(result.converged for result in float_outcomes),
        "mean_iterations_x1000": round(1000 * sum(result.total_iterations for result in float_outcomes) / shots),
    })
    formats = [("high_precision_integer", 16, 16, True)]
    formats += [("shared_scale", b, M, False) for b in (4, 6, 8) for M in (4, 8, 16)]
    formats += [("separate_M", b, M, True) for b in (4, 6, 8) for M in (4, 8, 16)]
    for label, b, M, separate_scale in formats:
        decoder = FixedRelayBPDecoder(
            graph.h_matrix,
            FixedRelayConfig(
                fixed=FixedConfig(b=b, g=3, M=M, clip=(1 << (b - 1)) - 1, separate_scale=separate_scale),
                leg_configs=(FixedRelayLegConfig((0.25, 0.5), carry_gamma=0.25),),
                max_iterations_per_leg=3,
            ),
        )
        outcomes = [decoder.decode(prior, syndrome) for syndrome in cases]
        rows.append({
            "family": label, "b": b, "g": 3, "M": M, "separate_scale": int(separate_scale),
            "shots": shots, "converged": sum(result.converged for result in outcomes),
            "mean_iterations_x1000": round(1000 * sum(result.total_iterations for result in outcomes) / shots),
        })
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "format_sweep.csv"
    with result_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    write_manifest(ManifestConfig(
        graph={"tier": graph.metadata.get("tier"), "graph_hash": graph.metadata.get("source_graph_hash")},
        arithmetic={"b": [4, 6, 8], "M": [4, 8, 16], "g": 3},
        experiment={"purpose": "tier-1 deterministic paired format screening", "shots": shots, "seed": seed},
        notes=["Not a circuit-level or headline accuracy result.", "Float baseline is deterministic but awaits canonical trace lock."],
    ), out_dir, [result_path])
    return result_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the tier-1 fixed-point format sweep")
    parser.add_argument("--package", type=Path, default=PROJECT_ROOT / "graphs/generated/gross_code_capacity/package.json")
    parser.add_argument("--out-dir", type=Path, default=PROJECT_ROOT / "results/format-sweep-tier1")
    parser.add_argument("--shots", type=int, default=32)
    args = parser.parse_args()
    print(run_sweep(args.package, args.out_dir, args.shots))


if __name__ == "__main__":
    main()

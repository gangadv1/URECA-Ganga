"""Run one deterministic Relay-BP decode and print the traceable summary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
for path in (CURRENT_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from configs.manifest import ManifestConfig, write_manifest  # noqa: E402
from graph_loader import load_graph_package  # noqa: E402
from fixedpoint import FixedConfig  # noqa: E402
from relay_bp_fixed import FixedRelayBPDecoder, FixedRelayConfig, FixedRelayLegConfig  # noqa: E402


def run_demo(seed: int, trace_out: Path | None) -> dict[str, object]:
    package_path = PROJECT_ROOT / "graphs" / "generated" / "gross_code_capacity" / "package.json"
    graph = load_graph_package(package_path)
    rng = np.random.default_rng(seed)
    syndrome = rng.integers(0, 2, size=graph.h_matrix.shape[0], dtype=np.uint8)
    prior = rng.integers(-4, 5, size=graph.h_matrix.shape[1], dtype=int)

    config = FixedRelayConfig(
        fixed=FixedConfig(b=4, g=2, M=8, clip=7, separate_scale=True),
        leg_configs=(
            FixedRelayLegConfig((0.25, 0.50, 0.50), carry_gamma=0.25),
            FixedRelayLegConfig((0.10, 0.20, 0.30), carry_gamma=0.50),
        ),
        max_iterations_per_leg=3,
        gamma_scale=16,
    )
    decoder = FixedRelayBPDecoder(graph.h_matrix, config)
    result = decoder.decode(prior, syndrome, trace_path=trace_out)

    summary = {
        "seed": seed,
        "input_syndrome": syndrome.astype(int).tolist(),
        "gamma_schedule": [list(leg.gamma_schedule) for leg in config.leg_configs],
        "relay_legs": result.relay_legs,
        "converged": result.converged,
        "final_candidate": result.decoded_error.astype(int).tolist(),
        "residual": result.final_syndrome.astype(int).tolist(),
        "iteration_count": result.total_iterations,
        "leg_count": result.relay_legs,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic Relay-BP decode demo")
    parser.add_argument("--seed", type=int, default=20260801)
    parser.add_argument("--trace-out", type=Path, default=None)
    args = parser.parse_args()
    summary = run_demo(args.seed, args.trace_out)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.trace_out is not None:
        write_manifest(
            ManifestConfig(
                experiment={"purpose": "Relay-BP decode demo", "seed": args.seed},
                notes=["Deterministic replay demo for the Python golden reference."],
            ),
            args.trace_out.parent,
            artifact_paths=[args.trace_out],
        )


if __name__ == "__main__":
    main()

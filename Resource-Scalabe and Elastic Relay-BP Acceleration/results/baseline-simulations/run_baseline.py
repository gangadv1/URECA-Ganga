"""Small deterministic paired baseline study for the canonical float decoder."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = PROJECT_ROOT / "reference"
sys.path.insert(0, str(REFERENCE_DIR))

from graph_loader import load_graph_package  # noqa: E402
from relay_bp_float import FloatRelayBPDecoder, RelayLegConfig  # noqa: E402


OUT_DIR = Path(__file__).resolve().parent
PACKAGE_PATH = PROJECT_ROOT / "graphs/generated/gross_code_capacity/package.json"
LOGICAL_MASKS_PATH = PROJECT_ROOT / "graphs/generated/gross_code/logical_masks.json"
FLOAT_SOURCE_PATH = REFERENCE_DIR / "relay_bp_float.py"
SHOTS = 64
PHYSICAL_ERROR_RATE = 0.03
SHOT_SEED = 20260807
DECODER_SEED = 91


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=PROJECT_ROOT.parent, text=True).strip()


def decoder_factories(h_matrix: np.ndarray) -> dict[str, FloatRelayBPDecoder]:
    return {
        "standard_bp": FloatRelayBPDecoder(
            h_matrix,
            leg_configs=(RelayLegConfig(max_iterations=80, gamma=0.0),),
            S=1,
            R=1,
            seed=DECODER_SEED,
        ),
        "uniform_mem_bp": FloatRelayBPDecoder(
            h_matrix,
            leg_configs=(RelayLegConfig(max_iterations=80, gamma=0.125),),
            S=1,
            R=1,
            seed=DECODER_SEED,
        ),
        "relay_bp": FloatRelayBPDecoder(
            h_matrix,
            leg_configs=(
                RelayLegConfig(max_iterations=80, gamma=0.125),
                *(RelayLegConfig(max_iterations=60, gamma_range=(-0.24, 0.66)) for _ in range(11)),
            ),
            S=3,
            R=12,
            seed=DECODER_SEED,
        ),
    }


def main() -> None:
    graph = load_graph_package(PACKAGE_PATH)
    h_matrix = graph.h_matrix
    probability = np.full(h_matrix.shape[1], PHYSICAL_ERROR_RATE, dtype=float)
    lambdas = np.log((1.0 - probability) / probability)
    rng = np.random.default_rng(SHOT_SEED)
    errors = (rng.random((SHOTS, h_matrix.shape[1])) < probability).astype(np.uint8)
    syndromes = ((errors @ h_matrix.T) & 1).astype(np.uint8)
    np.savez_compressed(OUT_DIR / "paired_shots.npz", errors=errors, syndromes=syndromes, lambdas=lambdas)

    rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for decoder_name, decoder in decoder_factories(h_matrix).items():
        results = [decoder.decode(lambdas, syndrome) for syndrome in syndromes]
        for shot, result in enumerate(results):
            rows.append(
                {
                    "decoder": decoder_name,
                    "shot": shot,
                    "converged": int(result.converged),
                    "iterations": result.total_iterations,
                    "relay_legs": result.relay_legs,
                    "valid_solutions": result.solutions_found,
                    "selected_solution_weight": "" if not result.converged else result.metadata["best_weight"],
                    "syndrome_weight": int(syndromes[shot].sum()),
                    "sampled_error_weight": int(errors[shot].sum()),
                }
            )
        converged = [result for result in results if result.converged]
        summaries.append(
            {
                "decoder": decoder_name,
                "shots": SHOTS,
                "converged": len(converged),
                "convergence_rate": len(converged) / SHOTS,
                "non_converged": SHOTS - len(converged),
                "non_convergence_rate": (SHOTS - len(converged)) / SHOTS,
                "logical_or_block_error_rate": None,
                "average_iterations": float(np.mean([result.total_iterations for result in results])),
                "average_relay_legs": float(np.mean([result.relay_legs for result in results])),
                "total_valid_solutions": int(sum(result.solutions_found for result in results)),
                "average_valid_solutions": float(np.mean([result.solutions_found for result in results])),
                "average_selected_solution_weight": (
                    float(np.mean([result.metadata["best_weight"] for result in converged])) if converged else None
                ),
            }
        )

    with (OUT_DIR / "per_shot_results.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT_DIR / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")

    logical_masks = json.loads(LOGICAL_MASKS_PATH.read_text(encoding="utf-8"))
    manifest = {
        "study": "small paired canonical-float Relay-BP baseline",
        "headline_ready": False,
        "graph": {
            "code": graph.metadata["gross_code"]["code_name"],
            "tier": graph.metadata["tier"],
            "package": str(PACKAGE_PATH.relative_to(PROJECT_ROOT)),
            "source_graph_hash": graph.metadata["source_graph_hash"],
            "detectors": int(h_matrix.shape[0]),
            "fault_variables": int(h_matrix.shape[1]),
        },
        "noise": {
            "source": "independent Bernoulli code-capacity faults over packaged variables",
            "physical_error_rate": PHYSICAL_ERROR_RATE,
            "decoder_priors": "uniform and matched to physical_error_rate",
        },
        "shots": {"count": SHOTS, "seed": SHOT_SEED, "paired_across_decoders": True},
        "decoder_seed": DECODER_SEED,
        "decoders": {
            "standard_bp": {"S": 1, "R": 1, "legs": [{"max_iterations": 80, "gamma": 0.0}]},
            "uniform_mem_bp": {"S": 1, "R": 1, "legs": [{"max_iterations": 80, "gamma": 0.125}]},
            "relay_bp": {
                "S": 3,
                "R": 12,
                "first_leg": {"max_iterations": 80, "gamma": 0.125},
                "later_legs": {"count": 11, "max_iterations": 60, "gamma_distribution": [-0.24, 0.66]},
            },
        },
        "logical_scoring": {
            "available": bool(logical_masks.get("masks")),
            "status": logical_masks.get("status"),
            "note": logical_masks.get("note"),
        },
        "software": {
            "git_commit": git_output("rev-parse", "HEAD"),
            "git_worktree_dirty": bool(git_output("status", "--porcelain")),
            "canonical_float_source": str(FLOAT_SOURCE_PATH.relative_to(PROJECT_ROOT)),
            "canonical_float_source_sha256": sha256(FLOAT_SOURCE_PATH),
            "numpy_version": np.__version__,
        },
        "artifacts": ["manifest.json", "summary.json", "per_shot_results.csv", "paired_shots.npz", "run_baseline.py"],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()

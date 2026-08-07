"""Small paired Relay-BP behavior ablation using the canonical float path."""

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
BASELINE_DIR = OUT_DIR.parent / "baseline-simulations"
PACKAGE_PATH = PROJECT_ROOT / "graphs/generated/gross_code_capacity/package.json"
LOGICAL_MASKS_PATH = PROJECT_ROOT / "graphs/generated/gross_code/logical_masks.json"
FLOAT_SOURCE_PATH = REFERENCE_DIR / "relay_bp_float.py"
SHOT_SEED = 20260807
GAMMA_SEED = 91
PHYSICAL_ERROR_RATE = 0.03
SHOTS = 64
R = 12


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=PROJECT_ROOT.parent, text=True).strip()


def explicit_legs(gammas: np.ndarray) -> tuple[RelayLegConfig, ...]:
    return (
        RelayLegConfig(max_iterations=80, gamma=0.125),
        *(RelayLegConfig(max_iterations=60, gamma=row) for row in gammas),
    )


def independent_decode(
    h_matrix: np.ndarray,
    lambdas: np.ndarray,
    syndrome: np.ndarray,
    gammas: np.ndarray,
    target_solutions: int = 3,
) -> dict[str, object]:
    """Run canonical one-leg decoders, restarting M(0)=lambda every leg."""
    leg_configs = explicit_legs(gammas)
    total_iterations = 0
    legs_used = 0
    solution_weights: list[float] = []
    best_weight = np.inf
    best_decoding: np.ndarray | None = None
    for leg in leg_configs:
        result = FloatRelayBPDecoder(
            h_matrix,
            leg_configs=(leg,),
            S=1,
            R=1,
            seed=GAMMA_SEED,
        ).decode(lambdas, syndrome)
        legs_used += 1
        total_iterations += result.total_iterations
        if result.converged:
            weight = float(result.metadata["best_weight"])
            solution_weights.append(weight)
            if weight < best_weight:
                best_weight = weight
                best_decoding = result.decoded_error.copy()
            if len(solution_weights) >= target_solutions:
                break
    return {
        "converged": best_decoding is not None,
        "total_iterations": total_iterations,
        "relay_legs": legs_used,
        "solutions_found": len(solution_weights),
        "solution_weights": solution_weights,
        "best_weight": None if best_decoding is None else best_weight,
        "decoded_error": np.zeros(h_matrix.shape[1], dtype=np.uint8) if best_decoding is None else best_decoding,
    }


def canonical_result(result: object) -> dict[str, object]:
    return {
        "converged": result.converged,
        "total_iterations": result.total_iterations,
        "relay_legs": result.relay_legs,
        "solutions_found": result.solutions_found,
        "solution_weights": list(result.solution_weights),
        "best_weight": result.metadata["best_weight"],
        "decoded_error": result.decoded_error.copy(),
    }


def main() -> None:
    graph = load_graph_package(PACKAGE_PATH)
    h_matrix = graph.h_matrix
    paired = np.load(BASELINE_DIR / "paired_shots.npz")
    errors = paired["errors"]
    syndromes = paired["syndromes"]
    lambdas = paired["lambdas"]
    if errors.shape[0] != SHOTS or syndromes.shape[0] != SHOTS:
        raise ValueError("baseline paired-shot artifact does not contain the expected 64 shots")

    # Common U(0,1) values couple the positive-only and paper-interval draws.
    gamma_rng = np.random.default_rng(GAMMA_SEED)
    uniforms = gamma_rng.random((SHOTS, R - 1, h_matrix.shape[1]))
    positive_gammas = 0.66 * uniforms
    paper_gammas = -0.24 + 0.90 * uniforms
    np.savez_compressed(
        OUT_DIR / "paired_inputs.npz",
        errors=errors,
        syndromes=syndromes,
        lambdas=lambdas,
        gamma_uniform_draws=uniforms,
        positive_gammas=positive_gammas,
        paper_gammas=paper_gammas,
    )

    variants: dict[str, list[dict[str, object]]] = {
        name: []
        for name in (
            "standard_bp",
            "uniform_mem_bp",
            "relay_s1_positive_only",
            "relay_s1_paper_interval",
            "relay_s3_paper_interval",
            "independent_s3_paper_interval",
        )
    }
    for shot, syndrome in enumerate(syndromes):
        variants["standard_bp"].append(
            canonical_result(
                FloatRelayBPDecoder(
                    h_matrix,
                    leg_configs=(RelayLegConfig(max_iterations=80, gamma=0.0),),
                    S=1,
                    R=1,
                ).decode(lambdas, syndrome)
            )
        )
        variants["uniform_mem_bp"].append(
            canonical_result(
                FloatRelayBPDecoder(
                    h_matrix,
                    leg_configs=(RelayLegConfig(max_iterations=80, gamma=0.125),),
                    S=1,
                    R=1,
                ).decode(lambdas, syndrome)
            )
        )
        variants["relay_s1_positive_only"].append(
            canonical_result(
                FloatRelayBPDecoder(
                    h_matrix,
                    leg_configs=explicit_legs(positive_gammas[shot]),
                    S=1,
                    R=R,
                ).decode(lambdas, syndrome)
            )
        )
        variants["relay_s1_paper_interval"].append(
            canonical_result(
                FloatRelayBPDecoder(
                    h_matrix,
                    leg_configs=explicit_legs(paper_gammas[shot]),
                    S=1,
                    R=R,
                ).decode(lambdas, syndrome)
            )
        )
        variants["relay_s3_paper_interval"].append(
            canonical_result(
                FloatRelayBPDecoder(
                    h_matrix,
                    leg_configs=explicit_legs(paper_gammas[shot]),
                    S=3,
                    R=R,
                ).decode(lambdas, syndrome)
            )
        )
        variants["independent_s3_paper_interval"].append(
            independent_decode(h_matrix, lambdas, syndrome, paper_gammas[shot], target_solutions=3)
        )

    rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    correction_arrays: dict[str, np.ndarray] = {}
    for name, results in variants.items():
        correction_arrays[name] = np.stack([result["decoded_error"] for result in results])
        converged = [result for result in results if result["converged"]]
        for shot, result in enumerate(results):
            rows.append(
                {
                    "decoder": name,
                    "shot": shot,
                    "converged": int(bool(result["converged"])),
                    "iterations": result["total_iterations"],
                    "legs": result["relay_legs"],
                    "successful_legs": result["solutions_found"],
                    "selected_weight": "" if result["best_weight"] is None else result["best_weight"],
                    "candidate_weights": json.dumps(result["solution_weights"]),
                    "sampled_error_weight": int(errors[shot].sum()),
                    "syndrome_weight": int(syndromes[shot].sum()),
                }
            )
        summaries.append(
            {
                "decoder": name,
                "shots": SHOTS,
                "converged": len(converged),
                "convergence_rate": len(converged) / SHOTS,
                "non_converged": SHOTS - len(converged),
                "non_convergence_rate": (SHOTS - len(converged)) / SHOTS,
                "average_iterations": float(np.mean([result["total_iterations"] for result in results])),
                "average_legs": float(np.mean([result["relay_legs"] for result in results])),
                "successful_legs": int(sum(result["solutions_found"] for result in results)),
                "average_successful_legs": float(np.mean([result["solutions_found"] for result in results])),
                "average_selected_weight": (
                    float(np.mean([result["best_weight"] for result in converged])) if converged else None
                ),
                "logical_error_rate": None,
            }
        )

    np.savez_compressed(OUT_DIR / "selected_corrections.npz", **correction_arrays)
    with (OUT_DIR / "per_shot_results.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT_DIR / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")

    difference_counts: dict[str, int] = {}
    difference_shots: dict[str, list[int]] = {}
    names = list(variants)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            key = f"{left}__vs__{right}"
            different = np.flatnonzero(np.any(correction_arrays[left] != correction_arrays[right], axis=1)).astype(int).tolist()
            difference_counts[key] = len(different)
            difference_shots[key] = different

    focus_pairs = {
        "negative_vs_positive_s1": ("relay_s1_paper_interval", "relay_s1_positive_only"),
        "s3_vs_s1_paper_interval": ("relay_s3_paper_interval", "relay_s1_paper_interval"),
        "relay_vs_independent_s3": ("relay_s3_paper_interval", "independent_s3_paper_interval"),
    }
    focus_details: dict[str, list[dict[str, object]]] = {}
    for label, (left, right) in focus_pairs.items():
        details = []
        for shot in difference_shots[f"{right}__vs__{left}"] if f"{right}__vs__{left}" in difference_shots else difference_shots[f"{left}__vs__{right}"]:
            details.append(
                {
                    "shot": shot,
                    "sampled_error_weight": int(errors[shot].sum()),
                    "syndrome_weight": int(syndromes[shot].sum()),
                    left: {
                        "converged": variants[left][shot]["converged"],
                        "iterations": variants[left][shot]["total_iterations"],
                        "legs": variants[left][shot]["relay_legs"],
                        "weights": variants[left][shot]["solution_weights"],
                        "selected_weight": variants[left][shot]["best_weight"],
                    },
                    right: {
                        "converged": variants[right][shot]["converged"],
                        "iterations": variants[right][shot]["total_iterations"],
                        "legs": variants[right][shot]["relay_legs"],
                        "weights": variants[right][shot]["solution_weights"],
                        "selected_weight": variants[right][shot]["best_weight"],
                    },
                }
            )
        focus_details[label] = details
    difference_analysis = {
        "pairwise_selected_correction_difference_counts": difference_counts,
        "pairwise_selected_correction_difference_shots": difference_shots,
        "focus_details": focus_details,
    }
    (OUT_DIR / "difference_analysis.json").write_text(json.dumps(difference_analysis, indent=2) + "\n", encoding="utf-8")

    logical_masks = json.loads(LOGICAL_MASKS_PATH.read_text(encoding="utf-8"))
    manifest = {
        "study": "small paired canonical-float Relay-BP behavior ablation",
        "headline_ready": False,
        "graph": {
            "code": graph.metadata["gross_code"]["code_name"],
            "tier": graph.metadata["tier"],
            "package": str(PACKAGE_PATH.relative_to(PROJECT_ROOT)),
            "source_graph_hash": graph.metadata["source_graph_hash"],
            "detectors": int(h_matrix.shape[0]),
            "fault_variables": int(h_matrix.shape[1]),
        },
        "paired_inputs": {
            "source": str((BASELINE_DIR / "paired_shots.npz").relative_to(PROJECT_ROOT)),
            "source_sha256": sha256(BASELINE_DIR / "paired_shots.npz"),
            "shots": SHOTS,
            "shot_seed": SHOT_SEED,
            "physical_error_rate": PHYSICAL_ERROR_RATE,
            "noise_source": "independent Bernoulli code-capacity faults over packaged variables",
        },
        "gamma_pairing": {
            "seed": GAMMA_SEED,
            "draws": "one stored U(0,1) tensor per shot/leg/node",
            "positive_mapping": "0.66*u",
            "paper_mapping": "-0.24 + 0.90*u",
            "relay_and_independent_use_identical_paper-interval gamma vectors": True,
        },
        "decoder_parameters": {
            "standard_bp": {"S": 1, "R": 1, "first_max_iterations": 80, "first_gamma": 0.0},
            "uniform_mem_bp": {"S": 1, "R": 1, "first_max_iterations": 80, "first_gamma": 0.125},
            "relay_s1_positive_only": {"S": 1, "R": R, "first": [80, 0.125], "later": [60, [0.0, 0.66]]},
            "relay_s1_paper_interval": {"S": 1, "R": R, "first": [80, 0.125], "later": [60, [-0.24, 0.66]]},
            "relay_s3_paper_interval": {"S": 3, "R": R, "first": [80, 0.125], "later": [60, [-0.24, 0.66]]},
            "independent_s3_paper_interval": {
                "S": 3,
                "R": R,
                "first": [80, 0.125],
                "later": [60, [-0.24, 0.66]],
                "handoff": "restart M(0)=lambda for every leg",
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
            "canonical_float_source_sha256": sha256(FLOAT_SOURCE_PATH),
            "numpy_version": np.__version__,
        },
        "artifacts": [
            "manifest.json",
            "summary.json",
            "per_shot_results.csv",
            "paired_inputs.npz",
            "selected_corrections.npz",
            "difference_analysis.json",
            "run_ablation.py",
        ],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summaries, "focus_difference_counts": {k: len(v) for k, v in focus_details.items()}}, indent=2))


if __name__ == "__main__":
    main()

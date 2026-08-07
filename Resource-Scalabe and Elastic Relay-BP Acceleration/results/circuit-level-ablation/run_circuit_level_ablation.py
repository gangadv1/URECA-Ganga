"""Small paired circuit-level Relay-BP behavior ablation."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy
import stim
from scipy import sparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = PROJECT_ROOT / "reference"
sys.path.insert(0, str(REFERENCE_DIR))

from relay_bp_float import FloatRelayBPDecoder, RelayLegConfig  # noqa: E402


OUT_DIR = Path(__file__).resolve().parent
TIER2_DIR = PROJECT_ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
BASELINE_DIR = PROJECT_ROOT / "results/circuit-level-baseline"
SHOTS = 32
SAMPLE_SEED = 20260808
DECODER_SEED = 91
R = 301
EXPECTED_DIMENSIONS = (1728, 67752, 12)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=PROJECT_ROOT.parent, text=True).strip()


def load_problem() -> tuple[sparse.csr_matrix, sparse.csr_matrix, np.ndarray, np.ndarray, np.ndarray]:
    package = json.loads((TIER2_DIR / "package.json").read_text(encoding="utf-8"))
    dimensions = (package["detector_count"], package["fault_count"], package["observable_count"])
    if dimensions != EXPECTED_DIMENSIONS:
        raise RuntimeError(f"Tier-2 dimensions {dimensions} != {EXPECTED_DIMENSIONS}")
    with np.load(TIER2_DIR / "edge_lists.npz") as data:
        detector_edges = data["detector_edges"]
        observable_edges = data["observable_edges"]
    with np.load(TIER2_DIR / "faults.npz") as data:
        probabilities = data["probabilities"]
    with np.load(BASELINE_DIR / "paired_samples.npz") as data:
        syndromes = data["syndromes"]
        observed_logicals = data["observed_logicals"]
    if syndromes.shape != (SHOTS, dimensions[0]) or observed_logicals.shape != (SHOTS, dimensions[2]):
        raise RuntimeError("Baseline paired sample dimensions differ from the requested ablation")
    h_matrix = sparse.csr_matrix(
        (np.ones(len(detector_edges), dtype=np.uint8), (detector_edges[:, 1], detector_edges[:, 0])),
        shape=dimensions[:2],
    )
    action_matrix = sparse.csr_matrix(
        (np.ones(len(observable_edges), dtype=np.uint8), (observable_edges[:, 1], observable_edges[:, 0])),
        shape=(dimensions[2], dimensions[1]),
    )
    for matrix in (h_matrix, action_matrix):
        matrix.data &= 1
        matrix.eliminate_zeros()
    return h_matrix, action_matrix, probabilities, syndromes, observed_logicals


def make_decoder(name: str, h_matrix: sparse.csr_matrix, seed: int) -> FloatRelayBPDecoder:
    if name == "standard_bp":
        return FloatRelayBPDecoder(
            h_matrix,
            leg_configs=(RelayLegConfig(max_iterations=80, gamma=0.0),),
            S=1,
            R=1,
            seed=seed,
        )
    if name == "uniform_mem_bp":
        return FloatRelayBPDecoder(
            h_matrix,
            leg_configs=(RelayLegConfig(max_iterations=80, gamma=0.125),),
            S=1,
            R=1,
            seed=seed,
        )
    positive_only = name == "relay_s1_positive_only"
    independent = name == "independent_ensemble_s3_paper"
    target_solutions = 1 if name in {"relay_s1_positive_only", "relay_s1_paper"} else 3
    gamma_range = (0.0, 0.66) if positive_only else (-0.24, 0.66)
    legs = (
        RelayLegConfig(max_iterations=80, gamma=0.125),
        *(RelayLegConfig(max_iterations=60, gamma_range=gamma_range) for _ in range(R - 1)),
    )
    return FloatRelayBPDecoder(
        h_matrix,
        leg_configs=legs,
        S=target_solutions,
        R=R,
        seed=seed,
        relay_handoff=not independent,
    )


def main() -> None:
    h_matrix, action_matrix, probabilities, syndromes, observed_logicals = load_problem()
    lambdas = np.log((1.0 - probabilities) / probabilities)
    names = [
        "standard_bp",
        "uniform_mem_bp",
        "relay_s1_positive_only",
        "relay_s1_paper",
        "relay_s3_paper",
        "independent_ensemble_s3_paper",
    ]
    rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    corrections_by_name: dict[str, np.ndarray] = {}
    results_by_name: dict[str, list] = {}

    for name in names:
        results = [
            make_decoder(name, h_matrix, DECODER_SEED + shot).decode(lambdas, syndromes[shot])
            for shot in range(SHOTS)
        ]
        results_by_name[name] = results
        corrections = np.stack([result.decoded_error for result in results])
        corrections_by_name[name] = corrections
        predicted_syndromes = np.asarray((h_matrix @ corrections.T).T, dtype=np.uint8) & 1
        predicted_logicals = np.asarray((action_matrix @ corrections.T).T, dtype=np.uint8) & 1
        syndrome_valid = np.all(predicted_syndromes == syndromes, axis=1)
        logical_match = np.all(predicted_logicals == observed_logicals, axis=1)
        logically_correct = syndrome_valid & logical_match
        for shot, result in enumerate(results):
            gamma_summaries = result.metadata["leg_gamma_summaries"]
            rows.append(
                {
                    "decoder": name,
                    "shot": shot,
                    "decoder_seed": DECODER_SEED + shot,
                    "syndrome_weight": int(syndromes[shot].sum()),
                    "observed_logical_weight": int(observed_logicals[shot].sum()),
                    "syndrome_converged": int(syndrome_valid[shot]),
                    "logical_action_match": int(logical_match[shot]),
                    "logically_correct": int(logically_correct[shot]),
                    "logical_residual_weight": int(np.count_nonzero(predicted_logicals[shot] ^ observed_logicals[shot])),
                    "final_syndrome_residual_weight": int(np.count_nonzero(predicted_syndromes[shot] ^ syndromes[shot])),
                    "iterations": result.total_iterations,
                    "relay_legs": result.relay_legs,
                    "valid_solutions": result.solutions_found,
                    "selected_solution_weight": (
                        "" if result.metadata["best_weight"] is None else float(result.metadata["best_weight"])
                    ),
                    "later_gamma_minimum": (
                        "" if len(gamma_summaries) == 1 else min(item["minimum"] for item in gamma_summaries[1:])
                    ),
                    "later_negative_gamma_count": sum(item["negative_count"] for item in gamma_summaries[1:]),
                }
            )
        converged_count = int(syndrome_valid.sum())
        conditional_errors = int(np.count_nonzero(syndrome_valid & ~logical_match))
        selected_weights = [
            float(result.metadata["best_weight"])
            for result in results
            if result.metadata["best_weight"] is not None
        ]
        summaries.append(
            {
                "decoder": name,
                "shots": SHOTS,
                "syndrome_converged": converged_count,
                "syndrome_convergence_rate": converged_count / SHOTS,
                "non_converged": SHOTS - converged_count,
                "non_convergence_rate": (SHOTS - converged_count) / SHOTS,
                "logically_correct": int(logically_correct.sum()),
                "logical_failure_rate_all_shots": float(np.mean(~logically_correct)),
                "logical_errors_among_converged": conditional_errors,
                "logical_error_rate_given_convergence": conditional_errors / converged_count if converged_count else None,
                "average_iterations": float(np.mean([result.total_iterations for result in results])),
                "maximum_iterations": int(max(result.total_iterations for result in results)),
                "average_relay_legs": float(np.mean([result.relay_legs for result in results])),
                "maximum_relay_legs": int(max(result.relay_legs for result in results)),
                "total_valid_solutions": int(sum(result.solutions_found for result in results)),
                "average_valid_solutions": float(np.mean([result.solutions_found for result in results])),
                "average_selected_solution_weight": float(np.mean(selected_weights)) if selected_weights else None,
                "shots_with_later_legs": [
                    shot for shot, result in enumerate(results) if result.relay_legs > 1
                ],
                "total_negative_gamma_values_sampled": int(
                    sum(
                        item["negative_count"]
                        for result in results
                        for item in result.metadata["leg_gamma_summaries"][1:]
                    )
                ),
            }
        )

    baseline = corrections_by_name["standard_bp"]
    difference_counts = {
        name: int(np.count_nonzero(np.any(corrections != baseline, axis=1)))
        for name, corrections in corrections_by_name.items()
    }
    pairwise_differences = {
        f"{left}__vs__{right}": [
            int(shot)
            for shot in np.flatnonzero(np.any(corrections_by_name[left] != corrections_by_name[right], axis=1))
        ]
        for index, left in enumerate(names)
        for right in names[index + 1 :]
    }
    for summary in summaries:
        summary["shots_correction_differs_from_standard_bp"] = difference_counts[summary["decoder"]]

    with (OUT_DIR / "per_shot_results.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT_DIR / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "difference_analysis.json").write_text(
        json.dumps(
            {
                "baseline": "standard_bp",
                "difference_counts": difference_counts,
                "pairwise_differing_shots": pairwise_differences,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    np.savez_compressed(OUT_DIR / "selected_corrections.npz", **corrections_by_name)

    tier2_manifest = json.loads((TIER2_DIR / "manifest.json").read_text(encoding="utf-8"))
    float_source = REFERENCE_DIR / "relay_bp_float.py"
    manifest = {
        "study": "small paired Tier-2 circuit-level Relay-BP behavior ablation",
        "graph": {
            "code": "gross [[144,12,12]]",
            "memory_basis": "Z",
            "dimensions": {"detectors": 1728, "faults": 67752, "logical_observables": 12},
            "package": str(TIER2_DIR.relative_to(PROJECT_ROOT)),
            "package_manifest_sha256": sha256(TIER2_DIR / "manifest.json"),
            "detector_incidence_sha256": tier2_manifest["graph"]["detector_incidence_sha256"],
            "source_circuit_sha256": tier2_manifest["provenance"]["source_circuit_sha256"],
        },
        "circuit": {"physical_error_rate": 0.003, "noisy_rounds": 12, "memory_basis": "Z"},
        "shots": {
            "count": SHOTS,
            "sample_seed": SAMPLE_SEED,
            "source": str((BASELINE_DIR / "paired_samples.npz").relative_to(PROJECT_ROOT)),
            "source_sha256": sha256(BASELINE_DIR / "paired_samples.npz"),
            "paired_across_all_decoders": True,
        },
        "decoder": {
            "per_shot_seed": "91 + shot_index",
            "R": R,
            "first_leg": {"gamma": 0.125, "max_iterations": 80},
            "later_leg_max_iterations": 60,
            "positive_only_interval": [0.0, 0.66],
            "paper_interval": [-0.24, 0.66],
            "independent_ensemble": "same per-shot/per-leg draws as relay_s3_paper; M(0) resets to lambda",
            "prior": "per-fault DEM LLR log((1-p_j)/p_j)",
        },
        "software": {
            "git_commit": git_output("rev-parse", "HEAD"),
            "git_worktree_dirty": bool(git_output("status", "--porcelain")),
            "canonical_float_source_sha256": sha256(float_source),
            "numpy_version": np.__version__,
            "scipy_version": scipy.__version__,
            "stim_version": stim.__version__,
        },
        "artifacts": [
            "manifest.json",
            "summary.json",
            "per_shot_results.csv",
            "difference_analysis.json",
            "selected_corrections.npz",
            "run_circuit_level_ablation.py",
        ],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()

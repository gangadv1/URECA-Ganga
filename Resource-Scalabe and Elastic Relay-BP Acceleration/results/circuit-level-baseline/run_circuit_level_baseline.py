"""Small paired Tier-2 circuit-level study using the canonical float decoder."""

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
SHOTS = 32
SAMPLE_SEED = 20260808
DECODER_SEED = 91
EXPECTED_DIMENSIONS = (1728, 67752, 12)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=PROJECT_ROOT.parent, text=True).strip()


def build_matrices() -> tuple[sparse.csr_matrix, sparse.csr_matrix, np.ndarray]:
    package = json.loads((TIER2_DIR / "package.json").read_text(encoding="utf-8"))
    detector_count, fault_count, observable_count = EXPECTED_DIMENSIONS
    actual = (package["detector_count"], package["fault_count"], package["observable_count"])
    if actual != EXPECTED_DIMENSIONS:
        raise RuntimeError(f"Tier-2 package dimensions {actual} != {EXPECTED_DIMENSIONS}")

    with np.load(TIER2_DIR / "edge_lists.npz") as edge_data:
        detector_edges = edge_data["detector_edges"]
        observable_edges = edge_data["observable_edges"]
    with np.load(TIER2_DIR / "faults.npz") as fault_data:
        probabilities = fault_data["probabilities"]

    h_matrix = sparse.csr_matrix(
        (np.ones(len(detector_edges), dtype=np.uint8), (detector_edges[:, 1], detector_edges[:, 0])),
        shape=(detector_count, fault_count),
        dtype=np.uint8,
    )
    action_matrix = sparse.csr_matrix(
        (np.ones(len(observable_edges), dtype=np.uint8), (observable_edges[:, 1], observable_edges[:, 0])),
        shape=(observable_count, fault_count),
        dtype=np.uint8,
    )
    for matrix in (h_matrix, action_matrix):
        matrix.data &= 1
        matrix.eliminate_zeros()
    if probabilities.shape != (fault_count,):
        raise RuntimeError(f"Fault probabilities have shape {probabilities.shape}")
    if np.any((probabilities <= 0.0) | (probabilities >= 1.0)):
        raise RuntimeError("Fault probabilities must lie strictly between zero and one")
    return h_matrix, action_matrix, probabilities


def decoders(h_matrix: sparse.csr_matrix) -> dict[str, FloatRelayBPDecoder]:
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
            S=1,
            R=301,
            seed=DECODER_SEED,
        ),
    }


def main() -> None:
    h_matrix, action_matrix, probabilities = build_matrices()
    circuit = stim.Circuit.from_file(str(TIER2_DIR / "circuit.stim"))
    syndromes, observed_logicals = circuit.compile_detector_sampler(seed=SAMPLE_SEED).sample(
        SHOTS, separate_observables=True
    )
    repeat_syndromes, repeat_logicals = circuit.compile_detector_sampler(seed=SAMPLE_SEED).sample(
        SHOTS, separate_observables=True
    )
    if not np.array_equal(syndromes, repeat_syndromes) or not np.array_equal(observed_logicals, repeat_logicals):
        raise RuntimeError("Fixed-seed circuit samples were not reproducible")
    if syndromes.shape != (SHOTS, EXPECTED_DIMENSIONS[0]):
        raise RuntimeError(f"Syndrome sample shape is {syndromes.shape}")
    if observed_logicals.shape != (SHOTS, EXPECTED_DIMENSIONS[2]):
        raise RuntimeError(f"Logical sample shape is {observed_logicals.shape}")

    lambdas = np.log((1.0 - probabilities) / probabilities)
    np.savez_compressed(
        OUT_DIR / "paired_samples.npz",
        syndromes=syndromes,
        observed_logicals=observed_logicals,
        fault_probabilities=probabilities,
        lambdas=lambdas,
    )

    rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    correction_outputs: dict[str, np.ndarray] = {}
    for decoder_name, decoder in decoders(h_matrix).items():
        results = [decoder.decode(lambdas, syndrome) for syndrome in syndromes]
        corrections = np.stack([result.decoded_error for result in results])
        correction_outputs[decoder_name] = corrections
        predicted_syndromes = np.asarray((h_matrix @ corrections.T).T, dtype=np.uint8) & 1
        predicted_logicals = np.asarray((action_matrix @ corrections.T).T, dtype=np.uint8) & 1
        syndrome_valid = np.all(predicted_syndromes == syndromes, axis=1)
        logical_action_match = np.all(predicted_logicals == observed_logicals, axis=1)
        logically_correct = syndrome_valid & logical_action_match
        for shot, result in enumerate(results):
            rows.append(
                {
                    "decoder": decoder_name,
                    "shot": shot,
                    "syndrome_weight": int(syndromes[shot].sum()),
                    "observed_logical_weight": int(observed_logicals[shot].sum()),
                    "syndrome_converged": int(syndrome_valid[shot]),
                    "logical_action_match": int(logical_action_match[shot]),
                    "logically_correct": int(logically_correct[shot]),
                    "predicted_logical_weight": int(predicted_logicals[shot].sum()),
                    "logical_residual_weight": int(np.count_nonzero(predicted_logicals[shot] ^ observed_logicals[shot])),
                    "iterations": result.total_iterations,
                    "relay_legs": result.relay_legs,
                    "valid_solutions": result.solutions_found,
                    "selected_solution_weight": (
                        "" if result.metadata["best_weight"] is None else float(result.metadata["best_weight"])
                    ),
                }
            )
        converged_count = int(syndrome_valid.sum())
        logical_failures = int((~logically_correct).sum())
        converged_logical_errors = int(np.count_nonzero(syndrome_valid & ~logical_action_match))
        selected_weights = [
            float(result.metadata["best_weight"])
            for result in results
            if result.metadata["best_weight"] is not None
        ]
        summaries.append(
            {
                "decoder": decoder_name,
                "shots": SHOTS,
                "syndrome_converged": converged_count,
                "syndrome_convergence_rate": converged_count / SHOTS,
                "non_converged": SHOTS - converged_count,
                "non_convergence_rate": (SHOTS - converged_count) / SHOTS,
                "logically_correct": int(logically_correct.sum()),
                "logical_failures": logical_failures,
                "logical_failure_rate_all_shots": logical_failures / SHOTS,
                "logical_errors_among_converged": converged_logical_errors,
                "logical_error_rate_given_convergence": (
                    converged_logical_errors / converged_count if converged_count else None
                ),
                "average_iterations": float(np.mean([result.total_iterations for result in results])),
                "average_relay_legs": float(np.mean([result.relay_legs for result in results])),
                "total_valid_solutions": int(sum(result.solutions_found for result in results)),
                "average_valid_solutions": float(np.mean([result.solutions_found for result in results])),
                "average_selected_solution_weight": float(np.mean(selected_weights)) if selected_weights else None,
            }
        )

    with (OUT_DIR / "per_shot_results.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT_DIR / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    np.savez_compressed(OUT_DIR / "selected_corrections.npz", **correction_outputs)

    tier2_manifest = json.loads((TIER2_DIR / "manifest.json").read_text(encoding="utf-8"))
    float_source = REFERENCE_DIR / "relay_bp_float.py"
    manifest = {
        "study": "small paired Tier-2 canonical-float Relay-BP baseline",
        "graph": {
            "code": "gross [[144,12,12]]",
            "tier": "tier-2-circuit-level",
            "memory_basis": "Z",
            "detectors": h_matrix.shape[0],
            "fault_variables": h_matrix.shape[1],
            "logical_observables": action_matrix.shape[0],
            "detector_edges": h_matrix.nnz,
            "logical_edges": action_matrix.nnz,
            "package": str(TIER2_DIR.relative_to(PROJECT_ROOT)),
            "package_manifest_sha256": sha256(TIER2_DIR / "manifest.json"),
            "detector_incidence_sha256": tier2_manifest["graph"]["detector_incidence_sha256"],
            "source_circuit_sha256": tier2_manifest["provenance"]["source_circuit_sha256"],
        },
        "circuit": {
            "noisy_rounds": 12,
            "final_perfect_measurement": tier2_manifest["circuit"]["final_perfect_measurement"],
            "physical_error_rate": 0.003,
            "noise_source": "direct samples from the packaged STIM circuit",
        },
        "shots": {"count": SHOTS, "seed": SAMPLE_SEED, "paired_across_decoders": True},
        "decoder": {
            "prior": "per-fault DEM LLR log((1-p_j)/p_j)",
            "seed": DECODER_SEED,
            "standard_bp": {"S": 1, "R": 1, "legs": [{"max_iterations": 80, "gamma": 0.0}]},
            "uniform_mem_bp": {"S": 1, "R": 1, "legs": [{"max_iterations": 80, "gamma": 0.125}]},
            "relay_bp": {
                "S": 1,
                "R": 301,
                "first_leg": {"max_iterations": 80, "gamma": 0.125},
                "later_legs": {"max_iterations": 60, "per_node_gamma_uniform": [-0.24, 0.66]},
            },
            "syndrome_criterion": "H @ e_hat mod 2 == detector sample",
            "logical_criterion": "A @ e_hat mod 2 == observed logical outcome",
        },
        "software": {
            "git_commit": git_output("rev-parse", "HEAD"),
            "git_worktree_dirty": bool(git_output("status", "--porcelain")),
            "canonical_float_source": str(float_source.relative_to(PROJECT_ROOT)),
            "canonical_float_source_sha256": sha256(float_source),
            "numpy_version": np.__version__,
            "scipy_version": scipy.__version__,
            "stim_version": stim.__version__,
        },
        "artifacts": [
            "manifest.json",
            "summary.json",
            "per_shot_results.csv",
            "paired_samples.npz",
            "selected_corrections.npz",
            "run_circuit_level_baseline.py",
        ],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()

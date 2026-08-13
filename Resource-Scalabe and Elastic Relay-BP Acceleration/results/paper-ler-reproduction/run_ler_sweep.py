"""Deterministic multi-p Tier-2 screening sweep with canonical float Relay-BP-1."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import scipy
import stim
from scipy import sparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = PROJECT_ROOT / "reference"
sys.path.insert(0, str(REFERENCE_DIR))

from relay_bp_float import FloatRelayBPDecoder  # noqa: E402


OUT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = PROJECT_ROOT / "graphs/generated/gross_circuit_level"
P_VALUES = (0.001, 0.002, 0.003, 0.004, 0.005)
SHOTS = 256
SAMPLE_SEEDS = {p: 2026081000 + index for index, p in enumerate(P_VALUES, start=1)}
DECODER_SEED = 250601779
EXPECTED_DIMENSIONS = (1728, 67752, 12)
UPSTREAM_COMMIT = "d185194ba0cb4101ced4340d82b2ee6d42f225f0"


def probability_tag(probability: float) -> str:
    return format(probability, ".12g").replace(".", "p")


def package_path(probability: float) -> Path:
    return PACKAGE_ROOT / f"memory_Z_r12_p{probability_tag(probability)}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_output(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], cwd=PROJECT_ROOT.parent, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def wilson_interval(failures: int, shots: int, z: float = 1.959963984540054) -> tuple[float, float]:
    estimate = failures / shots
    denominator = 1.0 + z * z / shots
    center = (estimate + z * z / (2.0 * shots)) / denominator
    radius = z * math.sqrt(estimate * (1.0 - estimate) / shots + z * z / (4.0 * shots * shots)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def load_package(probability: float) -> tuple[Path, sparse.csr_matrix, sparse.csr_matrix, np.ndarray, stim.Circuit]:
    package_dir = package_path(probability)
    package = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
    dimensions = (package["detector_count"], package["fault_count"], package["observable_count"])
    if dimensions != EXPECTED_DIMENSIONS:
        raise RuntimeError(f"p={probability}: package dimensions {dimensions} != {EXPECTED_DIMENSIONS}")
    if package["memory_basis"] != "Z" or package["noisy_rounds"] != 12:
        raise RuntimeError(f"p={probability}: package is not memory-Z with 12 noisy rounds")
    if not package["final_perfect_measurement"]:
        raise RuntimeError(f"p={probability}: final perfect measurement is absent")
    if not math.isclose(package["physical_error_probability"], probability, rel_tol=0.0, abs_tol=1e-15):
        raise RuntimeError(f"p={probability}: package probability mismatch")
    if manifest["provenance"]["upstream_commit"] != UPSTREAM_COMMIT:
        raise RuntimeError(f"p={probability}: upstream commit mismatch")

    with np.load(package_dir / "edge_lists.npz") as edges:
        detector_edges = edges["detector_edges"]
        observable_edges = edges["observable_edges"]
    with np.load(package_dir / "faults.npz") as faults:
        probabilities = faults["probabilities"]
    detector_count, fault_count, observable_count = EXPECTED_DIMENSIONS
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
    if probabilities.shape != (fault_count,) or np.any((probabilities <= 0.0) | (probabilities >= 0.5)):
        raise RuntimeError(f"p={probability}: invalid DEM fault probabilities")
    circuit = stim.Circuit.from_file(str(package_dir / "circuit.stim"))
    return package_dir, h_matrix, action_matrix, probabilities, circuit


def run_probability(probability: float) -> tuple[dict[str, object], list[dict[str, object]]]:
    package_dir, h_matrix, action_matrix, probabilities, circuit = load_package(probability)
    sample_seed = SAMPLE_SEEDS[probability]
    sampler = circuit.compile_detector_sampler(seed=sample_seed)
    syndromes, observed_logicals = sampler.sample(SHOTS, separate_observables=True)
    repeat_sampler = circuit.compile_detector_sampler(seed=sample_seed)
    repeat_syndromes, repeat_logicals = repeat_sampler.sample(SHOTS, separate_observables=True)
    if not np.array_equal(syndromes, repeat_syndromes) or not np.array_equal(observed_logicals, repeat_logicals):
        raise RuntimeError(f"p={probability}: fixed-seed circuit sampling is not reproducible")
    if syndromes.shape != (SHOTS, EXPECTED_DIMENSIONS[0]) or observed_logicals.shape != (SHOTS, EXPECTED_DIMENSIONS[2]):
        raise RuntimeError(f"p={probability}: unexpected sample dimensions")

    lambdas = np.log((1.0 - probabilities) / probabilities)
    decoder = FloatRelayBPDecoder(h_matrix, S=1, R=301, seed=DECODER_SEED)
    rows: list[dict[str, object]] = []
    for shot in range(SHOTS):
        result = decoder.decode(lambdas, syndromes[shot])
        correction = result.decoded_error
        predicted_syndrome = np.asarray(h_matrix @ correction).reshape(-1).astype(np.uint8) & 1
        predicted_logical = np.asarray(action_matrix @ correction).reshape(-1).astype(np.uint8) & 1
        syndrome_valid = bool(np.array_equal(predicted_syndrome, syndromes[shot]))
        logical_action_match = bool(np.array_equal(predicted_logical, observed_logicals[shot]))
        logically_correct = syndrome_valid and logical_action_match
        rows.append(
            {
                "p": probability,
                "shot": shot,
                "sample_seed": sample_seed,
                "decoder_seed": DECODER_SEED,
                "syndrome_weight": int(np.count_nonzero(syndromes[shot])),
                "observed_logical_weight": int(np.count_nonzero(observed_logicals[shot])),
                "syndrome_converged": int(syndrome_valid),
                "logical_action_match": int(logical_action_match),
                "logically_correct": int(logically_correct),
                "syndrome_valid_logical_error": int(syndrome_valid and not logical_action_match),
                "non_converged": int(not syndrome_valid),
                "logical_residual_weight": int(np.count_nonzero(predicted_logical ^ observed_logicals[shot])),
                "iterations": result.total_iterations,
                "relay_legs": result.relay_legs,
                "valid_solutions": result.solutions_found,
                "selected_solution_weight": (
                    "" if result.metadata["best_weight"] is None else float(result.metadata["best_weight"])
                ),
            }
        )

    failures = sum(1 - int(row["logically_correct"]) for row in rows)
    converged = sum(int(row["syndrome_converged"]) for row in rows)
    logical_successes = sum(int(row["logically_correct"]) for row in rows)
    syndrome_valid_logical_errors = sum(int(row["syndrome_valid_logical_error"]) for row in rows)
    non_convergence = SHOTS - converged
    ler = failures / SHOTS
    ci_low, ci_high = wilson_interval(failures, SHOTS)
    summary = {
        "p": probability,
        "package": str(package_dir.relative_to(PROJECT_ROOT)),
        "shots": SHOTS,
        "sample_seed": sample_seed,
        "decoder_seed": DECODER_SEED,
        "syndrome_converged_shots": converged,
        "syndrome_convergence_rate": converged / SHOTS,
        "logical_successes": logical_successes,
        "logical_failures": failures,
        "syndrome_valid_logical_errors": syndrome_valid_logical_errors,
        "non_convergence": non_convergence,
        "non_convergence_rate": non_convergence / SHOTS,
        "logical_error_rate": ler,
        "logical_error_rate_over_p": ler / probability,
        "ler_wilson_95_low": ci_low,
        "ler_wilson_95_high": ci_high,
        "average_iterations": float(np.mean([row["iterations"] for row in rows])),
        "average_relay_legs": float(np.mean([row["relay_legs"] for row in rows])),
        "average_valid_solutions": float(np.mean([row["valid_solutions"] for row in rows])),
        "failure_statistics_sufficient": failures >= 10,
        "package_manifest_sha256": sha256(package_dir / "manifest.json"),
        "detector_incidence_sha256": sha256(package_dir / "edge_lists.npz"),
    }
    return summary, rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=len(P_VALUES)) as executor:
        futures = {executor.submit(run_probability, probability): probability for probability in P_VALUES}
        for future in as_completed(futures):
            summary, probability_rows = future.result()
            summaries.append(summary)
            rows.extend(probability_rows)
            print(
                f"completed p={summary['p']}: failures={summary['logical_failures']}/{summary['shots']}, "
                f"converged={summary['syndrome_converged_shots']}",
                flush=True,
            )
    summaries.sort(key=lambda row: float(row["p"]))
    rows.sort(key=lambda row: (float(row["p"]), int(row["shot"])))

    (OUT_DIR / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    with (OUT_DIR / "per_p_summary.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    with (OUT_DIR / "per_shot_results.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    manifest = {
        "study": "canonical float Relay-BP-1 multi-p gross-code LER screening",
        "code": "gross [[144,12,12]]",
        "decoding_mode": "XYZ using full detector/fault and fault/observable incidence",
        "circuit": {"memory_basis": "Z", "noisy_rounds": 12, "final_perfect_measurement": True},
        "probabilities": list(P_VALUES),
        "shots_per_probability": SHOTS,
        "sample_seeds": {format(p, ".3f"): SAMPLE_SEEDS[p] for p in P_VALUES},
        "decoder": {
            "implementation": "reference/relay_bp_float.py",
            "S": 1,
            "R": 301,
            "first_leg": {"gamma": 0.125, "max_iterations": 80},
            "later_legs": {"gamma_interval": [-0.24, 0.66], "max_iterations": 60},
            "rng": "persistent NumPy Generator per p, sequential decode calls",
            "seed": DECODER_SEED,
            "prior": "log((1-p_j)/p_j) from each package's DEM fault probabilities",
        },
        "scoring": {
            "syndrome_convergence": "H @ e_hat mod 2 equals sampled detector syndrome",
            "logical_correctness": "syndrome convergence and A @ e_hat mod 2 equals sampled logical outcome",
            "ler": "logical failures / circuit shots; non-convergence counts as logical failure",
            "uncertainty": "two-sided 95% Wilson score interval",
            "sufficient_failure_threshold": 10,
        },
        "dimensions": {"detectors": 1728, "faults": 67752, "logical_observables": 12},
        "upstream_commit": UPSTREAM_COMMIT,
        "package_manifests": {
            format(p, ".3f"): sha256(package_path(p) / "manifest.json") for p in P_VALUES
        },
        "software": {
            "project_git_commit": git_output("rev-parse", "HEAD"),
            "canonical_float_sha256": sha256(REFERENCE_DIR / "relay_bp_float.py"),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "stim": stim.__version__,
        },
        "artifacts": ["summary.json", "per_p_summary.csv", "per_shot_results.csv", "manifest.json"],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()

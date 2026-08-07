"""Multi-seed validation of shortlisted Tier-2 Relay-BP configurations."""

from __future__ import annotations

import csv
import hashlib
import json
import os
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

from relay_bp_float import FloatRelayBPDecoder, RelayLegConfig  # noqa: E402


OUT_DIR = Path(__file__).resolve().parent
TIER2_DIR = PROJECT_ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
SHOTS = 128
SAMPLE_SEEDS = (20260809, 20260810, 20260811, 20260812, 20260813)
DECODER_SEED = 9100
EXPECTED_DIMENSIONS = (1728, 67752, 12)
CONFIGS = {
    "low_latency": {"first_gamma": 0.25, "interval": (0.0, 0.66), "S": 1, "R": 4},
    "balanced": {"first_gamma": 0.25, "interval": (-0.12, 0.54), "S": 1, "R": 16},
    "high_success": {"first_gamma": 0.125, "interval": (-0.12, 0.54), "S": 1, "R": 32},
    "rescue_efficiency": {"first_gamma": 0.125, "interval": (0.0, 0.66), "S": 1, "R": 4},
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=PROJECT_ROOT.parent, text=True).strip()


def load_matrices() -> tuple[sparse.csr_matrix, sparse.csr_matrix, np.ndarray]:
    with np.load(TIER2_DIR / "edge_lists.npz") as data:
        detector_edges = data["detector_edges"]
        observable_edges = data["observable_edges"]
    with np.load(TIER2_DIR / "faults.npz") as data:
        probabilities = data["probabilities"]
    h = sparse.csr_matrix(
        (np.ones(len(detector_edges), dtype=np.uint8), (detector_edges[:, 1], detector_edges[:, 0])),
        shape=EXPECTED_DIMENSIONS[:2],
    )
    action = sparse.csr_matrix(
        (np.ones(len(observable_edges), dtype=np.uint8), (observable_edges[:, 1], observable_edges[:, 0])),
        shape=(EXPECTED_DIMENSIONS[2], EXPECTED_DIMENSIONS[1]),
    )
    for matrix in (h, action):
        matrix.data &= 1
        matrix.eliminate_zeros()
    return h, action, probabilities


def make_decoder(name: str, h: sparse.csr_matrix, shot: int) -> FloatRelayBPDecoder:
    config = CONFIGS[name]
    legs = (
        RelayLegConfig(max_iterations=80, gamma=config["first_gamma"]),
        *(
            RelayLegConfig(max_iterations=60, gamma_range=config["interval"])
            for _ in range(config["R"] - 1)
        ),
    )
    return FloatRelayBPDecoder(
        h,
        leg_configs=legs,
        S=config["S"],
        R=config["R"],
        seed=DECODER_SEED + shot,
    )


def run_config_seed(name: str, seed_index: int, sample_seed: int) -> list[dict[str, object]]:
    h, action, probabilities = load_matrices()
    with np.load(OUT_DIR / "paired_samples.npz") as data:
        syndromes = data["syndromes"][seed_index]
        observed_logicals = data["observed_logicals"][seed_index]
    lambdas = np.log((1.0 - probabilities) / probabilities)
    rows: list[dict[str, object]] = []
    for shot in range(SHOTS):
        result = make_decoder(name, h, shot).decode(lambdas, syndromes[shot])
        decision = result.decoded_error
        predicted_syndrome = np.asarray(h @ decision, dtype=np.uint8).reshape(-1) & 1
        predicted_logical = np.asarray(action @ decision, dtype=np.uint8).reshape(-1) & 1
        syndrome_valid = bool(np.array_equal(predicted_syndrome, syndromes[shot]))
        logical_match = bool(np.array_equal(predicted_logical, observed_logicals[shot]))
        rows.append(
            {
                "configuration": name,
                "sample_seed": sample_seed,
                "shot": shot,
                "syndrome_converged": int(syndrome_valid),
                "logical_action_match": int(logical_match),
                "logically_correct": int(syndrome_valid and logical_match),
                "iterations": result.total_iterations,
                "relay_legs": result.relay_legs,
                "rescued_beyond_first_leg": int(result.converged and result.relay_legs > 1),
                "valid_solutions": result.solutions_found,
                "selected_solution_weight": (
                    "" if result.metadata["best_weight"] is None else float(result.metadata["best_weight"])
                ),
            }
        )
    return rows


def per_seed_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, int], list[dict[str, object]]] = {}
    for row in rows:
        groups.setdefault((str(row["configuration"]), int(row["sample_seed"])), []).append(row)
    output: list[dict[str, object]] = []
    for (name, seed), group in sorted(groups.items()):
        iterations = np.asarray([int(row["iterations"]) for row in group])
        legs = np.asarray([int(row["relay_legs"]) for row in group])
        converged = sum(int(row["syndrome_converged"]) for row in group)
        correct = sum(int(row["logically_correct"]) for row in group)
        weights = [float(row["selected_solution_weight"]) for row in group if row["selected_solution_weight"] != ""]
        output.append(
            {
                "configuration": name,
                "sample_seed": seed,
                "shots": len(group),
                "syndrome_converged": converged,
                "syndrome_convergence_rate": converged / len(group),
                "logical_successes": correct,
                "logical_success_rate": correct / len(group),
                "logical_failures": len(group) - correct,
                "logical_failure_rate": (len(group) - correct) / len(group),
                "average_iterations": float(np.mean(iterations)),
                "p50_iterations": float(np.percentile(iterations, 50)),
                "p90_iterations": float(np.percentile(iterations, 90)),
                "p99_iterations": float(np.percentile(iterations, 99)),
                "maximum_iterations": int(np.max(iterations)),
                "average_relay_legs": float(np.mean(legs)),
                "maximum_relay_legs": int(np.max(legs)),
                "rescued_shots_beyond_first_leg": sum(int(row["rescued_beyond_first_leg"]) for row in group),
                "average_selected_solution_weight": float(np.mean(weights)) if weights else None,
            }
        )
    return output


def aggregate(per_seed: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for name in CONFIGS:
        group = [row for row in per_seed if row["configuration"] == name]
        success = np.asarray([row["logical_success_rate"] for row in group], dtype=float)
        syndrome_success = np.asarray([row["syndrome_convergence_rate"] for row in group], dtype=float)
        iterations = np.asarray([row["average_iterations"] for row in group], dtype=float)
        p99 = np.asarray([row["p99_iterations"] for row in group], dtype=float)
        output.append(
            {
                "configuration": name,
                "seeds": len(group),
                "total_shots": len(group) * SHOTS,
                "total_logical_successes": int(sum(row["logical_successes"] for row in group)),
                "total_syndrome_converged": int(sum(row["syndrome_converged"] for row in group)),
                "logical_errors_among_syndrome_converged": int(
                    sum(row["syndrome_converged"] - row["logical_successes"] for row in group)
                ),
                "mean_syndrome_convergence_rate": float(np.mean(syndrome_success)),
                "std_syndrome_convergence_rate_across_seeds": float(np.std(syndrome_success, ddof=1)),
                "mean_logical_success_rate": float(np.mean(success)),
                "std_logical_success_rate_across_seeds": float(np.std(success, ddof=1)),
                "min_logical_success_rate": float(np.min(success)),
                "max_logical_success_rate": float(np.max(success)),
                "mean_average_iterations": float(np.mean(iterations)),
                "std_average_iterations_across_seeds": float(np.std(iterations, ddof=1)),
                "min_average_iterations": float(np.min(iterations)),
                "max_average_iterations": float(np.max(iterations)),
                "mean_p99_iterations": float(np.mean(p99)),
                "worst_observed_iterations": int(max(row["maximum_iterations"] for row in group)),
                "mean_average_relay_legs": float(np.mean([row["average_relay_legs"] for row in group])),
                "maximum_relay_legs": int(max(row["maximum_relay_legs"] for row in group)),
                "total_rescued_shots_beyond_first_leg": int(
                    sum(row["rescued_shots_beyond_first_leg"] for row in group)
                ),
                "mean_selected_solution_weight": float(
                    np.mean([row["average_selected_solution_weight"] for row in group])
                ),
            }
        )
    return output


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if os.environ.get("RELAY_MULTI_SEED_SUMMARY_ONLY") == "1":
        with (OUT_DIR / "per_shot_results.csv").open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source))
        seed_summaries = per_seed_summary(rows)
        aggregates = aggregate(seed_summaries)
        (OUT_DIR / "per_seed_summary.json").write_text(
            json.dumps(seed_summaries, indent=2) + "\n", encoding="utf-8"
        )
        (OUT_DIR / "aggregate_summary.json").write_text(
            json.dumps(aggregates, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(aggregates, indent=2))
        return
    _, _, probabilities = load_matrices()
    circuit = stim.Circuit.from_file(str(TIER2_DIR / "circuit.stim"))
    syndrome_sets = []
    logical_sets = []
    for seed in SAMPLE_SEEDS:
        sampler = circuit.compile_detector_sampler(seed=seed)
        syndromes, logicals = sampler.sample(SHOTS, separate_observables=True)
        repeat = circuit.compile_detector_sampler(seed=seed).sample(SHOTS, separate_observables=True)
        if not np.array_equal(syndromes, repeat[0]) or not np.array_equal(logicals, repeat[1]):
            raise RuntimeError(f"Circuit sampling is not reproducible for seed {seed}")
        syndrome_sets.append(syndromes)
        logical_sets.append(logicals)
    np.savez_compressed(
        OUT_DIR / "paired_samples.npz",
        syndromes=np.stack(syndrome_sets),
        observed_logicals=np.stack(logical_sets),
        probabilities=probabilities,
        sample_seeds=np.asarray(SAMPLE_SEEDS),
    )

    rows: list[dict[str, object]] = []
    tasks = [(name, index, seed) for name in CONFIGS for index, seed in enumerate(SAMPLE_SEEDS)]
    with ProcessPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(run_config_seed, *task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            rows.extend(future.result())
            print(f"completed configuration={task[0]} sample_seed={task[2]}", flush=True)
    rows.sort(key=lambda row: (row["configuration"], row["sample_seed"], row["shot"]))
    seed_summaries = per_seed_summary(rows)
    aggregates = aggregate(seed_summaries)

    with (OUT_DIR / "per_shot_results.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT_DIR / "per_seed_summary.json").write_text(json.dumps(seed_summaries, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "aggregate_summary.json").write_text(json.dumps(aggregates, indent=2) + "\n", encoding="utf-8")

    tier2_manifest = json.loads((TIER2_DIR / "manifest.json").read_text(encoding="utf-8"))
    manifest = {
        "study": "multi-seed validation of shortlisted circuit-level Relay-BP configurations",
        "graph": {
            "package": str(TIER2_DIR.relative_to(PROJECT_ROOT)),
            "dimensions": {"detectors": 1728, "faults": 67752, "logical_observables": 12},
            "package_manifest_sha256": sha256(TIER2_DIR / "manifest.json"),
            "detector_incidence_sha256": tier2_manifest["graph"]["detector_incidence_sha256"],
        },
        "circuit": {"code": "gross [[144,12,12]]", "memory_basis": "Z", "p": 0.003, "rounds": 12},
        "sampling": {
            "sample_seeds": list(SAMPLE_SEEDS),
            "shots_per_seed": SHOTS,
            "total_unique_circuit_shots": len(SAMPLE_SEEDS) * SHOTS,
            "paired_across_configurations": True,
        },
        "decoder": {
            "configs": CONFIGS,
            "decoder_seed_per_shot": "9100 + shot_index, held constant across circuit-sample seeds",
            "physical_prior": "per-fault DEM LLR log((1-p_j)/p_j)",
        },
        "software": {
            "git_commit": git_output("rev-parse", "HEAD"),
            "git_worktree_dirty": bool(git_output("status", "--porcelain")),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "stim": stim.__version__,
            "float_decoder_sha256": sha256(REFERENCE_DIR / "relay_bp_float.py"),
        },
        "artifacts": [
            "manifest.json",
            "paired_samples.npz",
            "per_shot_results.csv",
            "per_seed_summary.json",
            "aggregate_summary.json",
            "run_multiseed_validation.py",
        ],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()

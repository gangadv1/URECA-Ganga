"""First paired Tier-2 circuit-level Relay-BP parameter sweep."""

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
SAMPLE_SEED = 20260809
DECODER_SEED = 9100
FIRST_GAMMAS = (0.0, 0.125, 0.25)
INTERVALS = ((0.0, 0.66), (-0.12, 0.54), (-0.24, 0.66))
S_VALUES = (1, 3)
R_VALUES = (4, 8, 16, 32)
EXPECTED_DIMENSIONS = (1728, 67752, 12)


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


def one_trajectory(
    decoder: FloatRelayBPDecoder,
    lambdas: np.ndarray,
    syndrome: np.ndarray,
    first_gamma: float,
    interval: tuple[float, float],
) -> dict[str, object]:
    variables = decoder.h_matrix.shape[1]
    initial_marginals = lambdas.copy()
    cumulative_iterations = 0
    leg_iterations: list[int] = []
    candidates: list[tuple[int, float, np.ndarray]] = []
    checkpoint_decisions: dict[int, np.ndarray] = {}
    last_decision = decoder._hard_decision(lambdas)

    configs = [RelayLegConfig(max_iterations=80, gamma=first_gamma)] + [
        RelayLegConfig(max_iterations=60, gamma_range=interval) for _ in range(31)
    ]
    for leg_index, config in enumerate(configs):
        gamma = decoder._gamma_vector(config, decoder._rng)
        nu_previous = lambdas[decoder._edge_variables].copy()
        marginals_previous = initial_marginals.copy()
        iterations_this_leg = 0
        converged = False
        for _ in range(config.max_iterations):
            lambda_bias = (1.0 - gamma) * lambdas + gamma * marginals_previous
            mu = decoder._check_update(nu_previous, syndrome)
            incoming = np.bincount(decoder._edge_variables, weights=mu, minlength=variables)
            nu_current = lambda_bias[decoder._edge_variables] + incoming[decoder._edge_variables] - mu
            final_marginals = lambda_bias + incoming
            last_decision = decoder._hard_decision(final_marginals)
            iterations_this_leg += 1
            cumulative_iterations += 1
            nu_previous = nu_current
            marginals_previous = final_marginals
            if not np.any(decoder._syndrome(last_decision) ^ syndrome):
                candidates.append(
                    (leg_index + 1, float(np.dot(last_decision, lambdas)), last_decision.copy())
                )
                converged = True
                break
        leg_iterations.append(iterations_this_leg)
        initial_marginals = final_marginals.copy()
        if leg_index + 1 in R_VALUES:
            checkpoint_decisions[leg_index + 1] = last_decision.copy()
        if len(candidates) >= max(S_VALUES):
            break

    return {
        "leg_iterations": leg_iterations,
        "candidates": candidates,
        "checkpoint_decisions": checkpoint_decisions,
        "last_decision": last_decision,
    }


def derive_result(trajectory: dict[str, object], target_s: int, target_r: int) -> dict[str, object]:
    leg_iterations = trajectory["leg_iterations"]
    candidates = trajectory["candidates"]
    eligible = [candidate for candidate in candidates if candidate[0] <= target_r]
    stop_leg = target_r
    if len(eligible) >= target_s:
        stop_leg = eligible[target_s - 1][0]
        eligible = eligible[:target_s]
    else:
        eligible = [candidate for candidate in eligible if candidate[0] <= stop_leg]
    executed_legs = min(stop_leg, len(leg_iterations))
    total_iterations = int(sum(leg_iterations[:executed_legs]))
    first_leg_iterations = int(leg_iterations[0])
    if eligible:
        selected = min(eligible, key=lambda item: item[1])
        decision = selected[2]
        selected_weight: float | None = selected[1]
    else:
        checkpoint_decisions = trajectory["checkpoint_decisions"]
        decision = checkpoint_decisions.get(target_r, trajectory["last_decision"])
        selected_weight = None
    return {
        "decision": decision,
        "selected_weight": selected_weight,
        "iterations": total_iterations,
        "first_leg_iterations": first_leg_iterations,
        "legs": executed_legs,
        "solutions": len(eligible),
        "first_leg_success": any(candidate[0] == 1 for candidate in candidates),
        "rescued": bool(eligible) and not any(candidate[0] == 1 for candidate in candidates),
    }


def run_combo(first_gamma: float, interval: tuple[float, float]) -> list[dict[str, object]]:
    h, action, probabilities = load_matrices()
    with np.load(OUT_DIR / "paired_samples.npz") as samples:
        syndromes = samples["syndromes"]
        observed_logicals = samples["observed_logicals"]
    lambdas = np.log((1.0 - probabilities) / probabilities)
    output: list[dict[str, object]] = []
    for shot in range(SHOTS):
        decoder = FloatRelayBPDecoder(h, S=3, R=32, seed=DECODER_SEED + shot)
        trajectory = one_trajectory(decoder, lambdas, syndromes[shot], first_gamma, interval)
        for target_s in S_VALUES:
            for target_r in R_VALUES:
                result = derive_result(trajectory, target_s, target_r)
                decision = result.pop("decision")
                syndrome_valid = not np.any(decoder._syndrome(decision) ^ syndromes[shot])
                predicted_logical = np.asarray(action @ decision, dtype=np.uint8).reshape(-1) & 1
                logical_match = bool(np.array_equal(predicted_logical, observed_logicals[shot]))
                output.append(
                    {
                        "first_gamma": first_gamma,
                        "later_gamma_low": interval[0],
                        "later_gamma_high": interval[1],
                        "S": target_s,
                        "R": target_r,
                        "shot": shot,
                        "syndrome_converged": int(syndrome_valid),
                        "logical_action_match": int(logical_match),
                        "logically_correct": int(syndrome_valid and logical_match),
                        **result,
                    }
                )
    return output


def summarize(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    keys = ["first_gamma", "later_gamma_low", "later_gamma_high", "S", "R"]
    groups: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for row in rows:
        groups.setdefault(tuple(row[key] for key in keys), []).append(row)
    for values, group in sorted(groups.items()):
        iterations = np.asarray([row["iterations"] for row in group], dtype=float)
        legs = np.asarray([row["legs"] for row in group], dtype=float)
        converged = np.asarray([row["syndrome_converged"] for row in group], dtype=bool)
        correct = np.asarray([row["logically_correct"] for row in group], dtype=bool)
        rescued = np.asarray([row["rescued"] for row in group], dtype=bool)
        extra_iterations = sum(max(0, int(row["iterations"]) - int(row["first_leg_iterations"])) for row in group)
        weights = [float(row["selected_weight"]) for row in group if row["selected_weight"] is not None]
        summary = dict(zip(keys, values))
        summary.update(
            {
                "shots": len(group),
                "syndrome_convergence_rate": float(np.mean(converged)),
                "non_convergence_rate": float(np.mean(~converged)),
                "logical_successes": int(correct.sum()),
                "logical_failure_rate": float(np.mean(~correct)),
                "average_iterations": float(np.mean(iterations)),
                "p50_iterations": float(np.percentile(iterations, 50)),
                "p90_iterations": float(np.percentile(iterations, 90)),
                "p99_iterations": float(np.percentile(iterations, 99)),
                "maximum_iterations": int(np.max(iterations)),
                "average_relay_legs": float(np.mean(legs)),
                "maximum_relay_legs": int(np.max(legs)),
                "average_selected_solution_weight": float(np.mean(weights)) if weights else None,
                "rescued_shots_beyond_first_leg": int(rescued.sum()),
                "logical_successes_per_average_iteration": float(np.mean(correct) / np.mean(iterations)),
                "rescued_failures_per_extra_relay_iteration": (
                    float(rescued.sum() / extra_iterations) if extra_iterations else None
                ),
            }
        )
        summaries.append(summary)
    return summaries


def validate_checkpoint_method(h: sparse.csr_matrix, probabilities: np.ndarray, syndromes: np.ndarray) -> None:
    lambdas = np.log((1.0 - probabilities) / probabilities)
    first_gamma = 0.125
    interval = (-0.24, 0.66)
    shot = 0
    trajectory_decoder = FloatRelayBPDecoder(h, S=3, R=32, seed=DECODER_SEED + shot)
    trajectory = one_trajectory(trajectory_decoder, lambdas, syndromes[shot], first_gamma, interval)
    for target_s, target_r in ((1, 4), (3, 8), (3, 32)):
        legs = (
            RelayLegConfig(max_iterations=80, gamma=first_gamma),
            *(RelayLegConfig(max_iterations=60, gamma_range=interval) for _ in range(target_r - 1)),
        )
        direct = FloatRelayBPDecoder(
            h, leg_configs=legs, S=target_s, R=target_r, seed=DECODER_SEED + shot
        ).decode(lambdas, syndromes[shot])
        derived = derive_result(trajectory, target_s, target_r)
        if not np.array_equal(direct.decoded_error, derived["decision"]):
            raise RuntimeError("Checkpoint sweep correction differs from direct canonical decode")
        if direct.total_iterations != derived["iterations"] or direct.relay_legs != derived["legs"]:
            raise RuntimeError("Checkpoint sweep stopping data differs from direct canonical decode")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    h, _, probabilities = load_matrices()
    circuit = stim.Circuit.from_file(str(TIER2_DIR / "circuit.stim"))
    syndromes, observed_logicals = circuit.compile_detector_sampler(seed=SAMPLE_SEED).sample(
        SHOTS, separate_observables=True
    )
    repeat = circuit.compile_detector_sampler(seed=SAMPLE_SEED).sample(SHOTS, separate_observables=True)
    if not np.array_equal(syndromes, repeat[0]) or not np.array_equal(observed_logicals, repeat[1]):
        raise RuntimeError("Fixed-seed samples are not reproducible")
    np.savez_compressed(
        OUT_DIR / "paired_samples.npz",
        syndromes=syndromes,
        observed_logicals=observed_logicals,
        probabilities=probabilities,
    )
    validate_checkpoint_method(h, probabilities, syndromes)

    rows: list[dict[str, object]] = []
    combos = [(gamma, interval) for gamma in FIRST_GAMMAS for interval in INTERVALS]
    with ProcessPoolExecutor(max_workers=min(6, len(combos))) as executor:
        futures = {executor.submit(run_combo, gamma, interval): (gamma, interval) for gamma, interval in combos}
        for future in as_completed(futures):
            combo = futures[future]
            rows.extend(future.result())
            print(f"completed first_gamma={combo[0]} interval={combo[1]}", flush=True)
    rows.sort(key=lambda row: (row["first_gamma"], row["later_gamma_low"], row["S"], row["R"], row["shot"]))
    summaries = summarize(rows)
    with (OUT_DIR / "per_shot_results.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT_DIR / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")

    tier2_manifest = json.loads((TIER2_DIR / "manifest.json").read_text(encoding="utf-8"))
    manifest = {
        "study": "first paired Tier-2 circuit-level Relay-BP parameter sweep",
        "shots": {"count": SHOTS, "seed": SAMPLE_SEED, "paired": True},
        "circuit": {"p": 0.003, "rounds": 12, "memory_basis": "Z"},
        "graph": {
            "package": str(TIER2_DIR.relative_to(PROJECT_ROOT)),
            "dimensions": {"detectors": 1728, "faults": 67752, "logical_observables": 12},
            "package_manifest_sha256": sha256(TIER2_DIR / "manifest.json"),
            "detector_incidence_sha256": tier2_manifest["graph"]["detector_incidence_sha256"],
        },
        "sweep": {
            "first_gamma": list(FIRST_GAMMAS),
            "later_gamma_intervals": [list(value) for value in INTERVALS],
            "S": list(S_VALUES),
            "R": list(R_VALUES),
            "reported_configurations": len(summaries),
            "decoder_seed_per_shot": "9100 + shot_index",
            "shared_trajectory_checkpointing": True,
            "checkpoint_validation": "matched direct canonical decodes for S/R=(1,4),(3,8),(3,32)",
        },
        "efficiency_definitions": {
            "logical_successes_per_average_iteration": "logical success rate divided by average iterations",
            "rescued_failures_per_extra_relay_iteration": "rescued shots divided by total iterations after first legs",
        },
        "software": {
            "git_commit": git_output("rev-parse", "HEAD"),
            "git_worktree_dirty": bool(git_output("status", "--porcelain")),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "stim": stim.__version__,
            "float_decoder_sha256": sha256(REFERENCE_DIR / "relay_bp_float.py"),
        },
        "artifacts": ["manifest.json", "summary.json", "per_shot_results.csv", "paired_samples.npz", "run_first_sweep.py"],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()

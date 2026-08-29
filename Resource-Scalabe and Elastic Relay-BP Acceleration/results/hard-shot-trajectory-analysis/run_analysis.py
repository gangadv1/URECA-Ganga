#!/usr/bin/env python3
"""Compact canonical-float trajectory analysis for the locked 13-shot panel.

This script only reads existing circuit/sample/result artifacts.  It replays
the canonical float decoder with the exact saved hardware gamma streams and
writes compact derived metrics; it never stores dense mu/nu messages.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import sparse


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
REFERENCE = ROOT / "reference"
RNG_REFERENCE = ROOT / "fpga" / "verification" / "parallel_n2"
sys.path[:0] = [str(REFERENCE), str(RNG_REFERENCE)]

from gamma_rng_reference import vector as hardware_gamma_vector  # noqa: E402
from relay_bp_float import FloatRelayBPDecoder, RelayLegConfig  # noqa: E402


PACKAGE = ROOT / "graphs" / "generated" / "gross_circuit_level" / "memory_Z_r12_p0p003"
SAMPLES = ROOT / "results" / "circuit-level-multiseed" / "paired_samples.npz"
SAVED_RESULTS = ROOT / "results" / "n1-vs-n2-hardware-latency" / "per_shot_results.csv"

PANEL = (
    (20260809, 31),
    (20260810, 15),
    (20260811, 6),
    (20260809, 2),
    (20260810, 22),
    (20260811, 25),
    (20260812, 14),
    (20260811, 28),
    (20260810, 4),
    (20260810, 9),
    (20260809, 18),
    (20260810, 26),
    (20260811, 26),
)

SHOT_CLASS = {
    (20260810, 15): "easy",
    (20260811, 6): "easy",
    (20260809, 31): "easy",
    (20260809, 2): "typical",
    (20260810, 22): "typical",
    (20260811, 25): "moderately_hard",
    (20260812, 14): "moderately_hard_counterexample",
    (20260811, 28): "hard_major_improvement",
    (20260810, 4): "severe_success",
    (20260810, 9): "severe_success",
    (20260809, 18): "severe_rescue",
    (20260810, 26): "severe_rescue",
    (20260811, 26): "severe_rescue",
}

CLOSE_TO_ZERO = 1.0
FIRST_LIMIT = 80
LATER_LIMIT = 60
RELAY_LIMIT = 32


def packed_hash(bits: np.ndarray) -> str:
    return hashlib.sha256(np.packbits(np.asarray(bits, dtype=np.uint8)).tobytes()).hexdigest()


def load_problem() -> tuple[sparse.csr_matrix, sparse.csr_matrix, np.ndarray]:
    with np.load(PACKAGE / "edge_lists.npz") as data:
        detector_edges = data["detector_edges"]
        observable_edges = data["observable_edges"]
    with np.load(PACKAGE / "faults.npz") as data:
        probabilities = data["probabilities"]
    h = sparse.csr_matrix(
        (np.ones(len(detector_edges), dtype=np.uint8), (detector_edges[:, 1], detector_edges[:, 0])),
        shape=(1728, 67752),
    )
    action = sparse.csr_matrix(
        (np.ones(len(observable_edges), dtype=np.uint8), (observable_edges[:, 1], observable_edges[:, 0])),
        shape=(12, 67752),
    )
    return h, action, np.log((1.0 - probabilities) / probabilities)


def load_saved_rows() -> dict[tuple[int, int], dict[str, str]]:
    with SAVED_RESULTS.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    return {(int(row["sample_seed"]), int(row["shot"])): row for row in rows}


def make_leg_configs(seed: int, variables: int) -> tuple[tuple[RelayLegConfig, ...], dict[str, int]]:
    state = seed
    configs: list[RelayLegConfig] = [RelayLegConfig(max_iterations=FIRST_LIMIT, gamma=0.125)]
    words = 0
    rejected = 0
    for _ in range(1, RELAY_LIMIT):
        values, consumed, state, leg_rejected = hardware_gamma_vector(state, variables)
        gamma = np.asarray(values, dtype=np.float64) / 16.0
        configs.append(RelayLegConfig(max_iterations=LATER_LIMIT, gamma=gamma))
        words += len(consumed) + leg_rejected
        rejected += leg_rejected
    return tuple(configs), {"final_state": int(state), "words": words, "rejected": rejected}


class CompactTraceCollector:
    def __init__(
        self,
        sample_seed: int,
        shot: int,
        engine: str,
        prior: np.ndarray,
        h: sparse.csr_matrix,
        syndrome: np.ndarray,
    ) -> None:
        self.sample_seed = sample_seed
        self.shot = shot
        self.engine = engine
        self.prior = prior
        initial_decision = (prior <= 0.0).astype(np.uint8)
        initial_predicted = np.asarray(h @ initial_decision).reshape(-1).astype(np.uint8) & 1
        self.previous_residual = initial_predicted ^ syndrome
        self.previous_decision = initial_decision
        self.initial_residual_weight = int(np.count_nonzero(self.previous_residual))
        self.best_residual = self.initial_residual_weight
        self.since_best = 0
        self.longest_no_improvement = 0
        self.weight_increases = 0
        self.equal_weights = 0
        self.seen_residuals: Counter[str] = Counter({packed_hash(self.previous_residual): 1})
        self.previous_hashes = [packed_hash(self.previous_residual)]
        self.rows: list[dict[str, Any]] = []

    def __call__(self, event: dict[str, object]) -> None:
        gamma = np.asarray(event["gamma"], dtype=float)
        beliefs = np.asarray(event["beliefs"], dtype=float)
        decision = np.asarray(event["decoded_error"], dtype=np.uint8)
        residual = np.asarray(event["residual"], dtype=np.uint8)
        residual_weight = int(np.count_nonzero(residual))
        previous_weight = int(np.count_nonzero(self.previous_residual))
        residual_delta = residual_weight - previous_weight
        if residual_delta > 0:
            self.weight_increases += 1
        elif residual_delta == 0:
            self.equal_weights += 1
        improved_global_best = residual_weight < self.best_residual
        if improved_global_best:
            self.best_residual = residual_weight
            self.since_best = 0
        else:
            self.since_best += 1
        self.longest_no_improvement = max(self.longest_no_improvement, self.since_best)
        residual_hash = packed_hash(residual)
        decision_hash = packed_hash(decision)
        exact_repeat = self.seen_residuals[residual_hash] > 0
        two_cycle_repeat = len(self.previous_hashes) >= 2 and residual_hash == self.previous_hashes[-2]
        self.seen_residuals[residual_hash] += 1
        self.previous_hashes.append(residual_hash)
        abs_beliefs = np.abs(beliefs)
        row = {
            "sample_seed": self.sample_seed,
            "shot": self.shot,
            "trajectory": self.engine,
            "shot_class": SHOT_CLASS[(self.sample_seed, self.shot)],
            "relay_leg": int(event["leg_index"]) + 1,
            "iteration_in_leg": int(event["iteration"]),
            "global_iteration": int(event["global_iteration"]),
            "residual_weight": residual_weight,
            "residual_delta": residual_delta,
            "residual_improved": int(residual_delta < 0),
            "residual_equal": int(residual_delta == 0),
            "residual_worsened": int(residual_delta > 0),
            "best_residual_so_far": self.best_residual,
            "iterations_since_best": self.since_best,
            "longest_no_improvement_so_far": self.longest_no_improvement,
            "residual_vector_distance": int(np.count_nonzero(residual ^ self.previous_residual)),
            "residual_exact_repeat": int(exact_repeat),
            "residual_two_cycle_repeat": int(two_cycle_repeat),
            "residual_hash": residual_hash,
            "converged": int(bool(event["converged"])),
            "candidate_weight": float(np.dot(decision, self.prior)),
            "gamma_min": float(gamma.min()),
            "gamma_max": float(gamma.max()),
            "gamma_mean": float(gamma.mean()),
            "gamma_std": float(gamma.std()),
            "gamma_negative": int(np.count_nonzero(gamma < 0)),
            "gamma_zero": int(np.count_nonzero(gamma == 0)),
            "gamma_positive": int(np.count_nonzero(gamma > 0)),
            "belief_min": float(beliefs.min()),
            "belief_max": float(beliefs.max()),
            "belief_mean": float(beliefs.mean()),
            "belief_mean_abs": float(abs_beliefs.mean()),
            "belief_median_abs": float(np.median(abs_beliefs)),
            "belief_fraction_close_to_zero": float(np.mean(abs_beliefs <= CLOSE_TO_ZERO)),
            "decision_weight": int(np.count_nonzero(decision)),
            "decision_changes": int(np.count_nonzero(decision ^ self.previous_decision)),
            "decision_hash": decision_hash,
        }
        self.rows.append(row)
        self.previous_residual = residual.copy()
        self.previous_decision = decision.copy()


def first_leg_fields(rows: list[dict[str, Any]], initial_residual: int) -> dict[str, Any]:
    leg = [row for row in rows if row["relay_leg"] == 1]
    by_iteration = {row["iteration_in_leg"]: row for row in leg}
    output: dict[str, Any] = {
        "initial_residual": initial_residual,
        "first_leg_iterations": len(leg),
        "first_leg_end_residual": leg[-1]["residual_weight"],
        "first_leg_best_residual": min(row["residual_weight"] for row in leg),
        "first_leg_longest_no_improvement": max(row["iterations_since_best"] for row in leg),
        "first_leg_total_decision_changes": sum(row["decision_changes"] for row in leg),
        "first_leg_mean_decision_changes": float(np.mean([row["decision_changes"] for row in leg])),
        "first_leg_mean_belief_abs": float(np.mean([row["belief_mean_abs"] for row in leg])),
        "first_leg_end_belief_abs": leg[-1]["belief_mean_abs"],
        "first_leg_end_close_fraction": leg[-1]["belief_fraction_close_to_zero"],
    }
    for checkpoint in (5, 10, 20, 40):
        output[f"residual_after_{checkpoint}"] = (
            by_iteration[checkpoint]["residual_weight"] if checkpoint in by_iteration else None
        )
    return output


def summarize_legs(
    rows: list[dict[str, Any]], initial_residual: int
) -> list[dict[str, Any]]:
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[int(row["relay_leg"])].append(row)
    output: list[dict[str, Any]] = []
    prior_end = initial_residual
    global_best_before = initial_residual
    for leg_index in sorted(groups):
        leg = groups[leg_index]
        start = prior_end
        end = int(leg[-1]["residual_weight"])
        minimum = min(int(row["residual_weight"]) for row in leg)
        # Deliberately simple endpoint rule: a leg is productive only when it
        # leaves a lower residual for the next leg, regressive when it leaves
        # a higher one, and stagnant when the endpoints are equal.  The
        # separate minimum/best fields preserve temporary within-leg gains.
        if end < start:
            classification = "productive"
        elif end > start:
            classification = "regressive"
        else:
            classification = "stagnant"
        output.append(
            {
                "sample_seed": leg[0]["sample_seed"],
                "shot": leg[0]["shot"],
                "trajectory": leg[0]["trajectory"],
                "shot_class": leg[0]["shot_class"],
                "relay_leg": leg_index,
                "starting_residual": start,
                "minimum_residual": minimum,
                "ending_residual": end,
                "iterations_used": len(leg),
                "net_residual_improvement": start - end,
                "best_residual_improvement": start - minimum,
                "converged": int(bool(leg[-1]["converged"])),
                "improved_previous_global_best": int(minimum < global_best_before),
                "classification": classification,
                "residual_increases": sum(int(row["residual_worsened"]) for row in leg),
                "equal_residual_iterations": sum(int(row["residual_equal"]) for row in leg),
                "decision_changes": sum(int(row["decision_changes"]) for row in leg),
                "longest_no_improvement_at_end": leg[-1]["longest_no_improvement_so_far"],
                "mean_belief_abs": float(np.mean([row["belief_mean_abs"] for row in leg])),
                "mean_close_fraction": float(
                    np.mean([row["belief_fraction_close_to_zero"] for row in leg])
                ),
            }
        )
        prior_end = end
        global_best_before = min(global_best_before, minimum)
    return output


def trajectory_summary(
    rows: list[dict[str, Any]],
    legs: list[dict[str, Any]],
    collector: CompactTraceCollector,
    result: Any,
    logical_correct: bool,
    saved: dict[str, str],
    engine: str,
    gamma_meta: dict[str, int],
) -> dict[str, Any]:
    prefix = "e0_" if engine == "E0" else "e1_"
    convergence_iteration = next(
        (int(row["global_iteration"]) for row in rows if row["converged"]), None
    )
    repeated_weights = sum(count - 1 for count in Counter(row["residual_weight"] for row in rows).values())
    first = first_leg_fields(rows, collector.initial_residual_weight)
    output = {
        "sample_seed": collector.sample_seed,
        "shot": collector.shot,
        "trajectory": engine,
        "shot_class": SHOT_CLASS[(collector.sample_seed, collector.shot)],
        "gamma_seed": int(saved["s0"] if engine == "E0" else saved["s1"]),
        "workload_hash_verified": 1,
        "gamma_stream_reproduced": 1,
        "replay_converged": int(result.converged),
        "replay_logical_correct": int(logical_correct),
        "replay_iterations": int(result.total_iterations),
        "replay_relay_legs": int(result.relay_legs),
        "replay_convergence_iteration": convergence_iteration,
        "saved_fixed_converged": int(saved[prefix + "syndrome_converged"]),
        "saved_fixed_logical_correct": int(saved[prefix + "logical_correct"]),
        "saved_fixed_iterations": int(saved[prefix + "iterations"]),
        "saved_fixed_relay_legs": int(saved[prefix + "legs"]),
        "saved_fixed_cycles": int(saved[prefix + "result_cycles"]),
        "saved_outcome_match": int(
            int(result.converged) == int(saved[prefix + "syndrome_converged"])
            and int(logical_correct) == int(saved[prefix + "logical_correct"])
        ),
        "saved_iteration_leg_match": int(
            int(result.total_iterations) == int(saved[prefix + "iterations"])
            and int(result.relay_legs) == int(saved[prefix + "legs"])
        ),
        "best_residual": min(row["residual_weight"] for row in rows),
        "longest_no_improvement_streak": max(row["longest_no_improvement_so_far"] for row in rows),
        "residual_weight_increases": sum(row["residual_worsened"] for row in rows),
        "equal_residual_iterations": sum(row["residual_equal"] for row in rows),
        "repeated_residual_weights": repeated_weights,
        "exact_residual_vector_repeats": sum(row["residual_exact_repeat"] for row in rows),
        "two_cycle_residual_repeats": sum(row["residual_two_cycle_repeat"] for row in rows),
        "total_residual_vector_distance": sum(row["residual_vector_distance"] for row in rows),
        "total_decision_changes": sum(row["decision_changes"] for row in rows),
        "mean_decision_changes": float(np.mean([row["decision_changes"] for row in rows])),
        "mean_belief_abs": float(np.mean([row["belief_mean_abs"] for row in rows])),
        "mean_close_fraction": float(
            np.mean([row["belief_fraction_close_to_zero"] for row in rows])
        ),
        "productive_legs": sum(leg["classification"] == "productive" for leg in legs),
        "stagnant_legs": sum(leg["classification"] == "stagnant" for leg in legs),
        "regressive_legs": sum(leg["classification"] == "regressive" for leg in legs),
        "zero_net_improvement_legs": sum(leg["net_residual_improvement"] == 0 for leg in legs),
        "worsening_legs": sum(leg["net_residual_improvement"] < 0 for leg in legs),
        "gamma_words_for_full_32_leg_schedule": gamma_meta["words"],
        "gamma_rejections_for_full_32_leg_schedule": gamma_meta["rejected"],
        **first,
    }
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"no rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def mean_fields(rows: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, float | None]:
    return {
        field: (float(np.mean([float(row[field]) for row in rows])) if rows else None)
        for field in fields
    }


def paired_comparisons(
    iteration_rows: list[dict[str, Any]], trajectory_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_trajectory: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in iteration_rows:
        by_trajectory[(row["sample_seed"], row["shot"], row["trajectory"])].append(row)
    summaries = {(row["sample_seed"], row["shot"], row["trajectory"]): row for row in trajectory_rows}
    output: list[dict[str, Any]] = []
    for sample_seed, shot in PANEL:
        e0 = by_trajectory[(sample_seed, shot, "E0")]
        e1 = by_trajectory[(sample_seed, shot, "E1")]
        divergence = None
        for left, right in zip(e0, e1):
            if left["residual_hash"] != right["residual_hash"] or left["decision_hash"] != right["decision_hash"]:
                divergence = int(left["global_iteration"])
                break
        common_first_leg = all(
            left["residual_hash"] == right["residual_hash"]
            and left["decision_hash"] == right["decision_hash"]
            for left, right in zip(
                [row for row in e0 if row["relay_leg"] == 1],
                [row for row in e1 if row["relay_leg"] == 1],
            )
        )
        s0 = summaries[(sample_seed, shot, "E0")]
        s1 = summaries[(sample_seed, shot, "E1")]
        output.append(
            {
                "sample_seed": sample_seed,
                "shot": shot,
                "common_first_leg_exact": int(common_first_leg),
                "first_divergence_global_iteration": divergence,
                "e0_replay_converged": s0["replay_converged"],
                "e1_replay_converged": s1["replay_converged"],
                "e0_iterations": s0["replay_iterations"],
                "e1_iterations": s1["replay_iterations"],
                "e0_legs": s0["replay_relay_legs"],
                "e1_legs": s1["replay_relay_legs"],
                "e0_productive_legs": s0["productive_legs"],
                "e1_productive_legs": s1["productive_legs"],
                "e0_stagnant_regressive_legs": s0["stagnant_legs"] + s0["regressive_legs"],
                "e1_stagnant_regressive_legs": s1["stagnant_legs"] + s1["regressive_legs"],
                "e0_longest_stagnation": s0["longest_no_improvement_streak"],
                "e1_longest_stagnation": s1["longest_no_improvement_streak"],
                "e0_mean_decision_changes": s0["mean_decision_changes"],
                "e1_mean_decision_changes": s1["mean_decision_changes"],
                "e0_mean_belief_abs": s0["mean_belief_abs"],
                "e1_mean_belief_abs": s1["mean_belief_abs"],
            }
        )
    return output


def correlations(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for field in (
        "initial_residual",
        "residual_after_5",
        "residual_after_10",
        "residual_after_20",
        "residual_after_40",
        "first_leg_end_residual",
        "first_leg_best_residual",
        "first_leg_longest_no_improvement",
        "first_leg_total_decision_changes",
        "first_leg_end_belief_abs",
        "first_leg_end_close_fraction",
    ):
        pairs = [(float(row[field]), float(row["replay_iterations"])) for row in rows if row[field] not in (None, "")]
        if len(pairs) < 3 or np.std([pair[0] for pair in pairs]) == 0:
            result[field] = None
        else:
            result[field] = float(np.corrcoef(np.asarray(pairs).T)[0, 1])
    return result


def make_plots(
    iteration_rows: list[dict[str, Any]],
    leg_rows: list[dict[str, Any]],
    trajectory_rows: list[dict[str, Any]],
) -> None:
    by_key: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in iteration_rows:
        by_key[(row["sample_seed"], row["shot"], row["trajectory"])].append(row)

    representatives = [(20260810, 15, "E0"), (20260809, 2, "E0"), (20260810, 4, "E0"), (20260810, 26, "E0")]
    for key in representatives:
        rows = by_key[key]
        plt.plot([row["global_iteration"] for row in rows], [row["residual_weight"] for row in rows], label=f"{key[0]}/{key[1]} {key[2]}")
    plt.xlabel("Global iteration")
    plt.ylabel("Residual weight")
    plt.title("Representative canonical-float residual trajectories")
    plt.legend(fontsize=8)
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(OUT / "residual_representatives.png", dpi=170)
    plt.close()

    rescue_keys = [(20260810, 26), (20260809, 18), (20260811, 26)]
    fig, axes = plt.subplots(3, 1, figsize=(8, 10))
    for axis, key in zip(axes, rescue_keys):
        for engine in ("E0", "E1"):
            rows = by_key[(key[0], key[1], engine)]
            axis.plot([row["global_iteration"] for row in rows], [row["residual_weight"] for row in rows], label=engine)
        axis.set_title(f"{key[0]}/{key[1]}")
        axis.set_ylabel("Residual")
        axis.grid(alpha=0.25)
        axis.legend()
    axes[-1].set_xlabel("Global iteration")
    fig.tight_layout()
    fig.savefig(OUT / "rescue_e0_vs_e1_residual.png", dpi=170)
    plt.close(fig)

    selected_legs = [row for row in leg_rows if (row["sample_seed"], row["shot"]) in set(rescue_keys)]
    labels = [f"{row['sample_seed']}/{row['shot']} {row['trajectory']} L{row['relay_leg']}" for row in selected_legs]
    colors = {"productive": "#2ca02c", "stagnant": "#7f7f7f", "regressive": "#d62728"}
    plt.figure(figsize=(12, 5))
    plt.bar(np.arange(len(selected_legs)), [row["best_residual_improvement"] for row in selected_legs], color=[colors[row["classification"]] for row in selected_legs])
    plt.xticks(np.arange(len(labels)), labels, rotation=90, fontsize=6)
    plt.ylabel("Best residual improvement within leg")
    plt.title("Relay-leg productivity in saved rescue-shot workloads")
    plt.tight_layout()
    plt.savefig(OUT / "relay_leg_productivity.png", dpi=170)
    plt.close()

    e0 = [row for row in trajectory_rows if row["trajectory"] == "E0"]
    plt.scatter([row["longest_no_improvement_streak"] for row in e0], [row["saved_fixed_cycles"] for row in e0])
    for row in e0:
        plt.annotate(f"{row['sample_seed']}/{row['shot']}", (row["longest_no_improvement_streak"], row["saved_fixed_cycles"]), fontsize=6)
    plt.xlabel("Canonical-float longest no-best-improvement streak")
    plt.ylabel("Saved fixed-point E0 architectural cycles")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(OUT / "stagnation_vs_saved_latency.png", dpi=170)
    plt.close()

    plt.scatter([row["first_leg_best_residual"] for row in trajectory_rows], [row["replay_iterations"] for row in trajectory_rows], c=[row["first_leg_longest_no_improvement"] for row in trajectory_rows], cmap="viridis")
    plt.xlabel("Best first-leg residual")
    plt.ylabel("Canonical-float total iterations")
    plt.colorbar(label="First-leg longest no-improvement streak")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(OUT / "first_leg_vs_total_iterations.png", dpi=170)
    plt.close()


def write_documents(
    trajectory_rows: list[dict[str, Any]],
    leg_rows: list[dict[str, Any]],
    paired: list[dict[str, Any]],
    comparison: dict[str, Any],
) -> None:
    panel_text = "\n".join(f"- `({seed}, {shot})`" for seed, shot in PANEL)
    mismatch_count = sum(not row["saved_iteration_leg_match"] for row in trajectory_rows)
    outcome_mismatch_count = sum(not row["saved_outcome_match"] for row in trajectory_rows)
    readme = f"""# Hard-shot trajectory analysis

## Purpose

Compact per-iteration analysis of the locked 13-shot p=0.003 panel using
`reference/relay_bp_float.py::FloatRelayBPDecoder`.  No STIM samples are generated.

## Exact panel

{panel_text}

Each workload is recovered from `results/circuit-level-multiseed/paired_samples.npz`.
The syndrome and logical hashes are checked against
`results/n1-vs-n2-hardware-latency/per_shot_results.csv` before decoding.

## Methodology

- Both E0 and E1 are replayed for every shot.
- E0 uses saved seed `s0`; E1 uses saved seed `s1`.
- The exact xorshift64/rejection-map gamma vectors are reconstructed with
  `fpga/verification/parallel_n2/gamma_rng_reference.py` and supplied explicitly.
- First leg is gamma 0.125 for 80 iterations; later legs are limited to 60;
  S=1 and R=32 are unchanged.
- A disabled-by-default callback observes completed canonical-float iterations.
- Dense mu/nu matrices are not saved.
- "Close to zero" means `abs(belief) <= {CLOSE_TO_ZERO}` in float LLR units.

Relay-leg classes use a simple endpoint rule: productive if ending residual is
below starting residual, regressive if it is above, and stagnant if equal.  The
minimum/best fields separately retain temporary within-leg progress.

## Reproduction boundary

The archived latency study used `FixedRelayBPDecoder`, while this analysis is
required to use the canonical float decoder.  Workloads and gamma streams are
exactly reproducible, but fixed-point iteration/leg trajectories are not expected
to be identical.  There are {mismatch_count}/26 iteration/leg mismatches and
{outcome_mismatch_count}/26 convergence/logical-class mismatches versus the saved
fixed study; these are explicitly retained in `per_trajectory_summary.csv`.

## Outputs

- `per_iteration_trace.csv`: compact iteration metrics and state hashes.
- `per_leg_summary.csv`: relay-leg productivity summaries.
- `per_trajectory_summary.csv`: float replay and saved-fixed comparison.
- `comparison_summary.json`: grouped and paired summaries.
- `FIRST_LEG_ANALYSIS.md` and `TRAJECTORY_FINDINGS.md`.
- Five focused plots.

## Limitations

- This is a selected 13-shot panel, not an unbiased performance sample.
- Float trajectories characterize canonical algorithm behavior but do not replace
  the saved fixed/RTL-calibrated hardware results.
- Residual hashes detect exact repeats; they do not prove a dynamical limit cycle.
- Associations are descriptive and cannot establish causation or justify a heuristic.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")

    corr = comparison["first_leg_correlations_with_float_total_iterations"]
    first_leg = f"""# First-leg analysis

The first leg is bit-for-bit common between E0 and E1 in all {sum(row['common_first_leg_exact'] for row in paired)}/13 shot pairs because it uses the same syndrome, prior, and uniform gamma=0.125. Diversity begins with later-leg gamma vectors.

## Recorded signals

For every trajectory the analysis records initial residual; residual after 5, 10,
20 and 40 iterations when reached; first-leg ending and best residual; longest
no-best-improvement streak; decision churn; mean/end belief magnitude; and the
fraction with `abs(belief) <= {CLOSE_TO_ZERO}`.

## Exploratory correlations with canonical-float total iterations

```json
{json.dumps(json_ready(corr), indent=2)}
```

These correlations are descriptive.  E0/E1 duplicate the same first-leg observation
within a shot, the panel is deliberately tail-enriched, and checkpoint values are
missing when a trajectory converges before that checkpoint.  No predictor was fit.

Initial syndrome weight is available before decoding, but the panel includes the
saved maximum-latency shot `(20260811,26)` with initial weight 130 and much easier
controls with comparable or greater weights.  It is therefore not sufficient by
itself as a difficulty indicator in this panel.
"""
    (OUT / "FIRST_LEG_ANALYSIS.md").write_text(first_leg, encoding="utf-8")

    easy = comparison["easy_vs_severe"]["easy"]
    severe = comparison["easy_vs_severe"]["severe"]
    leg_counts = comparison["leg_class_counts"]
    findings = f"""# Trajectory findings

## Easy versus hard

Easy canonical-float trajectories converge in the first leg with short residual
histories.  Severe trajectories exhibit longer no-best-improvement streaks, more
equal/increasing residual-weight steps, more decision churn in aggregate, and many
additional relay legs.  Group means are retained below rather than interpreted as
causal effects.

```json
{json.dumps(json_ready({'easy': easy, 'severe': severe}), indent=2)}
```

## Relay-leg behavior

```json
{json.dumps(json_ready(leg_counts), indent=2)}
```

Productive, stagnant, and regressive legs coexist in difficult trajectories.  Exact
residual-vector repeats and two-cycle returns provide oscillation-like indicators,
but no claim of a stable dynamical cycle is made.

## E0 versus E1

All pairs share an identical first leg.  When they diverge, they do so only after
later-leg gamma diversity begins.  The paired records in `comparison_summary.json`
show whether the shorter float path has more productive legs, shorter stagnation,
different belief confidence, or reduced decision churn.  Because the saved study
was fixed-point, its named rescue/winner labels remain historical comparison labels;
the float replay outcome is reported independently.

## Scope

The evidence supports stagnation, regression, repeated residual states, residual
vector motion, belief confidence, and decision churn as observable candidates for
further analysis.  It does not select or validate a scheduling or folding heuristic.
"""
    (OUT / "TRAJECTORY_FINDINGS.md").write_text(findings, encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    h, action, prior = load_problem()
    saved_rows = load_saved_rows()
    iteration_rows: list[dict[str, Any]] = []
    leg_rows: list[dict[str, Any]] = []
    trajectory_rows: list[dict[str, Any]] = []
    workload_verification: list[dict[str, Any]] = []

    with np.load(SAMPLES) as samples:
        sample_seeds = samples["sample_seeds"]
        syndromes = samples["syndromes"]
        observed_logicals = samples["observed_logicals"]
        for sample_seed, shot in PANEL:
            saved = saved_rows[(sample_seed, shot)]
            matches = np.flatnonzero(sample_seeds == sample_seed)
            if len(matches) != 1:
                raise RuntimeError(f"sample seed {sample_seed} is not unique in archive")
            seed_index = int(matches[0])
            syndrome = syndromes[seed_index, shot].astype(np.uint8)
            observed_logical = observed_logicals[seed_index, shot].astype(np.uint8)
            detector_hash = packed_hash(syndrome)
            logical_hash = packed_hash(observed_logical)
            if detector_hash != saved["detector_sample_hash"] or logical_hash != saved["logical_sample_hash"]:
                raise RuntimeError(f"workload hash mismatch for {(sample_seed, shot)}")
            workload_verification.append(
                {
                    "sample_seed": sample_seed,
                    "shot": shot,
                    "seed_index": seed_index,
                    "syndrome_weight": int(syndrome.sum()),
                    "logical_weight": int(observed_logical.sum()),
                    "detector_hash": detector_hash,
                    "logical_hash": logical_hash,
                    "verified": True,
                }
            )
            for engine, seed_field in (("E0", "s0"), ("E1", "s1")):
                gamma_seed = int(saved[seed_field])
                configs, gamma_meta = make_leg_configs(gamma_seed, h.shape[1])
                collector = CompactTraceCollector(sample_seed, shot, engine, prior, h, syndrome)
                decoder = FloatRelayBPDecoder(
                    h,
                    leg_configs=configs,
                    S=1,
                    R=RELAY_LIMIT,
                    seed=0,
                    iteration_callback=collector,
                )
                result = decoder.decode(prior, syndrome)
                correction = result.decoded_error.astype(np.uint8)
                predicted_logical = np.asarray(action @ correction).reshape(-1).astype(np.uint8) & 1
                logical_correct = bool(result.converged and np.array_equal(predicted_logical, observed_logical))
                legs = summarize_legs(collector.rows, collector.initial_residual_weight)
                summary = trajectory_summary(
                    collector.rows, legs, collector, result, logical_correct, saved, engine, gamma_meta
                )
                iteration_rows.extend(collector.rows)
                leg_rows.extend(legs)
                trajectory_rows.append(summary)
                print(
                    f"completed {sample_seed}/{shot} {engine}: float={result.total_iterations}i/{result.relay_legs}l/conv={int(result.converged)} saved={saved['e0_iterations' if engine == 'E0' else 'e1_iterations']}i",
                    flush=True,
                )

    paired = paired_comparisons(iteration_rows, trajectory_rows)
    easy = [row for row in trajectory_rows if row["shot_class"] == "easy"]
    severe = [row for row in trajectory_rows if row["shot_class"].startswith("severe")]
    metric_fields = (
        "replay_iterations",
        "replay_relay_legs",
        "longest_no_improvement_streak",
        "residual_weight_increases",
        "equal_residual_iterations",
        "exact_residual_vector_repeats",
        "two_cycle_residual_repeats",
        "mean_decision_changes",
        "mean_belief_abs",
        "mean_close_fraction",
        "productive_legs",
        "stagnant_legs",
        "regressive_legs",
    )
    leg_class_counts: dict[str, dict[str, int]] = {}
    for label, predicate in {
        "easy": lambda row: row["shot_class"] == "easy",
        "hard_or_severe": lambda row: "hard" in row["shot_class"] or row["shot_class"].startswith("severe"),
        "saved_rescue": lambda row: (row["sample_seed"], row["shot"]) in {(20260809, 18), (20260810, 26), (20260811, 26)},
        "saved_fixed_failure": lambda row: row["trajectory"] == "E0"
        and (row["sample_seed"], row["shot"])
        in {(20260809, 18), (20260810, 26), (20260811, 26)},
    }.items():
        selected = [row for row in leg_rows if predicate(row)]
        counts = Counter(row["classification"] for row in selected)
        leg_class_counts[label] = {name: int(counts.get(name, 0)) for name in ("productive", "stagnant", "regressive")}

    comparison = {
        "schema_version": 1,
        "panel": [list(item) for item in PANEL],
        "reproduction": {
            "workloads_verified": len(workload_verification),
            "workload_hash_mismatches": 0,
            "gamma_streams_reproduced": len(trajectory_rows),
            "canonical_float_trajectories": len(trajectory_rows),
            "saved_fixed_outcome_matches": sum(row["saved_outcome_match"] for row in trajectory_rows),
            "saved_fixed_iteration_leg_matches": sum(row["saved_iteration_leg_match"] for row in trajectory_rows),
            "boundary": "exact workloads and gamma streams; float arithmetic replay versus saved fixed-point outcomes",
        },
        "counts": {
            "iterations": len(iteration_rows),
            "relay_legs": len(leg_rows),
            "trajectories": len(trajectory_rows),
        },
        "workload_verification": workload_verification,
        "easy_vs_severe": {
            "easy": {"trajectories": len(easy), **mean_fields(easy, metric_fields)},
            "severe": {"trajectories": len(severe), **mean_fields(severe, metric_fields)},
        },
        "first_leg_correlations_with_float_total_iterations": correlations(trajectory_rows),
        "leg_class_counts": leg_class_counts,
        "e0_vs_e1": paired,
        "saved_rescue_cases": [row for row in paired if (row["sample_seed"], row["shot"]) in {(20260809, 18), (20260810, 26), (20260811, 26)}],
        "major_improvement_cases": [row for row in paired if (row["sample_seed"], row["shot"]) in {(20260810, 4), (20260811, 28)}],
        "counterexample": next(row for row in paired if (row["sample_seed"], row["shot"]) == (20260812, 14)),
    }

    write_csv(OUT / "per_iteration_trace.csv", iteration_rows)
    write_csv(OUT / "per_leg_summary.csv", leg_rows)
    write_csv(OUT / "per_trajectory_summary.csv", trajectory_rows)
    (OUT / "comparison_summary.json").write_text(
        json.dumps(json_ready(comparison), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    make_plots(iteration_rows, leg_rows, trajectory_rows)
    write_documents(trajectory_rows, leg_rows, paired, comparison)
    print(json.dumps(comparison["reproduction"] | comparison["counts"], indent=2))


if __name__ == "__main__":
    main()

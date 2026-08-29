#!/usr/bin/env python3
"""Exact fixed-point trajectory analysis for the locked 13-shot panel."""

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
sys.path[:0] = [str(ROOT / "reference"), str(ROOT / "fpga/verification/parallel_n2")]

from fixedpoint import FixedConfig  # noqa: E402
from gamma_rng_reference import vector as hardware_gamma_vector  # noqa: E402
from relay_bp_fixed import FixedRelayBPDecoder, FixedRelayConfig, FixedRelayLegConfig  # noqa: E402


PACKAGE = ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
SAMPLES = ROOT / "results/circuit-level-multiseed/paired_samples.npz"
ARCHIVED = ROOT / "results/n1-vs-n2-hardware-latency/per_shot_results.csv"
FLOAT_SUMMARY = ROOT / "results/hard-shot-trajectory-analysis/per_trajectory_summary.csv"

PANEL = (
    (20260809, 31), (20260810, 15), (20260811, 6), (20260809, 2),
    (20260810, 22), (20260811, 25), (20260812, 14), (20260811, 28),
    (20260810, 4), (20260810, 9), (20260809, 18), (20260810, 26),
    (20260811, 26),
)
SHOT_CLASS = {
    (20260809, 31): "easy", (20260810, 15): "easy", (20260811, 6): "easy",
    (20260809, 2): "typical", (20260810, 22): "typical",
    (20260811, 25): "moderately_hard", (20260812, 14): "reverse_counterexample",
    (20260811, 28): "hard_major_improvement", (20260810, 4): "severe_success",
    (20260810, 9): "severe_success", (20260809, 18): "rescue",
    (20260810, 26): "rescue", (20260811, 26): "rescue",
}
RESCUES = {(20260809, 18), (20260810, 26), (20260811, 26)}
MARGINAL_NEAR_ZERO = 16  # one M=16 coefficient-scale unit
MEANINGFUL_RESIDUAL = 5
FROZEN_MOVEMENT = 2
CHURNING_MOVEMENT = 10
FIRST_LIMIT, LATER_LIMIT, RELAY_LIMIT = 80, 60, 32
V, C = 67752, 1728


def packed_hash(bits: np.ndarray) -> str:
    return hashlib.sha256(np.packbits(np.asarray(bits, dtype=np.uint8)).tobytes()).hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def load_problem() -> tuple[sparse.csr_matrix, sparse.csr_matrix, np.ndarray]:
    with np.load(PACKAGE / "edge_lists.npz") as data:
        de, oe = data["detector_edges"], data["observable_edges"]
    with np.load(PACKAGE / "faults.npz") as data:
        probabilities = data["probabilities"]
    h = sparse.csr_matrix((np.ones(len(de), np.uint8), (de[:, 1], de[:, 0])), shape=(C, V))
    action = sparse.csr_matrix((np.ones(len(oe), np.uint8), (oe[:, 1], oe[:, 0])), shape=(12, V))
    return h, action, np.log((1.0 - probabilities) / probabilities)


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def gamma_schedule(seed: int) -> tuple[tuple[FixedRelayLegConfig, ...], list[dict[str, int]]]:
    state = seed
    configs = [FixedRelayLegConfig(FIRST_LIMIT, gamma=0.125)]
    metadata = [{"leg": 1, "state": state, "words": 0, "accepted": 0, "rejected": 0}]
    for leg in range(2, RELAY_LIMIT + 1):
        values, accepted_words, state, rejected = hardware_gamma_vector(state, V)
        configs.append(FixedRelayLegConfig(LATER_LIMIT, gamma=np.asarray(values, dtype=float) / 16.0))
        metadata.append({"leg": leg, "state": state, "words": len(accepted_words) + rejected, "accepted": V, "rejected": rejected})
    return tuple(configs), metadata


class Collector:
    def __init__(self, seed: int, shot: int, engine: str, prior: np.ndarray, h: sparse.csr_matrix, syndrome: np.ndarray):
        self.seed, self.shot, self.engine, self.prior = seed, shot, engine, prior
        initial_decision = (np.rint(prior) <= 0).astype(np.uint8)
        predicted = np.asarray(h @ initial_decision).reshape(-1).astype(np.uint8) & 1
        self.prev_residual = predicted ^ syndrome
        self.prev_decision = initial_decision
        self.initial_residual = int(self.prev_residual.sum())
        self.best = self.initial_residual
        self.since_best = 0
        self.prev_saturations: Counter[str] = Counter()
        self.seen_residuals: Counter[str] = Counter({packed_hash(self.prev_residual): 1})
        self.rows: list[dict[str, Any]] = []
        self.marginal_site_hits = np.zeros(V, dtype=np.uint16)
        self.nu_site_hits = np.zeros(h.nnz, dtype=np.uint16)
        self.mu_site_hits = np.zeros(h.nnz, dtype=np.uint16)

    def __call__(self, event: dict[str, object]) -> None:
        residual = np.asarray(event["residual"], dtype=np.uint8)
        decision = np.asarray(event["decoded_error"], dtype=np.uint8)
        marginal = np.asarray(event["beliefs"], dtype=np.int64)
        bias = np.asarray(event["lambda_bias"], dtype=np.int64)
        nu = np.asarray(event["var_to_check"], dtype=np.int64)
        mu = np.asarray(event["check_to_var"], dtype=np.int64)
        gamma = np.asarray(event["gamma_int"], dtype=np.int64)
        saturation = Counter({k: int(v) for k, v in dict(event["saturation_counts"]).items()})
        delta_sat = saturation - self.prev_saturations
        self.prev_saturations = saturation
        weight = int(residual.sum()); previous_weight = int(self.prev_residual.sum())
        new_best = weight < self.best
        if new_best: self.best, self.since_best = weight, 0
        else: self.since_best += 1
        residual_distance = int(np.count_nonzero(residual ^ self.prev_residual))
        decision_changes = int(np.count_nonzero(decision ^ self.prev_decision))
        residual_hash = packed_hash(residual)
        repeated = self.seen_residuals[residual_hash] > 0
        self.seen_residuals[residual_hash] += 1
        marg_pos = marginal == 131071; marg_neg = marginal == -131072
        nu_sat = (nu == 131071) | (nu == -131072)
        mu_sat = (mu == 131071) | (mu == -131072)
        self.marginal_site_hits += (marg_pos | marg_neg)
        self.nu_site_hits += nu_sat
        self.mu_site_hits += mu_sat
        abs_m = np.abs(marginal)
        no_best = not new_best
        frozen = no_best and residual_distance <= FROZEN_MOVEMENT and decision_changes <= FROZEN_MOVEMENT
        churning = no_best and (residual_distance >= CHURNING_MOVEMENT or decision_changes >= CHURNING_MOVEMENT)
        self.rows.append({
            "sample_seed": self.seed, "shot": self.shot, "trajectory": self.engine,
            "shot_class": SHOT_CLASS[(self.seed, self.shot)],
            "relay_leg": int(event["leg_index"]) + 1, "iteration_in_leg": int(event["iteration"]),
            "global_iteration": int(event["global_iteration"]), "residual_weight": weight,
            "residual_delta": weight - previous_weight, "best_residual_so_far": self.best,
            "new_best": int(new_best), "iterations_since_best": self.since_best,
            "converged": int(bool(event["converged"])), "residual_vector_distance": residual_distance,
            "residual_exact_repeat": int(repeated), "residual_hash": residual_hash,
            "frozen_stagnation_step": int(frozen), "churning_stagnation_step": int(churning),
            "decision_weight": int(decision.sum()), "decision_changes": decision_changes,
            "candidate_weight": float(np.dot(decision, self.prior)),
            "marginal_min": int(marginal.min()), "marginal_max": int(marginal.max()),
            "marginal_mean": float(marginal.mean()), "marginal_mean_abs": float(abs_m.mean()),
            "marginal_median_abs": float(np.median(abs_m)),
            "marginal_zero_count": int(np.count_nonzero(marginal == 0)),
            "marginal_zero_fraction": float(np.mean(marginal == 0)),
            "marginal_near_zero_count": int(np.count_nonzero(abs_m <= MARGINAL_NEAR_ZERO)),
            "marginal_near_zero_fraction": float(np.mean(abs_m <= MARGINAL_NEAR_ZERO)),
            "marginal_sat_positive": int(marg_pos.sum()), "marginal_sat_negative": int(marg_neg.sum()),
            "marginal_sat_fraction": float(np.mean(marg_pos | marg_neg)),
            "bias_min": int(bias.min()), "bias_max": int(bias.max()),
            "bias_sat_count": int(np.count_nonzero((bias == 131071) | (bias == -131072))),
            "bias_sat_fraction": float(np.mean((bias == 131071) | (bias == -131072))),
            "bias_saturation_hits": int(delta_sat.get("lambda_bias", 0)),
            "nu_sat_count": int(nu_sat.sum()), "nu_sat_fraction": float(nu_sat.mean()),
            "nu_zero_count": int(np.count_nonzero(nu == 0)), "nu_zero_fraction": float(np.mean(nu == 0)),
            "nu_saturation_hits": int(delta_sat.get("variable_messages", 0)),
            "mu_sat_count": int(mu_sat.sum()), "mu_sat_fraction": float(mu_sat.mean()),
            "mu_zero_count": int(np.count_nonzero(mu == 0)), "mu_zero_fraction": float(np.mean(mu == 0)),
            "mu_saturation_hits": int(delta_sat.get("check_messages", 0)),
            "accumulator_saturation_hits": int(delta_sat.get("guard_accumulator", 0)),
            "marginal_saturation_hits": int(delta_sat.get("marginals", 0)),
            "gamma_min": int(gamma.min()), "gamma_max": int(gamma.max()),
            "gamma_mean": float(gamma.mean()), "gamma_negative": int(np.count_nonzero(gamma < 0)),
            "gamma_zero": int(np.count_nonzero(gamma == 0)), "gamma_positive": int(np.count_nonzero(gamma > 0)),
        })
        self.prev_residual = residual.copy(); self.prev_decision = decision.copy()


def leg_summaries(rows: list[dict[str, Any]], initial: int) -> list[dict[str, Any]]:
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows: groups[int(row["relay_leg"])].append(row)
    output, start, global_best = [], initial, initial
    for leg_index in sorted(groups):
        leg = groups[leg_index]; minimum = min(r["residual_weight"] for r in leg); end = leg[-1]["residual_weight"]
        new_best_improvement = max(0, global_best - minimum)
        if leg[-1]["converged"] or new_best_improvement >= MEANINGFUL_RESIDUAL: category = "productive"
        elif new_best_improvement > 0: category = "weak"
        elif end >= start + MEANINGFUL_RESIDUAL: category = "regressive"
        else: category = "stagnant"
        output.append({
            "sample_seed": leg[0]["sample_seed"], "shot": leg[0]["shot"], "trajectory": leg[0]["trajectory"],
            "shot_class": leg[0]["shot_class"], "relay_leg": leg_index, "starting_residual": start,
            "first_iteration_residual": leg[0]["residual_weight"], "minimum_residual": minimum,
            "ending_residual": end, "iterations_used": len(leg), "global_best_before": global_best,
            "global_best_after": min(global_best, minimum), "net_endpoint_improvement": start - end,
            "new_global_best_improvement": new_best_improvement, "decision_churn": sum(r["decision_changes"] for r in leg),
            "residual_vector_movement": sum(r["residual_vector_distance"] for r in leg),
            "frozen_stagnation_steps": sum(r["frozen_stagnation_step"] for r in leg),
            "churning_stagnation_steps": sum(r["churning_stagnation_step"] for r in leg),
            "marginal_saturation_hits": sum(r["marginal_saturation_hits"] for r in leg),
            "nu_saturation_hits": sum(r["nu_saturation_hits"] for r in leg),
            "mu_saturation_hits": sum(r["mu_saturation_hits"] for r in leg),
            "accumulator_saturation_hits": sum(r["accumulator_saturation_hits"] for r in leg),
            "mean_marginal_sat_fraction": float(np.mean([r["marginal_sat_fraction"] for r in leg])),
            "mean_marginal_near_zero_fraction": float(np.mean([r["marginal_near_zero_fraction"] for r in leg])),
            "converged": leg[-1]["converged"], "category": category,
        })
        start = end; global_best = min(global_best, minimum)
    return output


def early_fields(rows: list[dict[str, Any]], initial: int) -> dict[str, Any]:
    by_global = {r["global_iteration"]: r for r in rows}
    output: dict[str, Any] = {}
    for checkpoint in (5, 10, 20, 40):
        row = by_global.get(checkpoint)
        for metric in ("residual_weight", "best_residual_so_far", "iterations_since_best", "decision_changes", "marginal_near_zero_fraction", "marginal_sat_fraction"):
            output[f"i{checkpoint}_{metric}"] = None if row is None else row[metric]
        output[f"i{checkpoint}_residual_improvement"] = None if row is None else initial - row["residual_weight"]
        output[f"i{checkpoint}_cumulative_decision_churn"] = None if row is None else sum(r["decision_changes"] for r in rows[:checkpoint])
    first_leg = [r for r in rows if r["relay_leg"] == 1]
    end = first_leg[-1]
    output.update({
        "first_leg_end_residual": end["residual_weight"], "first_leg_residual_improvement": initial - end["residual_weight"],
        "first_leg_best_residual": min(r["residual_weight"] for r in first_leg),
        "first_leg_no_improvement_streak": end["iterations_since_best"],
        "first_leg_decision_churn": sum(r["decision_changes"] for r in first_leg),
        "first_leg_near_zero_fraction": end["marginal_near_zero_fraction"],
        "first_leg_marginal_sat_fraction": end["marginal_sat_fraction"],
    })
    return output


def trajectory_summary(rows: list[dict[str, Any]], legs: list[dict[str, Any]], collector: Collector, result: Any,
                       logical_correct: bool, archived: dict[str, str], engine: str,
                       rng_meta: list[dict[str, int]]) -> dict[str, Any]:
    prefix = "e0_" if engine == "E0" else "e1_"; used = int(result.relay_legs)
    rng_words = sum(m["words"] for m in rng_meta[:used]); accepted = sum(m["accepted"] for m in rng_meta[:used])
    final_state = rng_meta[used - 1]["state"]
    saved_weight = archived[prefix + "weight"]
    replay_weight = result.metadata.get("best_weight")
    weight_match = (saved_weight == "" and replay_weight is None) or (
        saved_weight != "" and replay_weight is not None and math.isclose(float(saved_weight), float(replay_weight), rel_tol=0, abs_tol=1e-9)
    )
    checks = {
        "convergence": int(result.converged) == int(archived[prefix + "syndrome_converged"]),
        "logical": int(logical_correct) == int(archived[prefix + "logical_correct"]),
        "iterations": int(result.total_iterations) == int(archived[prefix + "iterations"]),
        "legs": used == int(archived[prefix + "legs"]), "weight": weight_match,
        "final_rng_state": final_state == int(archived[prefix + "final_rng_state"]),
        "rng_words": rng_words == int(archived[prefix + "rng_words"]),
        "accepted_gamma": accepted == int(archived[prefix + "gamma_coefficients"]),
    }
    first_meaningful = next((r["global_iteration"] for r in rows if r["best_residual_so_far"] <= collector.initial_residual - MEANINGFUL_RESIDUAL), None)
    return {
        "sample_seed": collector.seed, "shot": collector.shot, "trajectory": engine,
        "shot_class": SHOT_CLASS[(collector.seed, collector.shot)], "gamma_seed": int(archived["s0" if engine == "E0" else "s1"]),
        "exact_reproduction": int(all(checks.values())), **{f"match_{k}": int(v) for k, v in checks.items()},
        "converged": int(result.converged), "logical_correct": int(logical_correct),
        "total_iterations": int(result.total_iterations), "relay_legs": used,
        "candidate_weight": replay_weight, "archived_cycles": int(archived[prefix + "result_cycles"]),
        "final_rng_state": final_state, "rng_words": rng_words, "accepted_gamma": accepted,
        "initial_residual": collector.initial_residual, "best_residual": min(r["residual_weight"] for r in rows),
        "iterations_to_first_meaningful_improvement": first_meaningful,
        "longest_no_best_improvement": max(r["iterations_since_best"] for r in rows),
        "total_no_improvement_iterations": sum(not r["new_best"] for r in rows),
        "residual_increases": sum(r["residual_delta"] > 0 for r in rows),
        "equal_residual_iterations": sum(r["residual_delta"] == 0 for r in rows),
        "residual_vector_movement": sum(r["residual_vector_distance"] for r in rows),
        "exact_residual_repeats": sum(r["residual_exact_repeat"] for r in rows),
        "mean_decision_churn": float(np.mean([r["decision_changes"] for r in rows])),
        "cumulative_decision_churn": sum(r["decision_changes"] for r in rows),
        "frozen_stagnation_steps": sum(r["frozen_stagnation_step"] for r in rows),
        "churning_stagnation_steps": sum(r["churning_stagnation_step"] for r in rows),
        "productive_legs": sum(r["category"] == "productive" for r in legs),
        "weak_legs": sum(r["category"] == "weak" for r in legs),
        "stagnant_legs": sum(r["category"] == "stagnant" for r in legs),
        "regressive_legs": sum(r["category"] == "regressive" for r in legs),
        "marginal_saturation_hits": sum(r["marginal_saturation_hits"] for r in rows),
        "nu_saturation_hits": sum(r["nu_saturation_hits"] for r in rows),
        "mu_saturation_hits": sum(r["mu_saturation_hits"] for r in rows),
        "accumulator_saturation_hits": sum(r["accumulator_saturation_hits"] for r in rows),
        "repeated_marginal_saturation_sites": int(np.count_nonzero(collector.marginal_site_hits >= 2)),
        "repeated_nu_saturation_sites": int(np.count_nonzero(collector.nu_site_hits >= 2)),
        "repeated_mu_saturation_sites": int(np.count_nonzero(collector.mu_site_hits >= 2)),
        "mean_marginal_saturation_fraction": float(np.mean([r["marginal_sat_fraction"] for r in rows])),
        "mean_marginal_near_zero_fraction": float(np.mean([r["marginal_near_zero_fraction"] for r in rows])),
        **early_fields(rows, collector.initial_residual),
    }


def pair_analysis(iterations: list[dict[str, Any]], legs: list[dict[str, Any]], trajectories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ir: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
    lr: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
    for r in iterations: ir[(r["sample_seed"], r["shot"], r["trajectory"])].append(r)
    for r in legs: lr[(r["sample_seed"], r["shot"], r["trajectory"])].append(r)
    tr = {(r["sample_seed"], r["shot"], r["trajectory"]): r for r in trajectories}; output=[]
    for seed, shot in (*sorted(RESCUES), (20260812, 14)):
        e0, e1 = ir[(seed, shot, "E0")], ir[(seed, shot, "E1")]
        divergence = next((a["global_iteration"] for a,b in zip(e0,e1) if a["residual_hash"] != b["residual_hash"] or a["decision_weight"] != b["decision_weight"]), None)
        def escape(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
            hit = next((r for r in rows if r["converged"]), None)
            if hit is None: return None
            prev = rows[max(0, hit["global_iteration"] - 6):hit["global_iteration"]]
            return {"iteration": hit["global_iteration"], "leg": hit["relay_leg"], "residual_before_5": prev[0]["residual_weight"],
                    "decision_churn_last_5": sum(r["decision_changes"] for r in prev), "near_zero_at_escape": hit["marginal_near_zero_fraction"],
                    "marginal_sat_at_escape": hit["marginal_sat_fraction"], "gamma_mean": hit["gamma_mean"], "gamma_negative": hit["gamma_negative"]}
        output.append({
            "sample_seed": seed, "shot": shot, "first_divergence_global_iteration": divergence,
            "first_disordered_leg_e0": lr[(seed,shot,"E0")][1] if len(lr[(seed,shot,"E0")])>1 else None,
            "first_disordered_leg_e1": lr[(seed,shot,"E1")][1] if len(lr[(seed,shot,"E1")])>1 else None,
            "e0_summary": tr[(seed,shot,"E0")], "e1_summary": tr[(seed,shot,"E1")],
            "e0_escape": escape(e0), "e1_escape": escape(e1),
        })
    return output


def correlations(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    fields = [k for k in rows[0] if k.startswith(("i5_","i10_","i20_","i40_","first_leg_"))] + ["initial_residual"]
    output={}
    for field in fields:
        pairs=[(float(r[field]),float(r["archived_cycles"])) for r in rows if r[field] not in (None,"")]
        output[field]=None if len(pairs)<3 or np.std([x for x,_ in pairs])==0 else float(np.corrcoef(np.asarray(pairs).T)[0,1])
    return output


def mean_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    fields=("total_iterations","relay_legs","longest_no_best_improvement","mean_decision_churn","churning_stagnation_steps",
            "productive_legs","weak_legs","stagnant_legs","regressive_legs","mean_marginal_saturation_fraction",
            "nu_saturation_hits","mu_saturation_hits","accumulator_saturation_hits","mean_marginal_near_zero_fraction")
    return {f:float(np.mean([float(r[f]) for r in rows])) for f in fields}


def make_plots(iterations: list[dict[str, Any]], legs: list[dict[str, Any]], trajectories: list[dict[str, Any]]) -> None:
    by:dict[tuple[int,int,str],list[dict[str,Any]]]=defaultdict(list)
    for r in iterations:by[(r["sample_seed"],r["shot"],r["trajectory"])].append(r)
    fig,axes=plt.subplots(3,1,figsize=(8,10))
    for ax,key in zip(axes,sorted(RESCUES)):
        for e in ("E0","E1"):
            rr=by[(key[0],key[1],e)];ax.plot([x["global_iteration"] for x in rr],[x["residual_weight"] for x in rr],label=e)
        ax.set_title(f"{key[0]}/{key[1]}");ax.grid(alpha=.25);ax.legend();ax.set_ylabel("Residual")
    axes[-1].set_xlabel("Iteration");fig.tight_layout();fig.savefig(OUT/"rescue_residual_trajectories.png",dpi=170);plt.close(fig)
    for e in ("E0","E1"):
        rr=by[(20260812,14,e)];plt.plot([x["global_iteration"] for x in rr],[x["residual_weight"] for x in rr],label=e)
    plt.legend();plt.grid(alpha=.25);plt.xlabel("Iteration");plt.ylabel("Residual");plt.tight_layout();plt.savefig(OUT/"reverse_counterexample.png",dpi=170);plt.close()
    def scatter(x,y,name,xlabel):
        plt.scatter([r[x] for r in trajectories],[r[y] for r in trajectories]);plt.xlabel(xlabel);plt.ylabel("Archived cycles");plt.grid(alpha=.25);plt.tight_layout();plt.savefig(OUT/name,dpi=170);plt.close()
    scatter("longest_no_best_improvement","archived_cycles","stagnation_vs_latency.png","Longest no-best-improvement streak")
    scatter("mean_decision_churn","archived_cycles","decision_churn_vs_latency.png","Mean decision churn")
    scatter("mean_marginal_saturation_fraction","archived_cycles","saturation_vs_latency.png","Mean marginal saturation fraction")
    scatter("first_leg_end_residual","archived_cycles","first_leg_vs_latency.png","First-leg ending residual")
    counts=Counter(r["category"] for r in legs);plt.bar(list(counts),list(counts.values()));plt.ylabel("Relay legs");plt.tight_layout();plt.savefig(OUT/"leg_category_distribution.png",dpi=170);plt.close()


def main() -> None:
    OUT.mkdir(parents=True,exist_ok=True);h,action,prior=load_problem();archived={(int(r["sample_seed"]),int(r["shot"])):r for r in load_csv(ARCHIVED)}
    iteration_rows=[];leg_rows=[];trajectory_rows=[];reproduction=[]
    with np.load(SAMPLES) as samples:
        seeds=samples["sample_seeds"]
        for sample_seed,shot in PANEL:
            index=int(np.flatnonzero(seeds==sample_seed)[0]);syndrome=samples["syndromes"][index,shot].astype(np.uint8);logical=samples["observed_logicals"][index,shot].astype(np.uint8);saved=archived[(sample_seed,shot)]
            if packed_hash(syndrome)!=saved["detector_sample_hash"] or packed_hash(logical)!=saved["logical_sample_hash"]:raise RuntimeError(f"workload mismatch {(sample_seed,shot)}")
            for engine,seed_field in (("E0","s0"),("E1","s1")):
                configs,rng_meta=gamma_schedule(int(saved[seed_field]));collector=Collector(sample_seed,shot,engine,prior,h,syndrome)
                decoder=FixedRelayBPDecoder(h,FixedRelayConfig(fixed=FixedConfig(b=18,g=4,M=16,clip=None,separate_scale=True),leg_configs=configs,S=1,R=32,seed=0),iteration_callback=collector)
                result=decoder.decode(prior,syndrome);decision=result.decoded_error.astype(np.uint8);pred_log=np.asarray(action@decision).reshape(-1).astype(np.uint8)&1;logical_correct=bool(result.converged and np.array_equal(pred_log,logical))
                legs=leg_summaries(collector.rows,collector.initial_residual);summary=trajectory_summary(collector.rows,legs,collector,result,logical_correct,saved,engine,rng_meta)
                iteration_rows.extend(collector.rows);leg_rows.extend(legs);trajectory_rows.append(summary);reproduction.append({k:summary[k] for k in summary if k.startswith("match_") or k in ("sample_seed","shot","trajectory","exact_reproduction")})
                print(f"completed {sample_seed}/{shot} {engine}: {result.total_iterations}i/{result.relay_legs}l exact={summary['exact_reproduction']}",flush=True)
    mismatches=[r for r in reproduction if not r["exact_reproduction"]]
    if mismatches: raise RuntimeError("archived reproduction gate failed: "+json.dumps(mismatches,indent=2))
    pairs=pair_analysis(iteration_rows,leg_rows,trajectory_rows)
    easy=[r for r in trajectory_rows if r["shot_class"]=="easy"];severe=[r for r in trajectory_rows if r["shot_class"] in {"severe_success","rescue"}];failed=[r for r in trajectory_rows if not r["converged"]];rescued=[r for r in trajectory_rows if (r["sample_seed"],r["shot"]) in RESCUES and r["trajectory"]=="E1"]
    threshold_sensitivity={str(t):Counter("productive" if (r["converged"] or r["new_global_best_improvement"]>=t) else "weak" if r["new_global_best_improvement"]>0 else "regressive" if r["ending_residual"]>=r["starting_residual"]+t else "stagnant" for r in leg_rows) for t in (1,5,10)}
    reproduction_summary={"panel":[list(x) for x in PANEL],"trajectories_reproduced":len(trajectory_rows),"total":26,"mismatches":mismatches,"iterations_traced":len(iteration_rows),"relay_legs_traced":len(leg_rows),"checks":reproduction,"thresholds":{"marginal_near_zero_abs_le":MARGINAL_NEAR_ZERO,"meaningful_residual_improvement":MEANINGFUL_RESIDUAL,"frozen_movement_le":FROZEN_MOVEMENT,"churning_movement_ge":CHURNING_MOVEMENT},"leg_threshold_sensitivity":{k:dict(v) for k,v in threshold_sensitivity.items()}}
    (OUT/"reproduction_summary.json").write_text(json.dumps(reproduction_summary,indent=2)+"\n")
    write_csv(OUT/"per_iteration_trace.csv",iteration_rows);write_csv(OUT/"per_leg_summary.csv",leg_rows);write_csv(OUT/"per_trajectory_summary.csv",trajectory_rows)
    (OUT/"rescue_case_analysis.json").write_text(json.dumps(pairs,indent=2)+"\n")
    aggregate={"easy":mean_metrics(easy),"severe":mean_metrics(severe),"failed":mean_metrics(failed),"rescued_e1":mean_metrics(rescued),"early_metric_correlations_with_archived_cycles":correlations(trajectory_rows),"leg_categories":dict(Counter(r["category"] for r in leg_rows))}
    (OUT/"analysis_summary.json").write_text(json.dumps(aggregate,indent=2)+"\n")
    make_plots(iteration_rows,leg_rows,trajectory_rows)
    print(json.dumps({"trajectories":26,"iterations":len(iteration_rows),"legs":len(leg_rows),"mismatches":len(mismatches)},indent=2))


if __name__=="__main__":main()

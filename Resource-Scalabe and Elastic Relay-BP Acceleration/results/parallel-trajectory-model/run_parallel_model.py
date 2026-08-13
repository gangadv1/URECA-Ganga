"""Parallel timing model for independent canonical b18 Relay-BP trajectories."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from scipy import sparse, stats

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "reference"
sys.path.insert(0, str(REF))
from fixedpoint import FixedConfig  # noqa: E402
from relay_bp_fixed import FixedRelayBPDecoder, FixedRelayConfig, FixedRelayLegConfig  # noqa: E402

OUT = Path(__file__).resolve().parent
TIER2 = ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
SAMPLES = ROOT / "results/circuit-level-multiseed/paired_samples.npz"
BASELINE = ROOT / "results/fixed-point-multiseed-lock/per_shot_results.csv"
SHOTS, B, M, G, BASE_SEED, SEED_STRIDE, ENGINES = 128, 18, 16, 4, 9100, 1_000_003, 4
CONFIG = {"first_gamma": 0.125, "later_interval": (-0.12, 0.54), "S": 1, "R": 32,
          "first_iterations": 80, "later_iterations": 60}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def problem():
    with np.load(TIER2 / "edge_lists.npz") as d:
        de, oe = d["detector_edges"], d["observable_edges"]
    with np.load(TIER2 / "faults.npz") as d:
        p = d["probabilities"]
    h = sparse.csr_matrix((np.ones(len(de), np.uint8), (de[:, 1], de[:, 0])), shape=(1728, 67752))
    a = sparse.csr_matrix((np.ones(len(oe), np.uint8), (oe[:, 1], oe[:, 0])), shape=(12, 67752))
    return h, a, p


def leg_configs():
    return (FixedRelayLegConfig(80, gamma=0.125),
            *(FixedRelayLegConfig(60, gamma_range=(-0.12, 0.54)) for _ in range(31)))


def run_engine_seed(engine: int, seed_index: int, sample_seed: int):
    h, action, probabilities = problem(); priors = np.log((1 - probabilities) / probabilities)
    with np.load(SAMPLES) as d:
        syndromes, logicals = d["syndromes"][seed_index], d["observed_logicals"][seed_index]
    rows, packed = [], []
    for shot in range(SHOTS):
        decoder_seed = BASE_SEED + shot + engine * SEED_STRIDE
        result = FixedRelayBPDecoder(h, FixedRelayConfig(
            fixed=FixedConfig(b=B, g=G, M=M, clip=None, separate_scale=True),
            leg_configs=leg_configs(), S=1, R=32, seed=decoder_seed)).decode(priors, syndromes[shot])
        decision = result.decoded_error
        syndrome_valid = bool(np.array_equal(np.asarray(h @ decision).reshape(-1) & 1, syndromes[shot]))
        logical_valid = bool(np.array_equal(np.asarray(action @ decision).reshape(-1) & 1, logicals[shot]))
        rows.append({"sample_seed": sample_seed, "shot": shot, "engine": engine,
                     "decoder_seed": decoder_seed, "iterations": result.total_iterations,
                     "relay_legs": result.relay_legs, "syndrome_converged": int(syndrome_valid),
                     "logically_correct": int(syndrome_valid and logical_valid),
                     "syndrome_valid_logical_error": int(syndrome_valid and not logical_valid),
                     "selected_weight": "" if result.metadata["best_weight"] is None else float(result.metadata["best_weight"])})
        packed.append(np.packbits(decision, bitorder="little"))
    return rows, np.stack(packed)


def summarize_parallel(rows, corrections):
    by_key = {(int(r["sample_seed"]), int(r["shot"]), int(r["engine"])): r for r in rows}
    sample_seeds = sorted({int(r["sample_seed"]) for r in rows})
    per_policy, summary = [], []
    for n in (1, 2, 4):
        for seed in sample_seeds:
            for shot in range(SHOTS):
                group = [by_key[(seed, shot, e)] for e in range(n)]
                successful = [r for r in group if int(r["syndrome_converged"])]
                if successful:
                    latency = min(int(r["iterations"]) for r in successful)
                    tied = [r for r in successful if int(r["iterations"]) == latency]
                    winner = min(tied, key=lambda r: int(r["engine"]))
                else:
                    latency = max(int(r["iterations"]) for r in group); winner = min(group, key=lambda r: int(r["engine"]))
                full_work = sum(int(r["iterations"]) for r in group)
                post_win_waste = sum(max(0, int(r["iterations"]) - latency) for r in group)
                correction = corrections[(seed, int(winner["engine"]))][shot]
                base_correction = corrections[(seed, 0)][shot]
                per_policy.append({
                    "N": n, "sample_seed": seed, "shot": shot, "winner_engine": int(winner["engine"]),
                    "parallel_iterations": latency, "syndrome_converged": int(winner["syndrome_converged"]),
                    "logically_correct": int(winner["logically_correct"]),
                    "syndrome_valid_logical_error": int(winner["syndrome_valid_logical_error"]),
                    "selected_weight": winner["selected_weight"],
                    "baseline_iterations": int(group[0]["iterations"]),
                    "rescued_vs_engine0": int(not int(group[0]["syndrome_converged"]) and int(winner["syndrome_converged"])),
                    "selected_correction_differs_from_engine0": int(not np.array_equal(correction, base_correction)),
                    "full_counterfactual_engine_iterations": full_work,
                    "post_winner_iterations_avoided_by_cancellation": post_win_waste,
                    "post_winner_waste_fraction_without_cancellation": post_win_waste / full_work,
                    "early_stop_compute_cycles": n * latency,
                    "early_stop_nonwinner_work_fraction": 0.0 if n == 1 else (n - 1) / n,
                })
        g = [r for r in per_policy if r["N"] == n]; its = np.asarray([r["parallel_iterations"] for r in g])
        base = np.asarray([r["baseline_iterations"] for r in g])
        logical = sum(r["logically_correct"] for r in g); base_logical = sum(by_key[(r["sample_seed"], r["shot"], 0)]["logically_correct"] for r in g)
        fixed_only = sum(r["logically_correct"] and not int(by_key[(r["sample_seed"], r["shot"], 0)]["logically_correct"]) for r in g)
        base_only = sum(not r["logically_correct"] and int(by_key[(r["sample_seed"], r["shot"], 0)]["logically_correct"]) for r in g)
        discordant = fixed_only + base_only
        summary.append({
            "N": n, "shots": len(g), "syndrome_converged": sum(r["syndrome_converged"] for r in g),
            "logical_successes": logical, "logical_success_difference_vs_engine0": logical - base_logical,
            "syndrome_valid_logical_errors": sum(r["syndrome_valid_logical_error"] for r in g),
            "average_iterations": float(np.mean(its)), "p50_iterations": float(np.percentile(its, 50)),
            "p90_iterations": float(np.percentile(its, 90)), "p99_iterations": float(np.percentile(its, 99)),
            "maximum_iterations": int(np.max(its)), "average_reduction_vs_N1": float(1 - np.mean(its) / np.mean(base)),
            "p99_reduction_vs_N1": float(1 - np.percentile(its, 99) / np.percentile(base, 99)),
            "rescued_shots_vs_engine0": sum(r["rescued_vs_engine0"] for r in g),
            "selected_corrections_differing_from_engine0": sum(r["selected_correction_differs_from_engine0"] for r in g),
            "average_selected_weight": float(np.mean([float(r["selected_weight"]) for r in g if r["selected_weight"] != ""])),
            "mean_post_winner_waste_fraction_without_cancellation": float(np.mean([r["post_winner_waste_fraction_without_cancellation"] for r in g])),
            "early_stop_nonwinner_work_fraction": 0.0 if n == 1 else (n - 1) / n,
            "paired_logical_exact_pvalue": 1.0 if discordant == 0 else float(stats.binomtest(min(fixed_only, base_only), discordant, 0.5).pvalue),
        })
    return per_policy, summary


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with np.load(SAMPLES) as d: seeds = [int(v) for v in d["sample_seeds"]]
    rows, corrections = [], {}
    tasks = [(e, i, seed) for e in range(ENGINES) for i, seed in enumerate(seeds)]
    with ProcessPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(run_engine_seed, *task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]; r, packed = future.result(); rows.extend(r); corrections[(task[2], task[0])] = packed
            print("completed", task, flush=True)
    rows.sort(key=lambda r: (r["sample_seed"], r["shot"], r["engine"]))
    with (OUT / "per_engine_results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    policy, summary = summarize_parallel(rows, corrections)
    with (OUT / "per_shot_parallel_results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=policy[0].keys()); w.writeheader(); w.writerows(policy)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    np.savez_compressed(OUT / "packed_corrections.npz", **{f"seed_{s}_engine_{e}": a for (s, e), a in corrections.items()})
    manifest = {"study": "parallel independent canonical b18 Relay-BP trajectory timing model",
                "shots": len(seeds) * SHOTS, "sample_seeds": seeds, "engine_count_modeled": ENGINES,
                "engine_seed": f"{BASE_SEED} + shot + engine*{SEED_STRIDE}", "configuration": CONFIG,
                "format": {"b": B, "guard_bits": G, "M": M, "P_hardware_assumption": 4},
                "timing_unit": "canonical fixed decoder iterations; assumes identical P=4 engines and no shared-memory stalls",
                "tie_break": "lowest engine index among syndrome-valid candidates completing at the same iteration",
                "hashes": {"decoder": sha(REF / "relay_bp_fixed.py"), "samples": sha(SAMPLES), "tier2": sha(TIER2 / "manifest.json")},
                "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT.parent, text=True).strip()}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__": main()

#!/usr/bin/env python3
"""Canonical N=1,2,4 trajectory archive and joint BA2 N x P sweep."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
N1_DIR = ROOT / "results/n1-vs-n2-hardware-latency"
SAMPLES = ROOT / "results/circuit-level-multiseed/paired_samples.npz"
CANONICAL_ROWS = N1_DIR / "per_shot_results.csv"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


canonical = load_module("canonical_n1_n2", N1_DIR / "run_study.py")
p_sweep = load_module("validated_p_sweep", ROOT / "results/folding-factor-sweep/run_p_sweep.py")

ENGINE_COUNT = 4
N_VALUES = (1, 2, 4)
P_VALUES = (2, 4, 8)
SPLITMIX_TRAJECTORY_DOMAIN = 0xD1B54A32D192ED03


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def trajectory_seed(sample_seed: int, shot: int, engine: int) -> int:
    """Keep canonical s0/s1 seeds and extend their splitmix recurrence."""
    seed = canonical.seeds(sample_seed, shot)[0]
    for _ in range(engine):
        seed = canonical.splitmix(seed ^ SPLITMIX_TRAJECTORY_DOMAIN)
    return seed


def load_jobs():
    with np.load(SAMPLES) as data:
        sample_seeds = np.asarray(data["sample_seeds"])
        syndromes = np.asarray(data["syndromes"])
        logicals = np.asarray(data["observed_logicals"])
    archive = list(csv.DictReader(CANONICAL_ROWS.open(newline="")))
    if len(archive) != 128:
        raise RuntimeError(f"Expected 128 canonical rows, found {len(archive)}")
    jobs = []
    for row in archive:
        sample_seed, shot = int(row["sample_seed"]), int(row["shot"])
        sample_index = int(np.flatnonzero(sample_seeds == sample_seed)[0])
        syndrome = syndromes[sample_index, shot].astype(np.uint8)
        logical = logicals[sample_index, shot].astype(np.uint8)
        detector_hash = hashlib.sha256(np.packbits(syndrome).tobytes()).hexdigest()
        logical_hash = hashlib.sha256(np.packbits(logical).tobytes()).hexdigest()
        if detector_hash != row["detector_sample_hash"] or logical_hash != row["logical_sample_hash"]:
            raise RuntimeError(f"Frozen STIM hash mismatch for {sample_seed}/{shot}")
        jobs.append((sample_index, shot, sample_seed, syndrome, logical, row))
    return jobs


def decode_job(job):
    sample_index, shot, sample_seed, syndrome, logical, _ = job
    h, action, priors = canonical.load_problem()
    trajectories = []
    for engine in range(ENGINE_COUNT):
        seed = trajectory_seed(sample_seed, shot, engine)
        result = canonical.decode_one(h, action, priors, syndrome, logical, seed)
        trajectories.append(
            {
                "sample_seed": sample_seed,
                "seed_index": sample_index,
                "shot": shot,
                "engine": engine,
                "decoder_seed": seed,
                "syndrome_sample_hash": hashlib.sha256(np.packbits(syndrome).tobytes()).hexdigest(),
                "logical_sample_hash": hashlib.sha256(np.packbits(logical).tobytes()).hexdigest(),
                "syndrome_converged": result["syndrome_converged"],
                "logical_correct": result["logical_correct"],
                "syndrome_valid_logical_error": result["syndrome_valid_logical_error"],
                "non_convergence": result["non_convergence"],
                "iterations": result["iterations"],
                "relay_legs": result["legs"],
                "weight": result["weight"],
                "natural_cycles": result["natural_cycles"],
                "result_cycles": result["result_cycles"],
                "rng_words": result["rng_words"],
                "gamma_coefficients": result["gamma_coefficients"],
                "initial_rng_state": result["initial_rng_state"],
                "final_rng_state": result["final_rng_state"],
            }
        )
    return trajectories


def canonical_selection(trajectories):
    successes = [(int(row["result_cycles"]), int(row["engine"])) for row in trajectories if int(row["syndrome_converged"])]
    return min(successes)[1] if successes else -1


def validate_against_canonical(trajectories, canonical_rows):
    expected = {(int(row["sample_seed"]), int(row["shot"])): row for row in canonical_rows}
    mismatches = []
    for group in trajectories:
        key = (int(group[0]["sample_seed"]), int(group[0]["shot"]))
        row = expected[key]
        selected = canonical_selection(group[:2])
        checks = {
            "engine0_convergence": int(group[0]["syndrome_converged"]) == int(row["e0_syndrome_converged"]),
            "engine0_logical": int(group[0]["logical_correct"]) == int(row["e0_logical_correct"]),
            "engine0_iterations": int(group[0]["iterations"]) == int(row["e0_iterations"]),
            "engine0_legs": int(group[0]["relay_legs"]) == int(row["e0_legs"]),
            "engine0_result_cycles": int(group[0]["result_cycles"]) == int(row["e0_result_cycles"]),
            "engine1_convergence": int(group[1]["syndrome_converged"]) == int(row["e1_syndrome_converged"]),
            "engine1_logical": int(group[1]["logical_correct"]) == int(row["e1_logical_correct"]),
            "engine1_iterations": int(group[1]["iterations"]) == int(row["e1_iterations"]),
            "engine1_legs": int(group[1]["relay_legs"]) == int(row["e1_legs"]),
            "engine1_result_cycles": int(group[1]["result_cycles"]) == int(row["e1_result_cycles"]),
            "n2_winner": selected == int(row["winner"]),
            "n1_modeled_base": int(group[0]["result_cycles"]) == int(row["n1_cycles"]),
            "n2_modeled_base": (min(int(group[i]["result_cycles"]) for i in (0, 1) if int(group[i]["syndrome_converged"])) if selected >= 0 else max(int(group[i]["result_cycles"]) for i in (0, 1))) == int(row["n2_cycles"]),
        }
        for check, passed in checks.items():
            if not passed:
                mismatches.append({"sample_seed": key[0], "shot": key[1], "check": check})
    return mismatches


def write_csv(path: Path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def phase_totals(phases, iterations, legs, processing_lanes):
    counts = {"requested": 0, "retries": 0, "issued": 0, "useful": 0, "active": 0, "full": 0}
    for phase_name, repetitions in (("check", iterations), ("variable", iterations), ("convergence", iterations), ("relay_init", legs)):
        phase = phases[phase_name]
        counts["requested"] += repetitions * int(phase["logical_accesses"])
        counts["retries"] += repetitions * int(phase["retry_subsets"])
        counts["issued"] += repetitions * int(phase["issued_groups"])
        counts["useful"] += repetitions * int(phase["issued_groups"] - phase["retry_subsets"])
        counts["active"] += repetitions * float(phase["mean_active_lanes"] * phase["issued_groups"])
        counts["full"] += repetitions * int(phase["lane_hist"][str(processing_lanes)])
    return counts


def cycle_metrics(phases, trajectory, processing_lanes):
    iterations, legs = int(trajectory["iterations"]), int(trajectory["relay_legs"])
    iteration_cycles = sum(int(phases[name]["estimated_cycles"]) for name in ("check", "variable", "convergence"))
    cycles = iterations * iteration_cycles + legs * int(phases["relay_init"]["estimated_cycles"])
    counts = phase_totals(phases, iterations, legs, processing_lanes)
    groups = counts["issued"]
    counts.update(
        modeled_cycles=cycles,
        iterations=iterations,
        relay_legs=legs,
        mean_active=(counts["active"] / groups) if groups else 0.0,
        lane_utilization=(counts["active"] / groups / processing_lanes) if groups else 0.0,
        full_fraction=(counts["full"] / groups) if groups else 0.0,
    )
    return counts


def run_joint(trajectories, phases_by_p):
    by_key = {(int(row["sample_seed"]), int(row["shot"]), int(row["engine"])): row for group in trajectories for row in group}
    per_shot = []
    summary = []
    shot_keys = sorted({(int(row["sample_seed"]), int(row["shot"])) for group in trajectories for row in group})
    for n in N_VALUES:
        for p in P_VALUES:
            phases = phases_by_p[p]
            for sample_seed, shot in shot_keys:
                candidates = [by_key[(sample_seed, shot, engine)] for engine in range(n)]
                scored = [(cycle_metrics(phases, row, p)["modeled_cycles"], int(row["engine"])) for row in candidates if int(row["syndrome_converged"])]
                winner = min(scored)[1] if scored else -1
                selected = by_key[(sample_seed, shot, winner)] if winner >= 0 else min(candidates, key=lambda row: int(row["result_cycles"]))
                metrics = cycle_metrics(phases, selected, p)
                per_shot.append({"N": n, "P": p, "sample_seed": sample_seed, "shot": shot, "winner_engine": winner,
                                 "converged": int(selected["syndrome_converged"]), "logical_failure": int(selected["syndrome_valid_logical_error"]),
                                 "logical_correct": int(selected["logical_correct"]), "modeled_cycles": metrics["modeled_cycles"],
                                 "relay_bp_iterations": metrics["iterations"], "relay_legs": metrics["relay_legs"],
                                 "useful_decoder_operations": metrics["useful"], "requested_memory_accesses": metrics["requested"],
                                 "bank_conflict_retries": metrics["retries"], "mean_active_P_lanes": metrics["mean_active"],
                                 "lane_utilization": metrics["lane_utilization"], "full_P_lane_fraction": metrics["full_fraction"],
                                 "total_available_lanes": n * p})
            rows = [r for r in per_shot if int(r["N"]) == n and int(r["P"]) == p]
            cycles = np.asarray([r["modeled_cycles"] for r in rows], dtype=float)
            def mean(key): return float(np.mean([float(r[key]) for r in rows]))
            summary.append({"N": n, "P": p, "convergence_count": sum(r["converged"] for r in rows),
                            "logical_failures": sum(r["logical_failure"] for r in rows), "mean_modeled_cycles": float(cycles.mean()),
                            "median_modeled_cycles": float(np.percentile(cycles, 50)), "p95_modeled_cycles": float(np.percentile(cycles, 95)),
                            "p99_modeled_cycles": float(np.percentile(cycles, 99)), "mean_relay_bp_iterations": mean("relay_bp_iterations"),
                            "mean_relay_legs": mean("relay_legs"), "total_useful_decoder_operations": sum(r["useful_decoder_operations"] for r in rows),
                            "mean_useful_decoder_operations": mean("useful_decoder_operations"), "total_requested_memory_accesses": sum(r["requested_memory_accesses"] for r in rows),
                            "mean_requested_memory_accesses": mean("requested_memory_accesses"), "total_bank_conflict_retries": sum(r["bank_conflict_retries"] for r in rows),
                            "mean_bank_conflict_retries": mean("bank_conflict_retries"), "mean_active_P_lanes": mean("mean_active_P_lanes"),
                            "lane_utilization": mean("lane_utilization"), "full_P_lane_fraction": mean("full_P_lane_fraction"),
                            "total_available_lanes": n * p})
    base = next(r for r in summary if r["N"] == 1 and r["P"] == 2)
    lookup = {(r["N"], r["P"]): r for r in summary}
    for row in summary:
        row["speedup_vs_N1_P2"] = base["mean_modeled_cycles"] / row["mean_modeled_cycles"]
        row["lane_cycle_cost"] = row["total_available_lanes"] * row["mean_modeled_cycles"]
        previous_n = lookup.get((row["N"] // 2, row["P"])) if row["N"] > 1 else None
        previous_p = lookup.get((row["N"], row["P"] // 2)) if row["P"] > 2 else None
        row["cycle_reduction_increasing_N_percent"] = "" if previous_n is None else 100.0 * (previous_n["mean_modeled_cycles"] - row["mean_modeled_cycles"]) / previous_n["mean_modeled_cycles"]
        row["cycle_reduction_increasing_P_percent"] = "" if previous_p is None else 100.0 * (previous_p["mean_modeled_cycles"] - row["mean_modeled_cycles"]) / previous_p["mean_modeled_cycles"]
        row["improvement_per_added_trajectory"] = "" if previous_n is None else (previous_n["mean_modeled_cycles"] - row["mean_modeled_cycles"]) / (row["N"] - previous_n["N"])
        row["improvement_per_added_processing_lane"] = "" if previous_p is None else (previous_p["mean_modeled_cycles"] - row["mean_modeled_cycles"]) / (row["total_available_lanes"] - previous_p["total_available_lanes"])
    return summary, per_shot


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = load_jobs()
    trajectories = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(decode_job, job) for job in jobs]
        for index, future in enumerate(as_completed(futures), 1):
            trajectories.extend(future.result())
            print(f"decoded {index}/{len(futures)} shots", flush=True)
    trajectories.sort(key=lambda row: (int(row["sample_seed"]), int(row["shot"]), int(row["engine"])))
    keys = sorted({(int(row["sample_seed"]), int(row["shot"])) for row in trajectories})
    grouped = [[row for row in trajectories if int(row["sample_seed"]) == seed and int(row["shot"]) == shot] for seed, shot in keys]
    mismatches = validate_against_canonical(grouped, list(csv.DictReader(CANONICAL_ROWS.open(newline=""))))
    validation = {"shots": len(grouped), "engine0_exact": not any("engine0" in x["check"] for x in mismatches), "engine1_exact": not any("engine1" in x["check"] for x in mismatches), "n2_exact": not any(x["check"] in ("n2_winner", "n2_modeled_base") for x in mismatches), "mismatch_count": len(mismatches), "mismatches": mismatches}
    (OUT / "validation_report.json").write_text(json.dumps(validation, indent=2) + "\n")
    if mismatches:
        raise RuntimeError(f"Canonical reproduction failed with {len(mismatches)} mismatches; no sweep accepted")
    write_csv(OUT / "canonical_trajectories.csv", trajectories)
    archive_manifest = {"status": "complete", "shots": 128, "engines": [0, 1, 2, 3], "N_values": list(N_VALUES), "decoder_source": str((N1_DIR / "run_study.py").relative_to(ROOT)), "sample_hash": sha256(SAMPLES), "seed_extension": "engine 0 is canonical s0; each later engine applies splitmix(seed ^ 0xD1B54A32D192ED03), preserving canonical engine 1", "validation": validation}
    (OUT / "archive_manifest.json").write_text(json.dumps(archive_manifest, indent=2) + "\n")
    graph = p_sweep.ba.load()
    _, phases, invariants = p_sweep.one_graph(graph, "canonical", True)
    phases_by_p = {p: phases[(p, "BA2")] for p in P_VALUES}
    summary, per_shot = run_joint(grouped, phases_by_p)
    write_csv(OUT / "joint_summary.csv", summary)
    write_csv(OUT / "joint_per_shot.csv", per_shot)
    best = min(summary, key=lambda row: (row["mean_modeled_cycles"], row["p95_modeled_cycles"], row["p99_modeled_cycles"]))
    efficient = min(summary, key=lambda row: (row["lane_cycle_cost"], row["mean_modeled_cycles"]))
    report = ["# Canonical Relay-BP N x P joint sweep", "", "All cycle values below are MODELED software-cycle values, not measured FPGA latency.", "", "## Validation", f"The frozen 128-shot STIM workload was hash-checked. Engine 0 reproduction: **exact**. Engine 1 and canonical N=2 selection reproduction: **exact**. Mismatches: **0**.", "", "## Joint model", "Each row uses the same selected trajectory, shot, BA2 layout, and folding model for its N/P point. N selects engines 0..N-1 by the canonical first syndrome-valid completion rule; P selects the validated BA2-P2, BA2-P4, or BA2-P8 phase model. Useful decoder operations are successful issued access groups (`issued_groups - bank_conflict_retries`); requested accesses and retries remain separate.", "", "## Results", "| N | P | Mean modeled cycles | P95 | Speedup vs N1/P2 | Lane-cycle cost |", "|---:|---:|---:|---:|---:|---:|"]
    report += [f"| {r['N']} | {r['P']} | {r['mean_modeled_cycles']:.1f} | {r['p95_modeled_cycles']:.1f} | {r['speedup_vs_N1_P2']:.4f} | {r['lane_cycle_cost']:.1f} |" for r in summary]
    report += ["", "## Conclusion", f"Absolute lowest modeled latency: **N={best['N']}, P={best['P']}** ({best['mean_modeled_cycles']:.1f} mean modeled cycles).", f"Best efficiency by lane-cycle cost: **N={efficient['N']}, P={efficient['P']}** ({efficient['lane_cycle_cost']:.1f}).", "Diminishing returns are identified from the reported fixed-P N transitions and fixed-N P transitions: a transition is diminishing when its cycle reduction per added trajectory or lane is lower than the preceding transition. See `joint_summary.csv` for the exact calculations.", "No FPGA resource, FPGA latency, power, DSP, LUT, FF, BRAM, or Fmax claim is made."]
    (OUT / "joint_report.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"validation": validation, "best_latency": best, "best_efficiency": efficient, "invariants": invariants}, indent=2))


if __name__ == "__main__":
    main()
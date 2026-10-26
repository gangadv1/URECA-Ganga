"""Read archived trajectories; never import or run a decoder.

Bounds assume simultaneous dedicated engines, no new stalls, and cancellation
does not delay an engine beyond its uncancelled natural completion. They do NOT
assume immediate cancellation or a particular request/acknowledgement delay.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
PHASE_KEYS = ("check", "variable", "convergence", "relay_init")


def account(row, n, p, phase_costs):
    """Return modeled cycles and conservative occupancy bounds, not useful ops."""
    if n < 1 or p < 1:
        raise ValueError("N and P must be positive")
    engines = []
    for i in range(n):
        prefix = f"e{i}_"
        e = {key: int(row[prefix + key]) for key in
             ("natural_cycles", "result_cycles", "iterations", "legs", "syndrome_converged")}
        e["phase_occupancy"] = (
            e["iterations"] * sum(phase_costs[k] for k in PHASE_KEYS[:3])
            + e["legs"] * phase_costs["relay_init"])
        if not (0 <= e["phase_occupancy"] <= e["natural_cycles"]
                and 0 <= e["result_cycles"] <= e["natural_cycles"]
                and e["syndrome_converged"] in (0, 1)):
            raise ValueError("Invalid engine timing/counts")
        engines.append(e)
    successes = [(e["result_cycles"], i) for i, e in enumerate(engines)
                 if e["syndrome_converged"]]
    completion, winner = min(successes) if successes else (
        max(e["result_cycles"] for e in engines), -1)
    # Completed failures and the winning engine retain their complete execution.
    # Other engines may execute anywhere between the selection instant and their
    # natural stop. No phase boundary position can be inferred from totals.
    elapsed_lower = elapsed_upper = phase_lower = phase_upper = 0
    quiescent_lower = quiescent_upper = completion
    for i, e in enumerate(engines):
        natural, busy = e["natural_cycles"], e["phase_occupancy"]
        fixed = winner < 0 or i == winner or natural <= completion
        stop_lower = natural if fixed else min(natural, completion)
        stop_upper = natural
        elapsed_lower += stop_lower
        elapsed_upper += stop_upper
        # Unknown placement of phase-controller occupancy within [0,natural):
        # at most natural-stop_lower phase cycles can lie after stop_lower.
        phase_lower += busy if fixed else max(0, busy - (natural - stop_lower))
        phase_upper += busy
        quiescent_lower = max(quiescent_lower, stop_lower)
        quiescent_upper = max(quiescent_upper, stop_upper)
    return {
        "N": n, "P": p, "winner_engine": winner,
        "same_cycle_successes": sum(t == completion for t, _ in successes),
        "all_fail": int(winner < 0), "ensemble_completion_cycles": completion,
        "uncancelled_natural_work": sum(e["natural_cycles"] for e in engines),
        "cancellation_aware_executed_work": None,
        "executed_work_status": "unsupported_without_phase_and_issue_events",
        "executed_engine_elapsed_cycles_lower_bound": elapsed_lower,
        "executed_engine_elapsed_cycles_upper_bound": elapsed_upper,
        "executed_phase_controller_cycles_lower_bound": phase_lower,
        "executed_phase_controller_cycles_upper_bound": phase_upper,
        "provisioned_lane_cycles": n * p * completion,
        "ensemble_quiescence_cycles_lower_bound": quiescent_lower,
        "ensemble_quiescence_cycles_upper_bound": quiescent_upper,
        "post_result_quiescence_overhead_cycles_lower_bound": quiescent_lower - completion,
        "post_result_quiescence_overhead_cycles_upper_bound": quiescent_upper - completion,
        "cancellation_ack_cycles": None,
        "cancellation_drain_cycles": None,
        "quantity_kind": "modeled_bounds_not_hardware_measurements",
    }


def analyze(source, output):
    source, output = source.resolve(), output.resolve()
    manifest_path = source / "manifest.json"
    csv_path = source / "per_shot_results.csv"
    manifest = json.loads(manifest_path.read_text())
    ns = manifest["trajectory_counts"]
    p = manifest["configuration"]["P"]
    phases = manifest["cycle_model"]
    with csv_path.open(newline="") as f:
        archived = list(csv.DictReader(f))
    if len(archived) != manifest["shots"] or len({(r["sample_seed"], r["shot"])
                                                for r in archived}) != len(archived):
        raise ValueError("Shot count or uniqueness mismatch")
    results = []
    for row in archived:
        for n in ns:
            result = account(row, n, p, phases)
            if (result["ensemble_completion_cycles"] != int(row[f"n{n}_cycles"])
                    or result["winner_engine"] != int(row[f"n{n}_winner"])
                    or result["uncancelled_natural_work"] != int(row[f"n{n}_active_work"])):
                raise ValueError("Canonical latency/winner/natural-work regression")
            result.update(sample_seed=int(row["sample_seed"]), shot=int(row["shot"]))
            results.append(result)
    # Require a fresh directory: no archived or previous analysis can be overwritten.
    output.mkdir(parents=True, exist_ok=False)
    with (output / "per_shot_accounting.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    numeric = [k for k, v in results[0].items() if isinstance(v, int)
               and k not in ("N", "P", "sample_seed", "shot", "winner_engine")]
    summary = {f"n{n}": {k: statistics.mean(r[k] for r in results if r["N"] == n)
                         for k in numeric} for n in ns}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    provenance = {
        "source_directory": str(source), "shots": len(archived),
        "trajectory_counts": ns, "P": p,
        "input_sha256": {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                          for f in (manifest_path, csv_path)},
        "analysis_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "phase_costs": {k: phases[k] for k in PHASE_KEYS},
        "assumptions": ["Simultaneous launch with P dedicated lanes per engine",
                        "No new memory/resource stalls introduced by cancellation",
                        "Engine stop/quiescence no later than natural completion",
                        "No exact request, acknowledgement or drain timing inferred"],
        "historical_active_work": "N-scaling sum of natural runtimes; historical N1/N2 cancellation model remains separate",
        "quantity_kind": "modeled_bounds_not_hardware_measurements",
    }
    (output / "analysis_manifest.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "results/n-scaling-canonical")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent / "analysis_output")
    args = parser.parse_args()
    print(json.dumps(analyze(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()

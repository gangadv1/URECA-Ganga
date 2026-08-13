"""Analyze bounded-window and multi-candidate policies from saved trajectories."""
import csv, json
from pathlib import Path
import numpy as np

OUT = Path(__file__).resolve().parent
rows = list(csv.DictReader((OUT / "per_engine_results.csv").open()))
groups = {}
for row in rows:
    groups.setdefault((int(row["sample_seed"]), int(row["shot"])), []).append(row)

results = []
policies = [
    ("first_success", 0, 1),
    ("window_60_lowest_weight", 60, None),
    ("window_120_lowest_weight", 120, None),
    ("first_2_candidates_lowest_weight", None, 2),
    ("first_3_candidates_lowest_weight", None, 3),
    ("all_4_candidates_lowest_weight", None, 4),
]
for name, window, target in policies:
    selected = []
    for key, group in sorted(groups.items()):
        success = sorted((r for r in group if int(r["syndrome_converged"])), key=lambda r: (int(r["iterations"]), int(r["engine"])))
        if window is not None:
            stop = int(success[0]["iterations"]) + window
            eligible = [r for r in success if int(r["iterations"]) <= stop]
            latency = stop if window else int(success[0]["iterations"])
        else:
            eligible = success[:target]
            latency = int(eligible[-1]["iterations"])
        winner = min(eligible, key=lambda r: (float(r["selected_weight"]), int(r["engine"])))
        selected.append((latency, int(winner["logically_correct"]), int(winner["syndrome_valid_logical_error"]), float(winner["selected_weight"]), int(winner["engine"])))
    its = np.asarray([r[0] for r in selected])
    results.append({"policy": name, "shots": len(selected), "logical_successes": sum(r[1] for r in selected),
                    "syndrome_valid_logical_errors": sum(r[2] for r in selected),
                    "average_iterations": float(np.mean(its)), "p50_iterations": float(np.percentile(its, 50)),
                    "p90_iterations": float(np.percentile(its, 90)), "p99_iterations": float(np.percentile(its, 99)),
                    "maximum_iterations": int(np.max(its)), "average_selected_weight": float(np.mean([r[3] for r in selected])),
                    "winner_engine_counts": {str(e): sum(r[4] == e for r in selected) for e in range(4)}})
(OUT / "selection_policy_summary.json").write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps(results, indent=2))

"""Multiseed lock study for unscaled saturating fixed-point Relay-BP."""

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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = PROJECT_ROOT / "reference"
sys.path.insert(0, str(REFERENCE))

from fixedpoint import FixedConfig  # noqa: E402
from relay_bp_fixed import FixedRelayBPDecoder, FixedRelayConfig, FixedRelayLegConfig  # noqa: E402

OUT = Path(__file__).resolve().parent
TIER2 = PROJECT_ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
MULTISEED = PROJECT_ROOT / "results/circuit-level-multiseed"
SAMPLES = MULTISEED / "paired_samples.npz"
FLOAT_ROWS = MULTISEED / "per_shot_results.csv"
WIDTHS, M, GUARD_BITS, SHOTS, DECODER_SEED = (14, 16, 18), 16, 4, 128, 9100
CONFIGS = {
    "low_latency": {"first_gamma": 0.25, "interval": (0.0, 0.66), "R": 4},
    "balanced": {"first_gamma": 0.25, "interval": (-0.12, 0.54), "R": 16},
    "high_success": {"first_gamma": 0.125, "interval": (-0.12, 0.54), "R": 32},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_problem():
    with np.load(TIER2 / "edge_lists.npz") as data:
        de, oe = data["detector_edges"], data["observable_edges"]
    with np.load(TIER2 / "faults.npz") as data:
        probabilities = data["probabilities"]
    h = sparse.csr_matrix((np.ones(len(de), np.uint8), (de[:, 1], de[:, 0])), shape=(1728, 67752))
    action = sparse.csr_matrix((np.ones(len(oe), np.uint8), (oe[:, 1], oe[:, 0])), shape=(12, 67752))
    return h, action, probabilities


def legs(name: str):
    c = CONFIGS[name]
    return (FixedRelayLegConfig(80, gamma=c["first_gamma"]),
            *(FixedRelayLegConfig(60, gamma_range=c["interval"]) for _ in range(c["R"] - 1)))


def load_float_rows():
    with FLOAT_ROWS.open(newline="") as source:
        rows = list(csv.DictReader(source))
    return {(r["configuration"], int(r["sample_seed"]), int(r["shot"])): r
            for r in rows if r["configuration"] in CONFIGS}


def run(name: str, width: int, seed_index: int, sample_seed: int):
    h, action, probabilities = load_problem()
    priors = np.log((1 - probabilities) / probabilities)
    with np.load(SAMPLES) as data:
        syndromes = data["syndromes"][seed_index]
        logicals = data["observed_logicals"][seed_index]
    oracle = load_float_rows()
    edge_count = h.nnz
    rows = []
    for shot in range(SHOTS):
        decoder = FixedRelayBPDecoder(
            h, FixedRelayConfig(
                fixed=FixedConfig(b=width, g=GUARD_BITS, M=M, clip=None, separate_scale=True),
                leg_configs=legs(name), S=1, R=CONFIGS[name]["R"], seed=DECODER_SEED + shot,
            ))
        result = decoder.decode(priors, syndromes[shot])
        decision = result.decoded_error
        syndrome_valid = bool(np.array_equal(np.asarray(h @ decision).reshape(-1) & 1, syndromes[shot]))
        logical_action_match = bool(np.array_equal(np.asarray(action @ decision).reshape(-1) & 1, logicals[shot]))
        success = syndrome_valid and logical_action_match
        o = oracle[(name, sample_seed, shot)]
        sat = result.saturation_counts
        iterations = result.total_iterations
        stored_denominator = h.shape[1] + iterations * (2 * h.shape[1] + 2 * edge_count)
        marginal_denominator = iterations * h.shape[1]
        rows.append({
            "configuration": name, "b": width, "M": M, "guard_bits": GUARD_BITS,
            "sample_seed": sample_seed, "shot": shot,
            "syndrome_converged": int(syndrome_valid), "logical_action_match": int(logical_action_match),
            "logically_correct": int(success), "syndrome_valid_logical_error": int(syndrome_valid and not logical_action_match),
            "non_convergence": int(not syndrome_valid), "float_logically_correct": int(o["logically_correct"]),
            "iterations": iterations, "float_iterations": int(o["iterations"]),
            "relay_legs": result.relay_legs, "float_relay_legs": int(o["relay_legs"]),
            "selected_solution_weight": "" if result.metadata["best_weight"] is None else float(result.metadata["best_weight"]),
            "float_selected_solution_weight": o["selected_solution_weight"],
            "prior_clipping": int(sat.get("physical_prior", 0)),
            "lambda_saturation": int(sat.get("lambda_bias", 0)),
            "check_message_saturation": int(sat.get("check_messages", 0)),
            "variable_message_saturation": int(sat.get("variable_messages", 0)),
            "marginal_saturation": int(sat.get("marginals", 0)),
            "accumulator_saturation": int(sat.get("guard_accumulator", 0)),
            "stored_operation_count": stored_denominator, "marginal_operation_count": marginal_denominator,
        })
    return rows


def describe(group):
    iterations = np.asarray([int(r["iterations"]) for r in group]); legs = np.asarray([int(r["relay_legs"]) for r in group])
    weights = [float(r["selected_solution_weight"]) for r in group if r["selected_solution_weight"] != ""]
    stored_sat = sum(int(r[k]) for r in group for k in ("prior_clipping", "lambda_saturation", "check_message_saturation", "variable_message_saturation", "marginal_saturation"))
    return {
        "shots": len(group), "syndrome_converged": sum(int(r["syndrome_converged"]) for r in group),
        "logical_successes": sum(int(r["logically_correct"]) for r in group),
        "syndrome_valid_logical_errors": sum(int(r["syndrome_valid_logical_error"]) for r in group),
        "non_convergence": sum(int(r["non_convergence"]) for r in group),
        "average_iterations": float(np.mean(iterations)), "p50_iterations": float(np.percentile(iterations, 50)),
        "p90_iterations": float(np.percentile(iterations, 90)), "p99_iterations": float(np.percentile(iterations, 99)),
        "maximum_iterations": int(np.max(iterations)), "average_relay_legs": float(np.mean(legs)),
        "maximum_relay_legs": int(np.max(legs)), "average_selected_solution_weight": float(np.mean(weights)) if weights else None,
        "stored_message_saturations": stored_sat,
        "stored_message_saturation_rate": stored_sat / sum(int(r["stored_operation_count"]) for r in group),
        "marginal_saturations": sum(int(r["marginal_saturation"]) for r in group),
        "marginal_saturation_rate": sum(int(r["marginal_saturation"]) for r in group) / sum(int(r["marginal_operation_count"]) for r in group),
        "prior_clipping": sum(int(r["prior_clipping"]) for r in group),
        "accumulator_saturation": sum(int(r["accumulator_saturation"]) for r in group),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with np.load(SAMPLES) as data:
        sample_seeds = [int(v) for v in data["sample_seeds"]]
    rows = []
    tasks = [(name, width, i, seed) for name in CONFIGS for width in WIDTHS for i, seed in enumerate(sample_seeds)]
    with ProcessPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(run, *task): task for task in tasks}
        for future in as_completed(futures):
            rows.extend(future.result()); print("completed", futures[future], flush=True)
    rows.sort(key=lambda r: (r["configuration"], r["b"], r["sample_seed"], r["shot"]))
    with (OUT / "per_shot_results.csv").open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)

    float_lookup = load_float_rows()
    float_rows = [{
        "configuration": k[0], "sample_seed": k[1], "shot": k[2],
        "syndrome_converged": int(v["syndrome_converged"]), "logically_correct": int(v["logically_correct"]),
        "syndrome_valid_logical_error": int(v["syndrome_converged"] == "1" and v["logically_correct"] == "0"),
        "non_convergence": int(v["syndrome_converged"] == "0"), "iterations": int(v["iterations"]),
        "relay_legs": int(v["relay_legs"]), "selected_solution_weight": v["selected_solution_weight"],
        "prior_clipping": 0, "lambda_saturation": 0, "check_message_saturation": 0,
        "variable_message_saturation": 0, "marginal_saturation": 0, "accumulator_saturation": 0,
        "stored_operation_count": 1, "marginal_operation_count": 1,
    } for k, v in float_lookup.items()]
    per_seed = []
    aggregate = []
    for name in CONFIGS:
        fg = [r for r in float_rows if r["configuration"] == name]
        fdesc = describe(fg); fdesc.update({"configuration": name, "format": "float"})
        for key in ("stored_message_saturations", "stored_message_saturation_rate", "marginal_saturations", "marginal_saturation_rate"):
            fdesc[key] = None
        aggregate.append(fdesc)
        for seed in sample_seeds:
            sd = describe([r for r in fg if r["sample_seed"] == seed]); sd.update({"configuration": name, "format": "float", "sample_seed": seed}); per_seed.append(sd)
        for width in WIDTHS:
            group = [r for r in rows if r["configuration"] == name and r["b"] == width]
            d = describe(group)
            fixed_success = d["logical_successes"]; float_success = fdesc["logical_successes"]
            fixed_only = sum(int(r["logically_correct"]) and not int(r["float_logically_correct"]) for r in group)
            float_only = sum(int(r["float_logically_correct"]) and not int(r["logically_correct"]) for r in group)
            discordant = fixed_only + float_only
            pvalue = 1.0 if discordant == 0 else float(stats.binomtest(min(fixed_only, float_only), discordant, 0.5).pvalue)
            seed_success_rates = []; seed_avg_iterations = []; seed_p99 = []
            for seed in sample_seeds:
                sd = describe([r for r in group if r["sample_seed"] == seed]); sd.update({"configuration": name, "format": f"b{width}", "sample_seed": seed}); per_seed.append(sd)
                seed_success_rates.append(sd["logical_successes"] / SHOTS); seed_avg_iterations.append(sd["average_iterations"]); seed_p99.append(sd["p99_iterations"])
            d.update({
                "configuration": name, "format": f"b{width}", "b": width,
                "logical_success_difference_vs_float": fixed_success - float_success,
                "logical_success_rate_difference_vs_float": (fixed_success - float_success) / len(group),
                "paired_fixed_only_successes": fixed_only, "paired_float_only_successes": float_only,
                "paired_success_difference_exact_pvalue": pvalue,
                "average_iteration_difference_vs_float": d["average_iterations"] - fdesc["average_iterations"],
                "p99_iteration_difference_vs_float": d["p99_iterations"] - fdesc["p99_iterations"],
                "seed_logical_success_rate_mean": float(np.mean(seed_success_rates)),
                "seed_logical_success_rate_std": float(np.std(seed_success_rates, ddof=1)),
                "seed_average_iterations_std": float(np.std(seed_avg_iterations, ddof=1)),
                "seed_p99_iterations_mean": float(np.mean(seed_p99)), "seed_p99_iterations_std": float(np.std(seed_p99, ddof=1)),
            })
            aggregate.append(d)
    (OUT / "per_seed_summary.json").write_text(json.dumps(per_seed, indent=2) + "\n")
    (OUT / "aggregate_summary.json").write_text(json.dumps(aggregate, indent=2) + "\n")
    manifest = {
        "study": "multiseed lock study for unscaled saturating fixed-point Relay-BP",
        "tier2_package": str(TIER2.relative_to(PROJECT_ROOT)), "paired_sample_source": str(SAMPLES.relative_to(PROJECT_ROOT)),
        "float_result_source": str(FLOAT_ROWS.relative_to(PROJECT_ROOT)), "sample_seeds": sample_seeds,
        "shots_per_seed": SHOTS, "paired_shots_per_configuration": len(sample_seeds) * SHOTS,
        "configs": CONFIGS, "formats": {"b": list(WIDTHS), "M": M, "guard_bits": GUARD_BITS, "stored": "signed saturating integer", "dynamic_scaling": False},
        "saturation_rate_denominator": "all physical-prior, lambda, check-message, variable-message, and marginal store operations",
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT.parent, text=True).strip(),
        "hashes": {"fixed_decoder": sha(REFERENCE / "relay_bp_fixed.py"), "float_decoder": sha(REFERENCE / "relay_bp_float.py"), "samples": sha(SAMPLES), "tier2_manifest": sha(TIER2 / "manifest.json")},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(aggregate, indent=2), flush=True)


if __name__ == "__main__":
    main()

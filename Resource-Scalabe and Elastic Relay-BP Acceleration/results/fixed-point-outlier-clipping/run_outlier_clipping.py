"""Paired Tier-2 node-state outlier-clipping characterization."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from scipy import sparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = PROJECT_ROOT / "reference"
sys.path.insert(0, str(REFERENCE))

from fixedpoint import FixedConfig  # noqa: E402
from relay_bp_fixed import FixedRelayConfig, FixedRelayLegConfig, SeparatedExponentRelayBPDecoder  # noqa: E402

OUT = Path(__file__).resolve().parent
TIER2 = PROJECT_ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
SAMPLES = PROJECT_ROOT / "results/circuit-level-sweeps/paired_samples.npz"
FLOAT = PROJECT_ROOT / "results/fixed-point-characterization"
GLOBAL = PROJECT_ROOT / "results/fixed-point-block-floating/summary.json"
SEPARATE = PROJECT_ROOT / "results/fixed-point-separated-exponents/summary.json"
UNSCALED = PROJECT_ROOT / "results/fixed-point-dynamic-range/wide_fixed_summary.json"
SHOTS, WIDTH, M, GUARD_BITS, EXPONENT_BITS, DECODER_SEED = 128, 12, 16, 4, 6, 9100
POLICIES = {"A_max": None, "B_p99p9": 99.9, "C_p99p5": 99.5, "D_p99": 99.0}
CONFIGS = {
    "low_latency": {"first_gamma": 0.25, "interval": (0.0, 0.66), "R": 4},
    "balanced": {"first_gamma": 0.25, "interval": (-0.12, 0.54), "R": 16},
    "high_success": {"first_gamma": 0.125, "interval": (-0.12, 0.54), "R": 32},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_problem():
    with np.load(TIER2 / "edge_lists.npz") as d:
        detector_edges, observable_edges = d["detector_edges"], d["observable_edges"]
    with np.load(TIER2 / "faults.npz") as d:
        probabilities = d["probabilities"]
    with np.load(SAMPLES) as d:
        syndromes, logicals = d["syndromes"], d["observed_logicals"]
    h = sparse.csr_matrix((np.ones(len(detector_edges), np.uint8),
                           (detector_edges[:, 1], detector_edges[:, 0])), shape=(1728, 67752))
    action = sparse.csr_matrix((np.ones(len(observable_edges), np.uint8),
                                (observable_edges[:, 1], observable_edges[:, 0])), shape=(12, 67752))
    return h, action, probabilities, syndromes, logicals


def legs(name: str):
    c = CONFIGS[name]
    return (FixedRelayLegConfig(80, gamma=c["first_gamma"]),
            *(FixedRelayLegConfig(60, gamma_range=c["interval"]) for _ in range(c["R"] - 1)))


def run(name: str, policy: str):
    h, action, probabilities, syndromes, logicals = load_problem()
    priors = np.log((1 - probabilities) / probabilities)
    with np.load(FLOAT / "float_corrections.npz") as d:
        oracle_corrections = d[name]
    oracle = json.loads((FLOAT / "float_per_shot.json").read_text())[name]
    rows = []
    for shot in range(SHOTS):
        decoder = SeparatedExponentRelayBPDecoder(
            h, FixedRelayConfig(
                fixed=FixedConfig(b=WIDTH, g=GUARD_BITS, M=M, separate_scale=True),
                leg_configs=legs(name), S=1, R=CONFIGS[name]["R"], seed=DECODER_SEED + shot,
            ), state_percentile=POLICIES[policy], exponent_bits=EXPONENT_BITS,
        )
        result = decoder.decode(priors, syndromes[shot])
        decision = result.decoded_error
        syndrome_valid = bool(np.array_equal(np.asarray(h @ decision).reshape(-1) & 1, syndromes[shot]))
        logical_valid = bool(np.array_equal(np.asarray(action @ decision).reshape(-1) & 1, logicals[shot]))
        logical_success = syndrome_valid and logical_valid
        bf = result.metadata["block_floating"]
        rows.append({
            "configuration": name, "policy": policy, "state_percentile": POLICIES[policy], "shot": shot,
            "syndrome_converged": int(syndrome_valid), "logically_correct": int(logical_success),
            "logical_classification_agrees_with_float": int(logical_success == bool(oracle[shot]["logically_correct"])),
            "correction_hamming_distance": int(np.count_nonzero(decision ^ oracle_corrections[shot])),
            "iterations": result.total_iterations, "relay_legs": result.relay_legs,
            "relay_legs_agree_with_float": int(result.relay_legs == oracle[shot]["relay_legs"]),
            "edge_saturation": int(result.saturation_counts.get("edge_mu", 0) + result.saturation_counts.get("edge_nu", 0)),
            "state_saturation": int(result.saturation_counts.get("state_lambda", 0) + result.saturation_counts.get("state_marginals", 0)),
            "guard_saturation": int(result.saturation_counts.get("guard_accumulator", 0)),
            "state_deliberately_clipped": int(bf["state_deliberately_clipped"]),
            "state_clip_candidates": int(bf["state_clip_candidates"]),
            "state_nonzero_to_zero": int(bf["state_nonzero_to_zero"]), "state_value_count": int(bf["state_value_count"]),
            "edge_nonzero_to_zero": int(bf["edge_nonzero_to_zero"]), "edge_value_count": int(bf["edge_value_count"]),
            "edge_exponent_min": int(bf["edge_exponent_min"]), "edge_exponent_max": int(bf["edge_exponent_max"]),
            "state_exponent_min": int(bf["state_exponent_min"]), "state_exponent_max": int(bf["state_exponent_max"]),
            "threshold_bucket_equal": int(bf["threshold_leading_one_bucket_equal"]),
            "threshold_bucket_above": int(bf["threshold_leading_one_bucket_above"]),
        })
    return rows


def summarize(rows):
    oracle_all = json.loads((FLOAT / "float_per_shot.json").read_text())
    output = []
    for name in CONFIGS:
        for policy in POLICIES:
            group = [r for r in rows if r["configuration"] == name and r["policy"] == policy]
            oracle = oracle_all[name]
            iterations = np.asarray([r["iterations"] for r in group]); relay = np.asarray([r["relay_legs"] for r in group])
            clip_count = sum(r["state_deliberately_clipped"] for r in group)
            clip_candidates = sum(r["state_clip_candidates"] for r in group)
            state_count = sum(r["state_value_count"] for r in group); edge_count = sum(r["edge_value_count"] for r in group)
            output.append({
                "configuration": name, "policy": policy, "state_percentile": POLICIES[policy],
                "mantissa_bits": WIDTH, "exponent_bits": EXPONENT_BITS, "M": M, "guard_bits": GUARD_BITS,
                "logical_successes": sum(r["logically_correct"] for r in group),
                "float_logical_successes": sum(bool(r["logically_correct"]) for r in oracle),
                "syndrome_converged": sum(r["syndrome_converged"] for r in group),
                "classification_agreement": sum(r["logical_classification_agrees_with_float"] for r in group),
                "mean_correction_hamming_distance": float(np.mean([r["correction_hamming_distance"] for r in group])),
                "average_iterations": float(np.mean(iterations)), "p90_iterations": float(np.percentile(iterations, 90)),
                "p99_iterations": float(np.percentile(iterations, 99)),
                "average_relay_legs": float(np.mean(relay)), "maximum_relay_legs": int(np.max(relay)),
                "relay_leg_agreement": sum(r["relay_legs_agree_with_float"] for r in group),
                "state_deliberately_clipped": clip_count, "state_clipping_rate": clip_count / clip_candidates,
                "state_nonzero_to_zero": sum(r["state_nonzero_to_zero"] for r in group),
                "state_zero_rate": sum(r["state_nonzero_to_zero"] for r in group) / state_count,
                "edge_nonzero_to_zero": sum(r["edge_nonzero_to_zero"] for r in group),
                "edge_zero_rate": sum(r["edge_nonzero_to_zero"] for r in group) / edge_count,
                "mantissa_saturation": sum(r["edge_saturation"] + r["state_saturation"] for r in group),
                "guard_saturation": sum(r["guard_saturation"] for r in group),
                "edge_exponent_range": [min(r["edge_exponent_min"] for r in group), max(r["edge_exponent_max"] for r in group)],
                "state_exponent_range": [min(r["state_exponent_min"] for r in group), max(r["state_exponent_max"] for r in group)],
                "leading_one_bucket_above_threshold": sum(r["threshold_bucket_above"] for r in group),
                "leading_one_bucket_at_threshold": sum(r["threshold_bucket_equal"] for r in group),
            })
    return output


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    with ProcessPoolExecutor(max_workers=4) as executor:
        jobs = {executor.submit(run, name, policy): (name, policy) for name in CONFIGS for policy in POLICIES}
        for future in as_completed(jobs):
            rows.extend(future.result()); print("completed", jobs[future], flush=True)
    rows.sort(key=lambda r: (r["configuration"], r["policy"], r["shot"]))
    with (OUT / "per_shot_results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    summary = summarize(rows)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    references = {
        "global_bf_12": [r for r in json.loads(GLOBAL.read_text()) if r["mantissa_bits"] == 12],
        "separate_A_12": [r for r in json.loads(SEPARATE.read_text()) if r["mantissa_bits"] == 12 and r["scheme"] == "A_separate"],
        "unscaled_b14_M16": [r for r in json.loads(UNSCALED.read_text()) if r["b"] == 14 and r["M"] == 16],
    }
    (OUT / "comparison_references.json").write_text(json.dumps(references, indent=2) + "\n")
    manifest = {
        "study": "Tier-2 controlled node-state outlier clipping", "shots": SHOTS,
        "paired_sample_source": str(SAMPLES.relative_to(PROJECT_ROOT)), "configurations": CONFIGS,
        "policies": POLICIES, "format": {"mantissa_bits": WIDTH, "exponent_bits_unsigned": EXPONENT_BITS, "M": M, "guard_bits": GUARD_BITS},
        "percentile_definition": "numpy exact linear percentile over abs(lambda) concatenated with abs(provisional marginal), independently each iteration",
        "clipping": "symmetric clip to exact percentile threshold before state exponent selection and quantization; edge block unchanged",
        "rtl_feasibility_proxy": "leading-one bucket counts at and above exact threshold are recorded; no approximate selector implemented",
        "physical_prior_exponent": 0,
        "hashes": {"fixed_decoder": sha(REFERENCE / "relay_bp_fixed.py"), "float_oracle": sha(REFERENCE / "relay_bp_float.py"), "paired_samples": sha(SAMPLES), "tier2_manifest": sha(TIER2 / "manifest.json")},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()

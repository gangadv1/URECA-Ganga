"""Paired Tier-2 separated-exponent Relay-BP characterization."""

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
from relay_bp_fixed import (  # noqa: E402
    FixedRelayConfig,
    FixedRelayLegConfig,
    SeparatedExponentRelayBPDecoder,
)

OUT = Path(__file__).resolve().parent
TIER2 = PROJECT_ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
SAMPLES = PROJECT_ROOT / "results/circuit-level-sweeps/paired_samples.npz"
FLOAT = PROJECT_ROOT / "results/fixed-point-characterization"
GLOBAL = PROJECT_ROOT / "results/fixed-point-block-floating/summary.json"
UNSCALED = PROJECT_ROOT / "results/fixed-point-dynamic-range/wide_fixed_summary.json"
SHOTS = 128
WIDTHS = (10, 12)
SCHEMES = {"A_separate": 1.0, "B_separate_75pct": 0.75}
M = 16
GUARD_BITS = 4
DECODER_SEED = 9100
CONFIGS = {
    "low_latency": {"first_gamma": 0.25, "interval": (0.0, 0.66), "R": 4},
    "balanced": {"first_gamma": 0.25, "interval": (-0.12, 0.54), "R": 16},
    "high_success": {"first_gamma": 0.125, "interval": (-0.12, 0.54), "R": 32},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_problem():
    with np.load(TIER2 / "edge_lists.npz") as d:
        de, oe = d["detector_edges"], d["observable_edges"]
    with np.load(TIER2 / "faults.npz") as d:
        probabilities = d["probabilities"]
    with np.load(SAMPLES) as d:
        syndromes, logicals = d["syndromes"], d["observed_logicals"]
    h = sparse.csr_matrix((np.ones(len(de), np.uint8), (de[:, 1], de[:, 0])), shape=(1728, 67752))
    a = sparse.csr_matrix((np.ones(len(oe), np.uint8), (oe[:, 1], oe[:, 0])), shape=(12, 67752))
    return h, a, probabilities, syndromes, logicals


def legs(name: str):
    c = CONFIGS[name]
    return (
        FixedRelayLegConfig(80, gamma=c["first_gamma"]),
        *(FixedRelayLegConfig(60, gamma_range=c["interval"]) for _ in range(c["R"] - 1)),
    )


def run(name: str, width: int, scheme: str):
    h, action, probabilities, syndromes, logicals = load_problem()
    priors = np.log((1 - probabilities) / probabilities)
    with np.load(FLOAT / "float_corrections.npz") as d:
        oracle_corrections = d[name]
    oracle = json.loads((FLOAT / "float_per_shot.json").read_text())[name]
    rows = []
    for shot in range(SHOTS):
        decoder = SeparatedExponentRelayBPDecoder(
            h,
            FixedRelayConfig(
                fixed=FixedConfig(b=width, g=GUARD_BITS, M=M, separate_scale=True),
                leg_configs=legs(name), S=1, R=CONFIGS[name]["R"], seed=DECODER_SEED + shot,
            ),
            headroom_fraction=SCHEMES[scheme],
        )
        result = decoder.decode(priors, syndromes[shot])
        decision = result.decoded_error
        syndrome_valid = bool(np.array_equal(np.asarray(h @ decision).reshape(-1) & 1, syndromes[shot]))
        logical_valid = bool(np.array_equal(np.asarray(action @ decision).reshape(-1) & 1, logicals[shot]))
        logical_success = syndrome_valid and logical_valid
        bf = result.metadata["block_floating"]
        rows.append({
            "configuration": name, "scheme": scheme, "mantissa_bits": width, "shot": shot,
            "syndrome_converged": int(syndrome_valid), "logically_correct": int(logical_success),
            "logical_classification_agrees_with_float": int(logical_success == bool(oracle[shot]["logically_correct"])),
            "exact_correction_agrees_with_float": int(np.array_equal(decision, oracle_corrections[shot])),
            "correction_hamming_distance": int(np.count_nonzero(decision ^ oracle_corrections[shot])),
            "iterations": result.total_iterations, "relay_legs": result.relay_legs,
            "relay_legs_agree_with_float": int(result.relay_legs == oracle[shot]["relay_legs"]),
            "edge_saturation": int(result.saturation_counts.get("edge_mu", 0) + result.saturation_counts.get("edge_nu", 0)),
            "state_saturation": int(result.saturation_counts.get("state_lambda", 0) + result.saturation_counts.get("state_marginals", 0)),
            "guard_saturation": int(result.saturation_counts.get("guard_accumulator", 0)),
            "edge_nonzero_to_zero": int(bf["edge_nonzero_to_zero"]),
            "state_nonzero_to_zero": int(bf["state_nonzero_to_zero"]),
            "edge_value_count": int(bf["edge_value_count"]), "state_value_count": int(bf["state_value_count"]),
            "edge_exponent_min": int(bf["edge_exponent_min"]), "edge_exponent_max": int(bf["edge_exponent_max"]),
            "state_exponent_min": int(bf["state_exponent_min"]), "state_exponent_max": int(bf["state_exponent_max"]),
            "edge_exponent_changes": int(bf["edge_exponent_changes"]),
            "state_exponent_changes": int(bf["state_exponent_changes"]),
        })
    return rows


def summarize(rows):
    output = []
    oracle_all = json.loads((FLOAT / "float_per_shot.json").read_text())
    for name in CONFIGS:
        oracle = oracle_all[name]
        for scheme in SCHEMES:
            for width in WIDTHS:
                g = [r for r in rows if r["configuration"] == name and r["scheme"] == scheme and r["mantissa_bits"] == width]
                its = np.asarray([r["iterations"] for r in g]); relay = np.asarray([r["relay_legs"] for r in g])
                edge_count = sum(r["edge_value_count"] for r in g); state_count = sum(r["state_value_count"] for r in g)
                output.append({
                    "configuration": name, "scheme": scheme, "headroom_fraction": SCHEMES[scheme],
                    "mantissa_bits": width, "M": M, "guard_bits": GUARD_BITS,
                    "logical_successes": sum(r["logically_correct"] for r in g),
                    "float_logical_successes": sum(bool(r["logically_correct"]) for r in oracle),
                    "syndrome_converged": sum(r["syndrome_converged"] for r in g),
                    "logical_classification_agreement": sum(r["logical_classification_agrees_with_float"] for r in g),
                    "exact_correction_agreement": sum(r["exact_correction_agrees_with_float"] for r in g),
                    "mean_correction_hamming_distance": float(np.mean([r["correction_hamming_distance"] for r in g])),
                    "average_iterations": float(np.mean(its)), "p90_iterations": float(np.percentile(its, 90)),
                    "p99_iterations": float(np.percentile(its, 99)),
                    "float_average_iterations": float(np.mean([r["iterations"] for r in oracle])),
                    "float_p90_iterations": float(np.percentile([r["iterations"] for r in oracle], 90)),
                    "float_p99_iterations": float(np.percentile([r["iterations"] for r in oracle], 99)),
                    "average_relay_legs": float(np.mean(relay)), "maximum_relay_legs": int(np.max(relay)),
                    "relay_leg_agreement": sum(r["relay_legs_agree_with_float"] for r in g),
                    "edge_saturation_count": sum(r["edge_saturation"] for r in g),
                    "state_saturation_count": sum(r["state_saturation"] for r in g),
                    "guard_saturation_count": sum(r["guard_saturation"] for r in g),
                    "edge_zero_rate": sum(r["edge_nonzero_to_zero"] for r in g) / edge_count,
                    "state_zero_rate": sum(r["state_nonzero_to_zero"] for r in g) / state_count,
                    "edge_exponent_range": [min(r["edge_exponent_min"] for r in g), max(r["edge_exponent_max"] for r in g)],
                    "state_exponent_range": [min(r["state_exponent_min"] for r in g), max(r["state_exponent_max"] for r in g)],
                    "edge_exponent_changes": sum(r["edge_exponent_changes"] for r in g),
                    "state_exponent_changes": sum(r["state_exponent_changes"] for r in g),
                })
    return output


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    with ProcessPoolExecutor(max_workers=4) as ex:
        jobs = {ex.submit(run, n, b, s): (n, s, b) for n in CONFIGS for s in SCHEMES for b in WIDTHS}
        for future in as_completed(jobs):
            rows.extend(future.result()); print("completed", jobs[future], flush=True)
    rows.sort(key=lambda r: (r["configuration"], r["scheme"], r["mantissa_bits"], r["shot"]))
    with (OUT / "per_shot_results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
    summary = summarize(rows)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    global_12 = [r for r in json.loads(GLOBAL.read_text()) if r["mantissa_bits"] == 12]
    unscaled = [r for r in json.loads(UNSCALED.read_text()) if r["b"] == 14 and r["M"] == 16]
    (OUT / "comparison_references.json").write_text(json.dumps({"global_bf_12": global_12, "unscaled_b14_M16": unscaled}, indent=2) + "\n")
    manifest = {
        "study": "Tier-2 separated edge/state exponent characterization", "shots": SHOTS,
        "paired_sample_source": str(SAMPLES.relative_to(PROJECT_ROOT)), "configurations": CONFIGS,
        "schemes": SCHEMES, "formats": {"mantissa_bits": list(WIDTHS), "M": M, "guard_bits": GUARD_BITS},
        "alignment": "rounded power-of-two shifts between state and edge blocks",
        "physical_prior_exponent": 0,
        "hashes": {"fixed_decoder": sha(REFERENCE / "relay_bp_fixed.py"), "float_oracle": sha(REFERENCE / "relay_bp_float.py"), "tier2_manifest": sha(TIER2 / "manifest.json")},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()

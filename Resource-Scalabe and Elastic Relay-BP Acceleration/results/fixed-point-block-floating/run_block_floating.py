"""Paired Tier-2 block-floating Relay-BP characterization."""

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
    BlockFloatingRelayBPDecoder,
    FixedRelayConfig,
    FixedRelayLegConfig,
)

OUT = Path(__file__).resolve().parent
TIER2 = PROJECT_ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
SAMPLES = PROJECT_ROOT / "results/circuit-level-sweeps/paired_samples.npz"
FLOAT = PROJECT_ROOT / "results/fixed-point-characterization"
UNSCALED = PROJECT_ROOT / "results/fixed-point-dynamic-range/wide_fixed_summary.json"
SHOTS = 128
WIDTHS = (8, 10, 12)
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


def run(name: str, width: int):
    h, action, probabilities, syndromes, logicals = load_problem()
    priors = np.log((1 - probabilities) / probabilities)
    with np.load(FLOAT / "float_corrections.npz") as d:
        oracle_corrections = d[name]
    oracle = json.loads((FLOAT / "float_per_shot.json").read_text())[name]
    rows = []
    for shot in range(SHOTS):
        decoder = BlockFloatingRelayBPDecoder(
            h,
            FixedRelayConfig(
                fixed=FixedConfig(b=width, g=GUARD_BITS, M=M, separate_scale=True),
                leg_configs=legs(name), S=1, R=CONFIGS[name]["R"], seed=DECODER_SEED + shot,
            ),
        )
        result = decoder.decode(priors, syndromes[shot])
        decision = result.decoded_error
        syndrome_valid = bool(np.array_equal(np.asarray(h @ decision).reshape(-1) & 1, syndromes[shot]))
        logical_valid = bool(np.array_equal(np.asarray(action @ decision).reshape(-1) & 1, logicals[shot]))
        oracle_logical = bool(oracle[shot]["logically_correct"])
        bf = result.metadata["block_floating"]
        row = {
            "configuration": name, "mantissa_bits": width, "shot": shot,
            "syndrome_converged": int(syndrome_valid),
            "logically_correct": int(syndrome_valid and logical_valid),
            "logical_classification_agrees_with_float": int((syndrome_valid and logical_valid) == oracle_logical),
            "exact_correction_agrees_with_float": int(np.array_equal(decision, oracle_corrections[shot])),
            "correction_hamming_distance": int(np.count_nonzero(decision ^ oracle_corrections[shot])),
            "iterations": result.total_iterations, "relay_legs": result.relay_legs,
            "iterations_agree_with_float": int(result.total_iterations == oracle[shot]["iterations"]),
            "relay_legs_agree_with_float": int(result.relay_legs == oracle[shot]["relay_legs"]),
            "mantissa_saturation": int(sum(result.saturation_counts.values())),
            "guard_saturation": int(result.saturation_counts.get("guard_accumulator", 0)),
            "exponent_changes": int(bf["exponent_changes"]),
            "exponent_min": int(bf["exponent_min"]), "exponent_max": int(bf["exponent_max"]),
            "rescale_nonzero_to_zero": int(bf["rescale_nonzero_to_zero"]),
            "quantized_value_count": int(bf["quantized_value_count"]),
        }
        rows.append(row)
    return rows


def summarize(rows):
    out = []
    for name in CONFIGS:
        float_rows = json.loads((FLOAT / "float_per_shot.json").read_text())[name]
        for width in WIDTHS:
            g = [r for r in rows if r["configuration"] == name and r["mantissa_bits"] == width]
            iterations = np.array([r["iterations"] for r in g])
            out.append({
                "configuration": name, "mantissa_bits": width, "M": M, "guard_bits": GUARD_BITS,
                "logical_successes": sum(r["logically_correct"] for r in g),
                "float_logical_successes": sum(bool(r["logically_correct"]) for r in float_rows),
                "syndrome_converged": sum(r["syndrome_converged"] for r in g),
                "logical_classification_agreement": sum(r["logical_classification_agrees_with_float"] for r in g),
                "exact_correction_agreement": sum(r["exact_correction_agrees_with_float"] for r in g),
                "mean_correction_hamming_distance": float(np.mean([r["correction_hamming_distance"] for r in g])),
                "average_iterations": float(np.mean(iterations)), "p99_iterations": float(np.percentile(iterations, 99)),
                "float_average_iterations": float(np.mean([r["iterations"] for r in float_rows])),
                "float_p99_iterations": float(np.percentile([r["iterations"] for r in float_rows], 99)),
                "iteration_agreement": sum(r["iterations_agree_with_float"] for r in g),
                "relay_leg_agreement": sum(r["relay_legs_agree_with_float"] for r in g),
                "mantissa_saturation_count": sum(r["mantissa_saturation"] for r in g),
                "guard_saturation_count": sum(r["guard_saturation"] for r in g),
                "exponent_changes": sum(r["exponent_changes"] for r in g),
                "exponent_range": [min(r["exponent_min"] for r in g), max(r["exponent_max"] for r in g)],
                "rescale_nonzero_to_zero": sum(r["rescale_nonzero_to_zero"] for r in g),
                "rescale_zero_fraction": sum(r["rescale_nonzero_to_zero"] for r in g) / sum(r["quantized_value_count"] for r in g),
            })
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    with ProcessPoolExecutor(max_workers=3) as ex:
        jobs = {ex.submit(run, n, b): (n, b) for n in CONFIGS for b in WIDTHS}
        for f in as_completed(jobs):
            rows.extend(f.result())
            print("completed", jobs[f], flush=True)
    rows.sort(key=lambda r: (r["configuration"], r["mantissa_bits"], r["shot"]))
    with (OUT / "per_shot_results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    summary = summarize(rows)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    unscaled = [r for r in json.loads(UNSCALED.read_text()) if r["b"] == 14 and r["M"] == 16]
    (OUT / "unscaled_b14_M16.json").write_text(json.dumps(unscaled, indent=2) + "\n")
    manifest = {
        "study": "Tier-2 iteration-shared block-floating fixed-point characterization",
        "shots": 128, "paired_sample_source": str(SAMPLES.relative_to(PROJECT_ROOT)),
        "configurations": CONFIGS, "formats": {"mantissa_bits": list(WIDTHS), "M": M, "guard_bits": GUARD_BITS},
        "scheme": {
            "physical_prior": "signed mantissa, exponent 0",
            "mutable_block": "one shared exponent for lambda, mu, nu, and marginals per iteration",
            "selection": "smallest e>=0 fitting provisional maximum absolute value",
            "rescaling": "round(real/2^e), nearest ties away from zero",
            "exponent_change": "once per iteration before stored mutable values are committed",
        },
        "hashes": {"fixed_decoder": sha(REFERENCE / "relay_bp_fixed.py"), "float_oracle": sha(REFERENCE / "relay_bp_float.py"), "tier2_manifest": sha(TIER2 / "manifest.json")},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

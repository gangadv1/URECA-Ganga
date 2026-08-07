"""Paired Tier-2 characterization of the canonical Python fixed decoder."""

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
REFERENCE_DIR = PROJECT_ROOT / "reference"
sys.path.insert(0, str(REFERENCE_DIR))

from fixedpoint import FixedConfig  # noqa: E402
from relay_bp_fixed import FixedRelayBPDecoder, FixedRelayConfig, FixedRelayLegConfig  # noqa: E402
from relay_bp_float import FloatRelayBPDecoder, RelayLegConfig  # noqa: E402


OUT_DIR = Path(__file__).resolve().parent
TIER2_DIR = PROJECT_ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
SAMPLE_SOURCE = PROJECT_ROOT / "results/circuit-level-sweeps/paired_samples.npz"
SHOTS = 128
SAMPLE_SEED = 20260809
DECODER_SEED = 9100
GUARD_BITS = 4
WIDTHS = (4, 6, 8)
COEFFICIENT_SCALES = (4, 8, 16)
CONFIGS = {
    "low_latency": {"first_gamma": 0.25, "interval": (0.0, 0.66), "S": 1, "R": 4},
    "balanced": {"first_gamma": 0.25, "interval": (-0.12, 0.54), "S": 1, "R": 16},
    "high_success": {"first_gamma": 0.125, "interval": (-0.12, 0.54), "S": 1, "R": 32},
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_problem() -> tuple[sparse.csr_matrix, sparse.csr_matrix, np.ndarray, np.ndarray, np.ndarray]:
    with np.load(TIER2_DIR / "edge_lists.npz") as data:
        detector_edges = data["detector_edges"]
        observable_edges = data["observable_edges"]
    with np.load(TIER2_DIR / "faults.npz") as data:
        probabilities = data["probabilities"]
    with np.load(SAMPLE_SOURCE) as data:
        syndromes = data["syndromes"]
        observed_logicals = data["observed_logicals"]
    h = sparse.csr_matrix(
        (np.ones(len(detector_edges), dtype=np.uint8), (detector_edges[:, 1], detector_edges[:, 0])),
        shape=(1728, 67752),
    )
    action = sparse.csr_matrix(
        (np.ones(len(observable_edges), dtype=np.uint8), (observable_edges[:, 1], observable_edges[:, 0])),
        shape=(12, 67752),
    )
    for matrix in (h, action):
        matrix.data &= 1
        matrix.eliminate_zeros()
    return h, action, probabilities, syndromes, observed_logicals


def float_decoder(name: str, h: sparse.csr_matrix, shot: int) -> FloatRelayBPDecoder:
    config = CONFIGS[name]
    legs = (
        RelayLegConfig(max_iterations=80, gamma=config["first_gamma"]),
        *(RelayLegConfig(max_iterations=60, gamma_range=config["interval"]) for _ in range(config["R"] - 1)),
    )
    return FloatRelayBPDecoder(h, leg_configs=legs, S=1, R=config["R"], seed=DECODER_SEED + shot)


def fixed_decoder(
    name: str,
    h: sparse.csr_matrix,
    shot: int,
    width: int,
    coefficient_scale: int,
    trace: bool = False,
) -> FixedRelayBPDecoder:
    config = CONFIGS[name]
    legs = (
        FixedRelayLegConfig(max_iterations=80, gamma=config["first_gamma"]),
        *(
            FixedRelayLegConfig(max_iterations=60, gamma_range=config["interval"])
            for _ in range(config["R"] - 1)
        ),
    )
    return FixedRelayBPDecoder(
        h,
        FixedRelayConfig(
            fixed=FixedConfig(b=width, g=GUARD_BITS, M=coefficient_scale, clip=None, separate_scale=True),
            leg_configs=legs,
            S=1,
            R=config["R"],
            seed=DECODER_SEED + shot,
            trace_iterations=trace,
        ),
    )


def run_float(name: str) -> tuple[str, list[dict[str, object]], np.ndarray]:
    h, action, probabilities, syndromes, observed_logicals = load_problem()
    lambdas = np.log((1.0 - probabilities) / probabilities)
    rows = []
    corrections = []
    for shot in range(SHOTS):
        result = float_decoder(name, h, shot).decode(lambdas, syndromes[shot])
        decision = result.decoded_error
        corrections.append(decision)
        syndrome_valid = bool(np.array_equal(np.asarray(h @ decision).reshape(-1) & 1, syndromes[shot]))
        logical_match = bool(np.array_equal(np.asarray(action @ decision).reshape(-1) & 1, observed_logicals[shot]))
        rows.append(
            {
                "configuration": name,
                "shot": shot,
                "syndrome_converged": int(syndrome_valid),
                "logically_correct": int(syndrome_valid and logical_match),
                "iterations": result.total_iterations,
                "relay_legs": result.relay_legs,
                "selected_solution_weight": result.metadata["best_weight"],
            }
        )
    return name, rows, np.stack(corrections)


def run_fixed(name: str, width: int, coefficient_scale: int) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    h, action, probabilities, syndromes, observed_logicals = load_problem()
    lambdas = np.log((1.0 - probabilities) / probabilities)
    with np.load(OUT_DIR / "float_corrections.npz") as data:
        float_corrections = data[name]
    float_rows = json.loads((OUT_DIR / "float_per_shot.json").read_text(encoding="utf-8"))[name]
    rows = []
    first_mismatch = None
    for shot in range(SHOTS):
        result = fixed_decoder(name, h, shot, width, coefficient_scale).decode(lambdas, syndromes[shot])
        decision = result.decoded_error
        syndrome_valid = bool(np.array_equal(np.asarray(h @ decision).reshape(-1) & 1, syndromes[shot]))
        logical_match = bool(np.array_equal(np.asarray(action @ decision).reshape(-1) & 1, observed_logicals[shot]))
        hamming = int(np.count_nonzero(decision ^ float_corrections[shot]))
        row = {
            "configuration": name,
            "b": width,
            "M": coefficient_scale,
            "guard_bits": GUARD_BITS,
            "shot": shot,
            "syndrome_converged": int(syndrome_valid),
            "logically_correct": int(syndrome_valid and logical_match),
            "decision_agrees_with_float": int(hamming == 0),
            "decision_hamming_distance": hamming,
            "iterations": result.total_iterations,
            "relay_legs": result.relay_legs,
            "iterations_agree_with_float": int(result.total_iterations == float_rows[shot]["iterations"]),
            "legs_agree_with_float": int(result.relay_legs == float_rows[shot]["relay_legs"]),
            "selected_solution_weight": result.metadata["best_weight"],
            **{f"saturation_{key}": value for key, value in result.saturation_counts.items()},
        }
        for key in ("physical_prior", "lambda_bias", "check_messages", "guard_accumulator", "variable_messages", "marginals"):
            row.setdefault(f"saturation_{key}", 0)
        rows.append(row)
        if hamming and first_mismatch is None:
            traced = fixed_decoder(name, h, shot, width, coefficient_scale, trace=True).decode(
                lambdas, syndromes[shot]
            )
            first_mismatch = {
                "configuration": name,
                "b": width,
                "M": coefficient_scale,
                "shot": shot,
                "decision_hamming_distance": hamming,
                "float": float_rows[shot],
                "fixed": {
                    "converged": traced.converged,
                    "iterations": traced.total_iterations,
                    "relay_legs": traced.relay_legs,
                    "final_residual_weight": int(traced.final_syndrome.sum()),
                    "selected_solution_weight": traced.metadata["best_weight"],
                    "saturation_counts": traced.saturation_counts,
                },
                "fixed_iteration_trace": traced.trace,
            }
    return rows, first_mismatch


def summarize_float(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output = []
    for name in CONFIGS:
        group = [row for row in rows if row["configuration"] == name]
        weights = [row["selected_solution_weight"] for row in group if row["selected_solution_weight"] is not None]
        output.append(
            {
                "configuration": name,
                "logical_successes": sum(row["logically_correct"] for row in group),
                "syndrome_converged": sum(row["syndrome_converged"] for row in group),
                "average_iterations": float(np.mean([row["iterations"] for row in group])),
                "average_relay_legs": float(np.mean([row["relay_legs"] for row in group])),
                "average_selected_solution_weight": float(np.mean(weights)),
            }
        )
    return output


def summarize_fixed(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output = []
    for name in CONFIGS:
        for width in WIDTHS:
            for coefficient_scale in COEFFICIENT_SCALES:
                group = [
                    row for row in rows
                    if row["configuration"] == name and row["b"] == width and row["M"] == coefficient_scale
                ]
                weights = [row["selected_solution_weight"] for row in group if row["selected_solution_weight"] is not None]
                saturation_keys = [key for key in group[0] if key.startswith("saturation_")]
                output.append(
                    {
                        "configuration": name,
                        "b": width,
                        "M": coefficient_scale,
                        "guard_bits": GUARD_BITS,
                        "logical_successes": sum(row["logically_correct"] for row in group),
                        "logical_failure_rate": 1.0 - sum(row["logically_correct"] for row in group) / SHOTS,
                        "syndrome_converged": sum(row["syndrome_converged"] for row in group),
                        "syndrome_convergence_rate": sum(row["syndrome_converged"] for row in group) / SHOTS,
                        "decision_agreement_shots": sum(row["decision_agrees_with_float"] for row in group),
                        "mean_decision_hamming_distance": float(np.mean([row["decision_hamming_distance"] for row in group])),
                        "maximum_decision_hamming_distance": max(row["decision_hamming_distance"] for row in group),
                        "iteration_agreement_shots": sum(row["iterations_agree_with_float"] for row in group),
                        "leg_agreement_shots": sum(row["legs_agree_with_float"] for row in group),
                        "average_iterations": float(np.mean([row["iterations"] for row in group])),
                        "average_relay_legs": float(np.mean([row["relay_legs"] for row in group])),
                        "average_selected_solution_weight": float(np.mean(weights)) if weights else None,
                        "saturation_counts": {
                            key.removeprefix("saturation_"): int(sum(row[key] for row in group))
                            for key in saturation_keys
                        },
                    }
                )
    return output


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    float_rows = []
    float_corrections = {}
    with ProcessPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_float, name) for name in CONFIGS]
        for future in as_completed(futures):
            name, rows, corrections = future.result()
            float_rows.extend(rows)
            float_corrections[name] = corrections
            print(f"completed float oracle {name}", flush=True)
    float_by_name = {name: sorted([row for row in float_rows if row["configuration"] == name], key=lambda row: row["shot"]) for name in CONFIGS}
    (OUT_DIR / "float_per_shot.json").write_text(json.dumps(float_by_name) + "\n", encoding="utf-8")
    np.savez_compressed(OUT_DIR / "float_corrections.npz", **float_corrections)

    fixed_rows = []
    mismatch_traces = []
    tasks = [(name, width, scale) for name in CONFIGS for width in WIDTHS for scale in COEFFICIENT_SCALES]
    with ProcessPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(run_fixed, *task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            rows, mismatch = future.result()
            fixed_rows.extend(rows)
            if mismatch is not None:
                mismatch_traces.append(mismatch)
            print(f"completed fixed config={task[0]} b={task[1]} M={task[2]}", flush=True)
    fixed_rows.sort(key=lambda row: (row["configuration"], row["b"], row["M"], row["shot"]))
    with (OUT_DIR / "per_shot_results.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(fixed_rows[0]))
        writer.writeheader()
        writer.writerows(fixed_rows)
    float_summary = summarize_float(float_rows)
    fixed_summary = summarize_fixed(fixed_rows)
    (OUT_DIR / "float_summary.json").write_text(json.dumps(float_summary, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "fixed_summary.json").write_text(json.dumps(fixed_summary, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "first_mismatch_traces.json").write_text(json.dumps(mismatch_traces, indent=2) + "\n", encoding="utf-8")

    tier2_manifest = json.loads((TIER2_DIR / "manifest.json").read_text(encoding="utf-8"))
    manifest = {
        "study": "first Tier-2 fixed-point characterization",
        "shots": {"count": SHOTS, "sample_seed": SAMPLE_SEED, "paired": True},
        "graph": {
            "package": str(TIER2_DIR.relative_to(PROJECT_ROOT)),
            "dimensions": {"detectors": 1728, "faults": 67752, "logical_observables": 12},
            "package_manifest_sha256": sha256(TIER2_DIR / "manifest.json"),
            "detector_incidence_sha256": tier2_manifest["graph"]["detector_incidence_sha256"],
        },
        "configurations": CONFIGS,
        "formats": {"message_width_b": list(WIDTHS), "coefficient_scale_M": list(COEFFICIENT_SCALES)},
        "arithmetic": {
            "guard_bits": GUARD_BITS,
            "guard_width": "b + 4 signed bits",
            "message_clipping": "full signed b-bit range; clip=None",
            "rounding": "nearest, ties away from zero",
            "saturation": "after physical-prior, bias, check-message, variable-message and marginal storage",
            "coefficient_quantization": "round(gamma*M), signed; independent per-node gamma fixed within leg",
            "relay_handoff": "only previous-leg final marginals; edge messages reset",
        },
        "audit": {
            "existing_fixed_required_correction": True,
            "removed_semantics": ["carry_gamma", "relay_memory mixing", "belief-plus-memory leg transfer"],
            "fixed_source_sha256": sha256(REFERENCE_DIR / "relay_bp_fixed.py"),
            "float_oracle_sha256": sha256(REFERENCE_DIR / "relay_bp_float.py"),
        },
        "artifacts": [
            "manifest.json", "float_summary.json", "fixed_summary.json", "per_shot_results.csv",
            "float_per_shot.json", "float_corrections.npz", "first_mismatch_traces.json", "run_characterization.py"
        ],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"float": float_summary, "fixed": fixed_summary}, indent=2))


if __name__ == "__main__":
    main()

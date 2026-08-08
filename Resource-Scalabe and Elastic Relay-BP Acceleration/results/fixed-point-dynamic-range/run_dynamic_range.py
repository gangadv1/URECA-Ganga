"""Float dynamic-range measurement and wider fixed-point characterization."""

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
FLOAT_SOURCE = PROJECT_ROOT / "results/fixed-point-characterization"
SHOTS = 128
SAMPLE_SEED = 20260809
DECODER_SEED = 9100
WIDTHS = (8, 10, 12, 14)
SCALES = (4, 16)
GUARD_BITS = 4
SAMPLE_PANEL_SIZE = 2048
SAMPLE_PANELS = 16
LOG_EDGES = np.linspace(-12.0, 308.0, 6401)
QUANTILES = (0.95, 0.99, 0.999, 0.9999)
CONFIGS = {
    "low_latency": {"first_gamma": 0.25, "interval": (0.0, 0.66), "R": 4},
    "balanced": {"first_gamma": 0.25, "interval": (-0.12, 0.54), "R": 16},
    "high_success": {"first_gamma": 0.125, "interval": (-0.12, 0.54), "R": 32},
}
QUANTITIES = ("physical_priors", "var_to_check", "check_to_var", "lambda_bias", "marginals")


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
        logicals = data["observed_logicals"]
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
    return h, action, probabilities, syndromes, logicals


class StreamingMagnitudeStats:
    def __init__(self) -> None:
        self.minimum = np.inf
        self.maximum = -np.inf
        self.zero_count = 0
        self.sample_count = 0
        self.histogram = np.zeros(len(LOG_EDGES) - 1, dtype=np.int64)

    def update(self, full_values: np.ndarray, sampled_values: np.ndarray) -> None:
        self.minimum = min(self.minimum, float(np.min(full_values)))
        self.maximum = max(self.maximum, float(np.max(full_values)))
        magnitudes = np.abs(np.asarray(sampled_values, dtype=float))
        zero = magnitudes == 0.0
        self.zero_count += int(np.count_nonzero(zero))
        nonzero = magnitudes[~zero]
        if len(nonzero):
            logs = np.clip(np.log10(nonzero), LOG_EDGES[0], LOG_EDGES[-1] - 1e-12)
            self.histogram += np.histogram(logs, bins=LOG_EDGES)[0]
        self.sample_count += len(magnitudes)

    def quantile(self, probability: float) -> float:
        target = probability * self.sample_count
        if target <= self.zero_count:
            return 0.0
        target_nonzero = target - self.zero_count
        cumulative = np.cumsum(self.histogram)
        index = min(int(np.searchsorted(cumulative, target_nonzero, side="left")), len(self.histogram) - 1)
        return float(10.0 ** ((LOG_EDGES[index] + LOG_EDGES[index + 1]) / 2.0))

    def result(self) -> dict[str, object]:
        return {
            "minimum": self.minimum,
            "maximum": self.maximum,
            "sample_count": self.sample_count,
            "absolute_percentiles_estimated": {
                "p95": self.quantile(0.95),
                "p99": self.quantile(0.99),
                "p99.9": self.quantile(0.999),
                "p99.99": self.quantile(0.9999),
            },
        }


def new_stats() -> dict[str, StreamingMagnitudeStats]:
    return {name: StreamingMagnitudeStats() for name in QUANTITIES if name != "physical_priors"}


def float_legs(name: str) -> tuple[RelayLegConfig, ...]:
    config = CONFIGS[name]
    return (
        RelayLegConfig(max_iterations=80, gamma=config["first_gamma"]),
        *(RelayLegConfig(max_iterations=60, gamma_range=config["interval"]) for _ in range(config["R"] - 1)),
    )


def measure_float_range(name: str) -> tuple[str, dict[str, object]]:
    h, _, probabilities, syndromes, _ = load_problem()
    lambdas = np.log((1.0 - probabilities) / probabilities)
    overall = new_stats()
    physical = StreamingMagnitudeStats()
    physical.update(lambdas, lambdas)
    by_leg: dict[int, dict[str, StreamingMagnitudeStats]] = {}
    by_iteration: dict[int, dict[str, StreamingMagnitudeStats]] = {}
    rng = np.random.default_rng(4400)
    edge_panels = [rng.integers(0, h.nnz, size=SAMPLE_PANEL_SIZE) for _ in range(SAMPLE_PANELS)]
    variable_panels = [rng.integers(0, h.shape[1], size=SAMPLE_PANEL_SIZE) for _ in range(SAMPLE_PANELS)]
    total_iterations = 0
    max_abs_by_global_iteration: list[dict[str, object]] = []

    for shot in range(SHOTS):
        decoder = FloatRelayBPDecoder(h, leg_configs=float_legs(name), S=1, R=CONFIGS[name]["R"], seed=DECODER_SEED + shot)
        initial_marginals = lambdas.copy()
        converged = False
        global_iteration = 0
        for leg_index, leg in enumerate(decoder.leg_configs[: decoder.R]):
            gamma = decoder._gamma_vector(leg, decoder._rng)
            nu_previous = lambdas[decoder._edge_variables].copy()
            marginals_previous = initial_marginals.copy()
            for iteration in range(1, leg.max_iterations + 1):
                lambda_bias = (1.0 - gamma) * lambdas + gamma * marginals_previous
                mu = decoder._check_update(nu_previous, syndromes[shot])
                incoming = np.bincount(decoder._edge_variables, weights=mu, minlength=h.shape[1])
                nu_current = lambda_bias[decoder._edge_variables] + incoming[decoder._edge_variables] - mu
                marginals = lambda_bias + incoming
                panel = global_iteration % SAMPLE_PANELS
                edge_index = edge_panels[panel]
                variable_index = variable_panels[panel]
                values = {
                    "var_to_check": (nu_current, nu_current[edge_index]),
                    "check_to_var": (mu, mu[edge_index]),
                    "lambda_bias": (lambda_bias, lambda_bias[variable_index]),
                    "marginals": (marginals, marginals[variable_index]),
                }
                leg_stats = by_leg.setdefault(leg_index, new_stats())
                iteration_stats = by_iteration.setdefault(iteration, new_stats())
                for quantity, (full, sampled) in values.items():
                    overall[quantity].update(full, sampled)
                    leg_stats[quantity].update(full, sampled)
                    iteration_stats[quantity].update(full, sampled)
                if shot == 0:
                    max_abs_by_global_iteration.append(
                        {
                            "leg": leg_index,
                            "iteration": iteration,
                            **{quantity: float(np.max(np.abs(full))) for quantity, (full, _) in values.items()},
                        }
                    )
                decision = decoder._hard_decision(marginals)
                total_iterations += 1
                global_iteration += 1
                nu_previous = nu_current
                marginals_previous = marginals
                if not np.any(decoder._syndrome(decision) ^ syndromes[shot]):
                    converged = True
                    break
            initial_marginals = marginals.copy()
            if converged:
                break

    return name, {
        "configuration": name,
        "shots": SHOTS,
        "total_iterations_observed": total_iterations,
        "percentile_method": (
            f"deterministic {SAMPLE_PANELS}-panel sampling of {SAMPLE_PANEL_SIZE} nodes/edges per iteration; "
            "exact full-array min/max; log10 histogram bin width 0.05 decade"
        ),
        "overall": {"physical_priors": physical.result(), **{key: value.result() for key, value in overall.items()}},
        "by_leg": {
            str(leg): {key: value.result() for key, value in stats.items()} for leg, stats in sorted(by_leg.items())
        },
        "by_iteration_within_leg": {
            str(iteration): {key: value.result() for key, value in stats.items()}
            for iteration, stats in sorted(by_iteration.items())
        },
        "shot_zero_max_abs_evolution": max_abs_by_global_iteration,
    }


def make_fixed(name: str, h: sparse.csr_matrix, shot: int, width: int, scale: int) -> FixedRelayBPDecoder:
    legs = (
        FixedRelayLegConfig(max_iterations=80, gamma=CONFIGS[name]["first_gamma"]),
        *(
            FixedRelayLegConfig(max_iterations=60, gamma_range=CONFIGS[name]["interval"])
            for _ in range(CONFIGS[name]["R"] - 1)
        ),
    )
    return FixedRelayBPDecoder(
        h,
        FixedRelayConfig(
            fixed=FixedConfig(b=width, g=GUARD_BITS, M=scale, clip=None, separate_scale=True),
            leg_configs=legs,
            S=1,
            R=CONFIGS[name]["R"],
            seed=DECODER_SEED + shot,
        ),
    )


def run_wide_fixed(name: str, width: int, scale: int) -> list[dict[str, object]]:
    h, action, probabilities, syndromes, logicals = load_problem()
    lambdas = np.log((1.0 - probabilities) / probabilities)
    with np.load(FLOAT_SOURCE / "float_corrections.npz") as data:
        oracle_corrections = data[name]
    oracle_rows = json.loads((FLOAT_SOURCE / "float_per_shot.json").read_text(encoding="utf-8"))[name]
    rows = []
    for shot in range(SHOTS):
        result = make_fixed(name, h, shot, width, scale).decode(lambdas, syndromes[shot])
        decision = result.decoded_error
        syndrome_valid = bool(np.array_equal(np.asarray(h @ decision).reshape(-1) & 1, syndromes[shot]))
        logical_match = bool(np.array_equal(np.asarray(action @ decision).reshape(-1) & 1, logicals[shot]))
        oracle_logical = bool(oracle_rows[shot]["logically_correct"])
        rows.append(
            {
                "configuration": name,
                "b": width,
                "M": scale,
                "shot": shot,
                "syndrome_converged": int(syndrome_valid),
                "logically_correct": int(syndrome_valid and logical_match),
                "logical_classification_agrees_with_float": int((syndrome_valid and logical_match) == oracle_logical),
                "decision_agrees_with_float": int(np.array_equal(decision, oracle_corrections[shot])),
                "decision_hamming_distance": int(np.count_nonzero(decision ^ oracle_corrections[shot])),
                "iterations": result.total_iterations,
                "relay_legs": result.relay_legs,
                "iterations_agree_with_float": int(result.total_iterations == oracle_rows[shot]["iterations"]),
                "legs_agree_with_float": int(result.relay_legs == oracle_rows[shot]["relay_legs"]),
                "selected_solution_weight": (
                    float(result.metadata["best_weight"])
                    if result.metadata["best_weight"] is not None
                    else None
                ),
                **{f"saturation_{key}": int(value) for key, value in result.saturation_counts.items()},
            }
        )
        for key in ("physical_prior", "lambda_bias", "check_messages", "guard_accumulator", "variable_messages", "marginals"):
            rows[-1].setdefault(f"saturation_{key}", 0)
    return rows


def summarize_wide(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output = []
    for name in CONFIGS:
        for width in WIDTHS:
            for scale in SCALES:
                group = [row for row in rows if row["configuration"] == name and row["b"] == width and row["M"] == scale]
                iterations = np.asarray([row["iterations"] for row in group])
                total_iterations = int(iterations.sum())
                saturation = {
                    key.removeprefix("saturation_"): int(sum(row[key] for row in group))
                    for key in group[0] if key.startswith("saturation_")
                }
                output.append(
                    {
                        "configuration": name,
                        "b": width,
                        "M": scale,
                        "guard_bits": GUARD_BITS,
                        "logical_successes": int(sum(row["logically_correct"] for row in group)),
                        "syndrome_converged": int(sum(row["syndrome_converged"] for row in group)),
                        "logical_classification_agreement_shots": int(sum(row["logical_classification_agrees_with_float"] for row in group)),
                        "exact_correction_agreement_shots": int(sum(row["decision_agrees_with_float"] for row in group)),
                        "mean_correction_hamming_distance": float(np.mean([row["decision_hamming_distance"] for row in group])),
                        "iteration_agreement_shots": int(sum(row["iterations_agree_with_float"] for row in group)),
                        "leg_agreement_shots": int(sum(row["legs_agree_with_float"] for row in group)),
                        "average_iterations": float(np.mean(iterations)),
                        "p99_iterations": float(np.percentile(iterations, 99)),
                        "average_relay_legs": float(np.mean([row["relay_legs"] for row in group])),
                        "average_selected_solution_weight": (
                            float(np.mean([row["selected_solution_weight"] for row in group if row["selected_solution_weight"] is not None]))
                            if any(row["selected_solution_weight"] is not None for row in group)
                            else None
                        ),
                        "saturation_counts": saturation,
                        "saturation_rates": {
                            "physical_prior": saturation["physical_prior"] / (SHOTS * 67752),
                            "variable_messages": saturation["variable_messages"] / (total_iterations * 391320),
                            "marginals": saturation["marginals"] / (total_iterations * 67752),
                            "guard_accumulator": saturation["guard_accumulator"] / (total_iterations * 67752),
                        },
                    }
                )
    return output


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dynamic = {}
    with ProcessPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(measure_float_range, name): name for name in CONFIGS}
        for future in as_completed(futures):
            name, result = future.result()
            dynamic[name] = result
            print(f"completed float dynamic range {name}", flush=True)
    (OUT_DIR / "float_dynamic_range.json").write_text(json.dumps(dynamic, indent=2) + "\n", encoding="utf-8")

    rows = []
    tasks = [(name, width, scale) for name in CONFIGS for width in WIDTHS for scale in SCALES]
    with ProcessPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(run_wide_fixed, *task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            rows.extend(future.result())
            print(f"completed wide fixed config={task[0]} b={task[1]} M={task[2]}", flush=True)
    rows.sort(key=lambda row: (row["configuration"], row["b"], row["M"], row["shot"]))
    with (OUT_DIR / "per_shot_results.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = summarize_wide(rows)
    (OUT_DIR / "wide_fixed_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    tier2_manifest = json.loads((TIER2_DIR / "manifest.json").read_text(encoding="utf-8"))
    manifest = {
        "study": "Tier-2 float dynamic range and wider fixed-point characterization",
        "shots": {"count": SHOTS, "sample_seed": SAMPLE_SEED, "paired": True},
        "graph": {
            "package": str(TIER2_DIR.relative_to(PROJECT_ROOT)),
            "dimensions": {"detectors": 1728, "faults": 67752, "logical_observables": 12},
            "package_manifest_sha256": sha256(TIER2_DIR / "manifest.json"),
            "detector_incidence_sha256": tier2_manifest["graph"]["detector_incidence_sha256"],
        },
        "configurations": CONFIGS,
        "fixed_formats": {"b": list(WIDTHS), "M": list(SCALES), "guard_bits": GUARD_BITS},
        "dynamic_range_method": {
            "min_max": "exact over every full float array at every executed iteration",
            "percentiles": "estimated by deterministic sampled panels and 0.05-decade log histogram",
            "panel_size": SAMPLE_PANEL_SIZE,
            "panels": SAMPLE_PANELS,
        },
        "scaling_part_c": {
            "evaluated": False,
            "reason": "filled after reviewing measured distributions; no arbitrary scale is applied by this script",
        },
        "software": {
            "float_oracle_sha256": sha256(REFERENCE_DIR / "relay_bp_float.py"),
            "fixed_decoder_sha256": sha256(REFERENCE_DIR / "relay_bp_fixed.py"),
        },
        "artifacts": ["manifest.json", "float_dynamic_range.json", "wide_fixed_summary.json", "per_shot_results.csv", "run_dynamic_range.py"],
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

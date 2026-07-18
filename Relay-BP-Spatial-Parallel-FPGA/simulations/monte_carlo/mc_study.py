"""
Monte Carlo study orchestration for Sequential Relay-BP versus Parallel Relay-BP.

This module ties together the random trial generator, the sequential Relay
decoder, the parallel Relay decoder, and the reporting schema. The code keeps
the simulation logic reusable so a later notebook or script can import the
same study class without depending on the CLI entry point.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Sequence

import numpy as np


CURRENT_DIR = Path(__file__).resolve().parent
SEQUENTIAL_DIR = CURRENT_DIR.parent / "sequential_relay"
PARALLEL_DIR = CURRENT_DIR.parent / "parallel_relay"
for search_path in (CURRENT_DIR, SEQUENTIAL_DIR, PARALLEL_DIR):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from mc_models import (
    MonteCarloConfig,
    MonteCarloRunResult,
    MonteCarloSummary,
    MonteCarloTrialRecord,
    format_gamma_schedule_text,
    format_histogram_text,
)
from mc_trials import MonteCarloTrialGenerator, build_monte_carlo_matrix
from parallel_relay_decoder import ParallelRelayDecoder, ParallelRelayLaneConfig
from relay_bp_decoder import RelayBPDecoder, RelayDecoderConfig, RelayLegConfig


def _build_relay_leg_configs(gamma_schedules: Sequence[Sequence[float]], carry_gammas: Sequence[float]) -> list[RelayLegConfig]:
    """Convert gamma and carry schedules into Relay leg configuration objects."""
    if len(gamma_schedules) != len(carry_gammas):
        raise ValueError("gamma_schedules and carry_gammas must have the same length")

    return [
        RelayLegConfig(gamma_schedule=list(gamma_schedule), carry_gamma=float(carry_gamma))
        for gamma_schedule, carry_gamma in zip(gamma_schedules, carry_gammas)
    ]


def _build_parallel_lane_configs(config: MonteCarloConfig) -> list[ParallelRelayLaneConfig]:
    """Convert the Monte Carlo configuration into per-lane parallel configs."""
    if len(config.parallel_lane_labels) != len(config.parallel_lane_gamma_schedules):
        raise ValueError("parallel_lane_labels and parallel_lane_gamma_schedules must have the same length")
    if len(config.parallel_lane_seeds) != len(config.parallel_lane_gamma_schedules):
        raise ValueError("parallel_lane_seeds and parallel_lane_gamma_schedules must have the same length")
    if len(config.parallel_lane_carry_gammas) != len(config.parallel_lane_gamma_schedules):
        raise ValueError("parallel_lane_carry_gammas and parallel_lane_gamma_schedules must have the same length")

    lane_configs: list[ParallelRelayLaneConfig] = []
    for label, seed, lane_gamma_schedules, lane_carry_gammas in zip(
        config.parallel_lane_labels,
        config.parallel_lane_seeds,
        config.parallel_lane_gamma_schedules,
        config.parallel_lane_carry_gammas,
    ):
        relay_legs = _build_relay_leg_configs(lane_gamma_schedules, lane_carry_gammas)
        lane_configs.append(
            ParallelRelayLaneConfig(
                label=label,
                seed=seed,
                relay_config=RelayDecoderConfig(
                    leg_configs=relay_legs,
                    max_iterations_per_leg=config.relay_max_iterations_per_leg,
                    damping=config.relay_damping,
                ),
            )
        )
    return lane_configs


def _build_sequential_decoder(config: MonteCarloConfig, matrix) -> RelayBPDecoder:
    """Build the baseline sequential Relay decoder used in the study."""
    relay_legs = _build_relay_leg_configs(config.sequential_gamma_schedules, config.sequential_carry_gammas)
    relay_config = RelayDecoderConfig(
        leg_configs=relay_legs,
        max_iterations_per_leg=config.relay_max_iterations_per_leg,
        damping=config.relay_damping,
    )
    return RelayBPDecoder(matrix, relay_config, seed=config.base_seed)


def _build_parallel_decoder(config: MonteCarloConfig, matrix) -> ParallelRelayDecoder:
    """Build the concurrent multi-lane Relay decoder used in the study."""
    return ParallelRelayDecoder(matrix, _build_parallel_lane_configs(config))


class MonteCarloStudy:
    """Run a Monte Carlo comparison between sequential and parallel Relay-BP."""

    def __init__(self, config: MonteCarloConfig):
        self.config = config
        self.matrix = build_monte_carlo_matrix(
            n_checks=config.matrix_checks,
            n_variables=config.matrix_variables,
            ones_per_variable=config.ones_per_variable,
            seed=config.matrix_seed,
        )
        self.trial_generator = MonteCarloTrialGenerator(
            matrix=self.matrix,
            error_rate=config.error_rate,
            llr_magnitude=config.llr_magnitude,
            llr_noise_std=config.llr_noise_std,
        )
        self.sequential_decoder = _build_sequential_decoder(config, self.matrix)
        self.parallel_decoder = _build_parallel_decoder(config, self.matrix)

    def run(self) -> MonteCarloRunResult:
        """Execute the configured number of trials and return the full result set."""
        trial_samples = self.trial_generator.generate_trials(self.config.trial_count, self.config.base_seed)
        trial_records: list[MonteCarloTrialRecord] = []

        sequential_latencies_ms: list[float] = []
        parallel_latencies_ms: list[float] = []
        sequential_iterations: list[int] = []
        parallel_iterations: list[int] = []
        sequential_successes = 0
        parallel_successes = 0
        lane_histogram: dict[int, int] = {}

        sequential_schedule_text = format_gamma_schedule_text(self.config.sequential_gamma_schedules)

        for trial_sample in trial_samples:
            sequential_result = self.sequential_decoder.decode(
                trial_sample.prior_llr.copy(),
                trial_sample.syndrome.copy(),
            )
            parallel_result = self.parallel_decoder.decode(
                trial_sample.prior_llr.copy(),
                trial_sample.syndrome.copy(),
            )

            winning_lane_result = None
            if parallel_result.winning_lane is not None:
                winning_lane_result = next(
                    (lane_result for lane_result in parallel_result.lane_results if lane_result.lane_index == parallel_result.winning_lane),
                    None,
                )

            if sequential_result.converged:
                sequential_successes += 1
            if parallel_result.converged:
                parallel_successes += 1
                if parallel_result.winning_lane is not None:
                    lane_histogram[parallel_result.winning_lane] = lane_histogram.get(parallel_result.winning_lane, 0) + 1

            sequential_latency_ms = sequential_result.latency_seconds * 1e3
            if parallel_result.converged and parallel_result.convergence_time_seconds is not None:
                parallel_effective_latency_ms = parallel_result.convergence_time_seconds * 1e3
                parallel_convergence_time_ms = parallel_effective_latency_ms
            else:
                parallel_effective_latency_ms = parallel_result.total_latency_seconds * 1e3
                parallel_convergence_time_ms = None

            sequential_iterations_value = sequential_result.total_iterations
            if winning_lane_result is not None:
                parallel_iterations_value = winning_lane_result.total_iterations
                parallel_relay_legs = winning_lane_result.relay_legs
                parallel_gamma_text = format_gamma_schedule_text(parallel_result.winning_gamma_schedule or [])
            else:
                parallel_iterations_value = max((lane_result.total_iterations for lane_result in parallel_result.lane_results), default=0)
                parallel_relay_legs = max((lane_result.relay_legs for lane_result in parallel_result.lane_results), default=0)
                parallel_gamma_text = None

            latency_improvement_percent = 0.0
            if sequential_latency_ms > 0:
                latency_improvement_percent = 100.0 * (sequential_latency_ms - parallel_effective_latency_ms) / sequential_latency_ms

            trial_records.append(
                MonteCarloTrialRecord(
                    trial_index=trial_sample.trial_index,
                    error_weight=trial_sample.error_weight,
                    syndrome_weight=trial_sample.syndrome_weight,
                    sequential_converged=sequential_result.converged,
                    sequential_relay_legs=sequential_result.relay_legs,
                    sequential_iterations=sequential_iterations_value,
                    sequential_latency_ms=sequential_latency_ms,
                    sequential_gamma_schedule=sequential_schedule_text,
                    parallel_converged=parallel_result.converged,
                    parallel_winning_lane=parallel_result.winning_lane,
                    parallel_winning_label=parallel_result.winning_label,
                    parallel_relay_legs=parallel_relay_legs,
                    parallel_iterations=parallel_iterations_value,
                    parallel_convergence_time_ms=parallel_convergence_time_ms,
                    parallel_total_latency_ms=parallel_result.total_latency_seconds * 1e3,
                    parallel_effective_latency_ms=parallel_effective_latency_ms,
                    parallel_gamma_schedule=parallel_gamma_text,
                    latency_improvement_percent=latency_improvement_percent,
                )
            )

            sequential_latencies_ms.append(sequential_latency_ms)
            parallel_latencies_ms.append(parallel_effective_latency_ms)
            sequential_iterations.append(sequential_iterations_value)
            parallel_iterations.append(parallel_iterations_value)

        summary = MonteCarloSummary(
            trial_count=len(trial_records),
            sequential_average_latency_ms=float(np.mean(sequential_latencies_ms)) if sequential_latencies_ms else 0.0,
            parallel_average_latency_ms=float(np.mean(parallel_latencies_ms)) if parallel_latencies_ms else 0.0,
            sequential_worst_latency_ms=float(np.max(sequential_latencies_ms)) if sequential_latencies_ms else 0.0,
            parallel_worst_latency_ms=float(np.max(parallel_latencies_ms)) if parallel_latencies_ms else 0.0,
            sequential_average_iterations=float(np.mean(sequential_iterations)) if sequential_iterations else 0.0,
            parallel_average_iterations=float(np.mean(parallel_iterations)) if parallel_iterations else 0.0,
            sequential_success_rate=(sequential_successes / len(trial_records)) if trial_records else 0.0,
            parallel_success_rate=(parallel_successes / len(trial_records)) if trial_records else 0.0,
            average_latency_improvement_percent=float(np.mean([record.latency_improvement_percent for record in trial_records])) if trial_records else 0.0,
            parallel_winning_lane_histogram_text=format_histogram_text(lane_histogram),
        )

        return MonteCarloRunResult(summary=summary, trial_records=trial_records)

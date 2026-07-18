"""
Parallel Relay-BP simulator.

This module extends the sequential baseline into a multi-lane behavioral
simulator. Each lane receives the same syndrome and prior information, but
uses a different gamma schedule. The lanes are advanced in lockstep so the
simulator can identify the first successful decode and compare the parallel
result against the sequential baseline.

The implementation is intentionally research-oriented rather than hardware-
accurate. It is meant to measure lane-level convergence behavior, first-
success latency, and baseline-vs-parallel differences before FPGA work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

import sys


SEQUENTIAL_DIR = Path(__file__).resolve().parent.parent / "sequential_relay"
if str(SEQUENTIAL_DIR) not in sys.path:
    sys.path.insert(0, str(SEQUENTIAL_DIR))

from sequential_relay_bp_sim import (  # type: ignore  # noqa: E402
    BatchSummary,
    QCParityCheckMatrix,
    RelayBPConfig,
    RelayBPDecodeResult,
    SequentialRelayBPDecoder,
    SequentialRelayBPSimulator,
    TrialData,
    build_synthetic_qc_matrix,
)


@dataclass(frozen=True)
class ParallelLaneConfig:
    """Configuration for one parallel Relay-BP lane."""

    gamma_schedule: Sequence[float]
    seed: int


@dataclass
class ParallelRelayLaneResult:
    """Per-lane result data recorded by the parallel simulator."""

    lane_index: int
    converged: bool
    iterations: int
    latency_seconds: float
    residual_weight: int
    decoded_error: np.ndarray


@dataclass
class ParallelRelayLaneState:
    """Mutable state for one lane running inside the lockstep simulator."""

    lane_index: int
    gamma_schedule: Sequence[float]
    seed: int
    noise_std: float
    var_to_checks: list[list[int]]
    check_to_vars: list[list[int]]
    syndrome: np.ndarray
    prior_llr: np.ndarray
    rng: np.random.Generator
    llr_current: np.ndarray
    llr_previous: np.ndarray
    msg_v2c: dict[tuple[int, int], float]
    iterations: int = 0
    converged: bool = False
    latency_seconds: float = 0.0
    residual_weight: int = 0
    decoded_error: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.uint8))

    @classmethod
    def create(
        cls,
        lane_index: int,
        matrix: QCParityCheckMatrix,
        lane_config: ParallelLaneConfig,
        noise_std: float,
        trial: TrialData,
    ) -> "ParallelRelayLaneState":
        var_to_checks, check_to_vars = matrix.neighbors()
        prior_llr = trial.prior_llr.astype(float).copy()
        llr_current = prior_llr.copy()
        llr_previous = llr_current.copy()
        msg_v2c = {
            (variable_index, check_index): float(trial.prior_llr[variable_index])
            for variable_index, checks in enumerate(var_to_checks)
            for check_index in checks
        }
        rng = np.random.default_rng(lane_config.seed)
        decoded_error = (llr_current < 0).astype(np.uint8)
        return cls(
            lane_index=lane_index,
            gamma_schedule=lane_config.gamma_schedule,
            seed=lane_config.seed,
            noise_std=noise_std,
            var_to_checks=var_to_checks,
            check_to_vars=check_to_vars,
            syndrome=trial.syndrome,
            prior_llr=prior_llr,
            rng=rng,
            llr_current=llr_current,
            llr_previous=llr_previous,
            msg_v2c=msg_v2c,
            decoded_error=decoded_error,
        )

    def _hard_decision(self) -> np.ndarray:
        return (self.llr_current < 0).astype(np.uint8)

    def _residual_weight(self, decoded_error: np.ndarray) -> int:
        residual = self.syndrome.copy()
        for row_index, vars_in_check in enumerate(self.check_to_vars):
            parity = 0
            for variable_index in vars_in_check:
                parity ^= decoded_error[variable_index]
            residual[row_index] ^= parity
        return int(np.sum(residual))

    def _check_node_update(self) -> dict[tuple[int, int], float]:
        msg_c2v: dict[tuple[int, int], float] = {}
        for check_index, vars_in_check in enumerate(self.check_to_vars):
            syndrome_sign = -1 if self.syndrome[check_index] else 1
            for variable_index in vars_in_check:
                incoming = [self.msg_v2c[(neighbor, check_index)] for neighbor in vars_in_check if neighbor != variable_index]
                if not incoming:
                    msg_c2v[(check_index, variable_index)] = 0.0
                    continue

                sign_product = 1
                for value in incoming:
                    sign_product *= 1 if value >= 0 else -1
                magnitude = min(abs(value) for value in incoming)
                msg_c2v[(check_index, variable_index)] = syndrome_sign * sign_product * magnitude
        return msg_c2v

    def step(self, iteration_index: int, iteration_time_seconds: float) -> None:
        if self.converged:
            return

        gamma_schedule = list(self.gamma_schedule)
        gamma = gamma_schedule[min(iteration_index, len(gamma_schedule) - 1)] if gamma_schedule else 0.0
        msg_c2v = self._check_node_update()

        llr_next = self.prior_llr.copy()
        for variable_index, checks in enumerate(self.var_to_checks):
            incoming_sum = sum(msg_c2v[(check_index, variable_index)] for check_index in checks)
            noise = self.rng.normal(0.0, self.noise_std)
            llr_next[variable_index] = self.prior_llr[variable_index] + incoming_sum + gamma * self.llr_previous[variable_index] + noise

            for check_index in checks:
                self.msg_v2c[(variable_index, check_index)] = llr_next[variable_index] - msg_c2v[(check_index, variable_index)]

        self.llr_previous = self.llr_current
        self.llr_current = llr_next
        self.decoded_error = self._hard_decision()
        self.residual_weight = self._residual_weight(self.decoded_error)
        self.iterations = iteration_index + 1
        self.latency_seconds = self.iterations * iteration_time_seconds
        self.converged = self.residual_weight == 0


@dataclass
class ParallelRelayDecodeResult:
    """Result for a single parallel decode attempt."""

    converged: bool
    winning_lane: int | None
    winning_iterations: int
    winning_latency_seconds: float
    total_iterations: int
    lane_results: list[ParallelLaneResult] = field(default_factory=list)
    sequential_comparison: RelayBPDecodeResult | None = None


class ParallelRelayBPSimulator:
    """Multi-lane Relay-BP simulator with first-success arbitration."""

    def __init__(self, parity_check_matrix: QCParityCheckMatrix, lane_configs: Sequence[ParallelLaneConfig], max_iterations: int = 60, noise_std: float = 0.35):
        if not lane_configs:
            raise ValueError("lane_configs must contain at least one lane")

        self.matrix = parity_check_matrix
        self.lane_configs = list(lane_configs)
        self.max_iterations = max_iterations
        self.noise_std = noise_std
        self._sequential_baseline = SequentialRelayBPSimulator(
            parity_check_matrix,
            RelayBPConfig(
                gamma_schedule=self.lane_configs[0].gamma_schedule,
                max_iterations=max_iterations,
                noise_std=noise_std,
                seed=self.lane_configs[0].seed,
            ),
        )

    def generate_trial(self, error_rate: float, seed: int) -> TrialData:
        return self._sequential_baseline.generate_trial(error_rate=error_rate, seed=seed)

    def run_trial(self, trial: TrialData) -> ParallelRelayDecodeResult:
        """Run all lanes in lockstep and return the first successful decode."""
        iteration_time_seconds = 1e-3
        lane_states = [
            ParallelRelayLaneState.create(
                lane_index=index,
                matrix=self.matrix,
                lane_config=lane_config,
                noise_std=self.noise_std,
                trial=trial,
            )
            for index, lane_config in enumerate(self.lane_configs)
        ]

        winning_lane: int | None = None
        winning_iterations = self.max_iterations
        winning_latency_seconds = self.max_iterations * iteration_time_seconds

        for iteration_index in range(self.max_iterations):
            for lane_state in lane_states:
                lane_state.step(iteration_index, iteration_time_seconds)
                if lane_state.converged and winning_lane is None:
                    winning_lane = lane_state.lane_index
                    winning_iterations = lane_state.iterations
                    winning_latency_seconds = lane_state.latency_seconds

            if winning_lane is not None:
                break

        lane_results = [
            ParallelRelayLaneResult(
                lane_index=lane_state.lane_index,
                converged=lane_state.converged,
                iterations=lane_state.iterations,
                latency_seconds=lane_state.latency_seconds,
                residual_weight=lane_state.residual_weight,
                decoded_error=lane_state.decoded_error,
            )
            for lane_state in lane_states
        ]
        converged = winning_lane is not None
        total_iterations = sum(lane_state.iterations for lane_state in lane_states)

        sequential_result = self._sequential_baseline.run_trial(trial)
        return ParallelRelayDecodeResult(
            converged=converged,
            winning_lane=winning_lane,
            winning_iterations=winning_iterations,
            winning_latency_seconds=winning_latency_seconds,
            total_iterations=total_iterations,
            lane_results=lane_results,
            sequential_comparison=sequential_result,
        )

    def run_batch(self, trials: Sequence[TrialData]) -> list[ParallelRelayDecodeResult]:
        return [self.run_trial(trial) for trial in trials]


@dataclass
class ParallelBatchSummary:
    """Aggregate metrics for a set of parallel decode attempts."""

    results: list[ParallelRelayDecodeResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.results if result.converged)

    @property
    def failure_count(self) -> int:
        return len(self.results) - self.success_count

    @property
    def average_winning_latency_seconds(self) -> float:
        if not self.results:
            return 0.0
        return float(np.mean([result.winning_latency_seconds for result in self.results]))

    @property
    def average_winning_iterations(self) -> float:
        if not self.results:
            return 0.0
        return float(np.mean([result.winning_iterations for result in self.results]))

    @property
    def first_lane_histogram(self) -> dict[int, int]:
        histogram: dict[int, int] = {}
        for result in self.results:
            if result.winning_lane is None:
                continue
            histogram[result.winning_lane] = histogram.get(result.winning_lane, 0) + 1
        return histogram


def _compare_against_sequential(parallel_result: ParallelRelayDecodeResult) -> str:
    if parallel_result.sequential_comparison is None:
        return "No sequential comparison available."

    sequential = parallel_result.sequential_comparison
    parallel_latency_ms = parallel_result.winning_latency_seconds * 1e3
    sequential_latency_ms = sequential.latency_seconds * 1e3
    latency_delta_ms = sequential_latency_ms - parallel_latency_ms
    iteration_delta = sequential.iterations - parallel_result.winning_iterations

    return (
        f"Sequential latency: {sequential_latency_ms:.3f} ms | "
        f"Parallel winning latency: {parallel_latency_ms:.3f} ms | "
        f"Latency gain: {latency_delta_ms:.3f} ms | "
        f"Iteration gain: {iteration_delta}"
    )


def _print_result(result: ParallelRelayDecodeResult) -> None:
    print("Parallel Relay-BP trial result")
    print("-" * 40)
    print(f"Converged:        {result.converged}")
    print(f"Winning lane:     {result.winning_lane}")
    print(f"Winning iters:    {result.winning_iterations}")
    print(f"Winning latency:  {result.winning_latency_seconds * 1e3:.3f} ms")
    print(f"Total iterations: {result.total_iterations}")
    print(_compare_against_sequential(result))
    print("Per-lane results:")
    for lane_result in result.lane_results:
        print(
            f"  lane {lane_result.lane_index}: converged={lane_result.converged} "
            f"iters={lane_result.iterations} latency={lane_result.latency_seconds * 1e3:.3f} ms "
            f"residual={lane_result.residual_weight}"
        )


def _print_batch_summary(summary: ParallelBatchSummary) -> None:
    winning_latencies = np.array([result.winning_latency_seconds for result in summary.results], dtype=float)
    winning_iterations = np.array([result.winning_iterations for result in summary.results], dtype=float)
    print("Parallel Relay-BP batch summary")
    print("-" * 40)
    print(f"Trials:                   {len(summary.results)}")
    print(f"Successes:                {summary.success_count}")
    print(f"Failures:                 {summary.failure_count}")
    print(f"Average winning latency:  {summary.average_winning_latency_seconds * 1e3:.3f} ms")
    print(f"Average winning iters:    {summary.average_winning_iterations:.2f}")
    if summary.results:
        print(f"p95 winning latency:      {np.percentile(winning_latencies, 95) * 1e3:.3f} ms")
        print(f"p95 winning iterations:   {np.percentile(winning_iterations, 95):.2f}")
    print(f"Winning lane histogram:   {summary.first_lane_histogram}")


def main() -> None:
    """Run a small demonstration of the parallel Relay-BP simulator."""
    matrix = build_synthetic_qc_matrix(seed=1)
    lane_configs = [
        ParallelLaneConfig(gamma_schedule=[0.05, 0.10, 0.15, 0.15, 0.20, 0.25], seed=11),
        ParallelLaneConfig(gamma_schedule=[0.00, 0.20, 0.45, 0.60, 0.70, 0.75], seed=22),
        ParallelLaneConfig(gamma_schedule=[0.40, 0.40, 0.40, 0.40, 0.40, 0.40], seed=33),
        ParallelLaneConfig(gamma_schedule=[0.10, 0.25, 0.45, 0.65, 0.75, 0.80], seed=44),
    ]
    simulator = ParallelRelayBPSimulator(matrix, lane_configs, max_iterations=60, noise_std=0.35)

    trial = simulator.generate_trial(error_rate=0.13, seed=1000)
    result = simulator.run_trial(trial)
    _print_result(result)

    trials = [simulator.generate_trial(error_rate=0.13, seed=1000 + index) for index in range(20)]
    batch_summary = ParallelBatchSummary(results=simulator.run_batch(trials))
    _print_batch_summary(batch_summary)


if __name__ == "__main__":
    main()
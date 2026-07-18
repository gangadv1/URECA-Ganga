"""
Sequential Relay-BP simulator for a baseline quantum LDPC decoding study.

This module provides a clean, class-based behavioral simulator for a single
Relay-BP decoding trajectory executed sequentially. It is intentionally not a
hardware model. The goal is to support early-stage research measurements such
as iteration count, convergence behavior, decode latency, and success/failure
rate before any FPGA HLS or RTL work begins.

The decoder uses a lightweight min-sum belief-propagation proxy with a
Relay-style memory term controlled by a configurable gamma schedule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import List, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Parity-check matrix representation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QCParityCheckMatrix:
    """Block-circulant parity-check matrix stored as a compact shift table."""

    block_rows: int
    block_cols: int
    block_size: int
    shift_table: np.ndarray

    def __post_init__(self) -> None:
        expected_shape = (self.block_rows, self.block_cols)
        if self.shift_table.shape != expected_shape:
            raise ValueError(f"shift_table must have shape {expected_shape}, got {self.shift_table.shape}")

    @property
    def n_rows(self) -> int:
        return self.block_rows * self.block_size

    @property
    def n_cols(self) -> int:
        return self.block_cols * self.block_size

    def syndrome(self, error_vector: np.ndarray) -> np.ndarray:
        """Compute Hx mod 2 using the compact QC representation."""
        if error_vector.shape != (self.n_cols,):
            raise ValueError(f"error_vector must have shape {(self.n_cols,)}, got {error_vector.shape}")

        syn = np.zeros(self.n_rows, dtype=np.uint8)
        for br in range(self.block_rows):
            for bc in range(self.block_cols):
                shift = int(self.shift_table[br, bc])
                if shift < 0:
                    continue
                for row_offset in range(self.block_size):
                    col_offset = (row_offset + shift) % self.block_size
                    row_index = br * self.block_size + row_offset
                    col_index = bc * self.block_size + col_offset
                    syn[row_index] ^= error_vector[col_index]
        return syn

    def neighbors(self) -> tuple[list[list[int]], list[list[int]]]:
        """Build variable-to-check and check-to-variable adjacency lists."""
        var_to_checks = [[] for _ in range(self.n_cols)]
        check_to_vars = [[] for _ in range(self.n_rows)]

        for br in range(self.block_rows):
            for bc in range(self.block_cols):
                shift = int(self.shift_table[br, bc])
                if shift < 0:
                    continue
                for row_offset in range(self.block_size):
                    col_offset = (row_offset + shift) % self.block_size
                    row_index = br * self.block_size + row_offset
                    col_index = bc * self.block_size + col_offset
                    var_to_checks[col_index].append(row_index)
                    check_to_vars[row_index].append(col_index)

        return var_to_checks, check_to_vars


@dataclass(frozen=True)
class TrialData:
    """Input data for a single decode attempt."""

    syndrome: np.ndarray
    prior_llr: np.ndarray
    true_error: np.ndarray | None = None


@dataclass(frozen=True)
class RelayBPConfig:
    """Configuration parameters for the sequential Relay-BP decoder."""

    gamma_schedule: Sequence[float]
    max_iterations: int = 60
    noise_std: float = 0.35
    seed: int = 0


@dataclass
class RelayBPDecodeResult:
    """Output metrics for one sequential decode attempt."""

    converged: bool
    iterations: int
    total_iterations: int
    latency_seconds: float
    residual_weight: int
    decoded_error: np.ndarray


@dataclass
class BatchSummary:
    """Aggregate results for a collection of decode trials."""

    trial_results: List[RelayBPDecodeResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.trial_results if result.converged)

    @property
    def failure_count(self) -> int:
        return len(self.trial_results) - self.success_count

    @property
    def average_iterations(self) -> float:
        if not self.trial_results:
            return 0.0
        return float(np.mean([result.iterations for result in self.trial_results]))

    @property
    def average_latency_seconds(self) -> float:
        if not self.trial_results:
            return 0.0
        return float(np.mean([result.latency_seconds for result in self.trial_results]))


# ---------------------------------------------------------------------------
# Sequential Relay-BP decoder
# ---------------------------------------------------------------------------


class SequentialRelayBPDecoder:
    """Sequential baseline Relay-BP decoder.

    The decoder runs one trajectory at a time. It uses a min-sum BP proxy with
    a Relay-style memory term that is controlled by a configurable gamma
    schedule. This provides a research-friendly baseline for iteration counts,
    convergence behavior, latency, and success/failure statistics.
    """

    def __init__(self, parity_check_matrix: QCParityCheckMatrix, config: RelayBPConfig):
        self.matrix = parity_check_matrix
        self.config = config
        self._rng = np.random.default_rng(config.seed)
        self._var_to_checks, self._check_to_vars = self.matrix.neighbors()

    def _hard_decision(self, llr: np.ndarray) -> np.ndarray:
        return (llr < 0).astype(np.uint8)

    def _residual_weight(self, decoded_error: np.ndarray, syndrome: np.ndarray) -> int:
        residual = self.matrix.syndrome(decoded_error) ^ syndrome
        return int(np.sum(residual))

    def _check_node_update(self, msg_v2c: dict[tuple[int, int], float], syndrome: np.ndarray) -> dict[tuple[int, int], float]:
        """Compute check-to-variable messages using the min-sum rule."""
        msg_c2v: dict[tuple[int, int], float] = {}
        for check_index, vars_in_check in enumerate(self._check_to_vars):
            syndrome_sign = -1 if syndrome[check_index] else 1
            for variable_index in vars_in_check:
                incoming = [msg_v2c[(neighbor, check_index)] for neighbor in vars_in_check if neighbor != variable_index]
                if not incoming:
                    msg_c2v[(check_index, variable_index)] = 0.0
                    continue

                sign_product = 1
                for value in incoming:
                    sign_product *= 1 if value >= 0 else -1
                magnitude = min(abs(value) for value in incoming)
                msg_c2v[(check_index, variable_index)] = syndrome_sign * sign_product * magnitude
        return msg_c2v

    def decode(self, trial: TrialData) -> RelayBPDecodeResult:
        """Decode a single trial sequentially and record the runtime statistics."""
        if trial.syndrome.shape != (self.matrix.n_rows,):
            raise ValueError(f"syndrome must have shape {(self.matrix.n_rows,)}, got {trial.syndrome.shape}")
        if trial.prior_llr.shape != (self.matrix.n_cols,):
            raise ValueError(f"prior_llr must have shape {(self.matrix.n_cols,)}, got {trial.prior_llr.shape}")

        start_time = perf_counter()
        gamma_schedule = list(self.config.gamma_schedule)
        max_iterations = self.config.max_iterations

        llr_current = trial.prior_llr.astype(float).copy()
        llr_previous = llr_current.copy()
        decoded_error = self._hard_decision(llr_current)
        total_iterations = 0

        msg_v2c = {
            (variable_index, check_index): float(trial.prior_llr[variable_index])
            for variable_index, checks in enumerate(self._var_to_checks)
            for check_index in checks
        }

        converged = False
        residual_weight = self._residual_weight(decoded_error, trial.syndrome)

        for iteration_index in range(max_iterations):
            gamma = gamma_schedule[min(iteration_index, len(gamma_schedule) - 1)] if gamma_schedule else 0.0
            msg_c2v = self._check_node_update(msg_v2c, trial.syndrome)

            llr_next = trial.prior_llr.astype(float).copy()
            for variable_index, checks in enumerate(self._var_to_checks):
                incoming_sum = sum(msg_c2v[(check_index, variable_index)] for check_index in checks)
                noise = self._rng.normal(0.0, self.config.noise_std)
                llr_next[variable_index] = trial.prior_llr[variable_index] + incoming_sum + gamma * llr_previous[variable_index] + noise

                for check_index in checks:
                    msg_v2c[(variable_index, check_index)] = llr_next[variable_index] - msg_c2v[(check_index, variable_index)]

            llr_previous = llr_current
            llr_current = llr_next
            decoded_error = self._hard_decision(llr_current)
            residual_weight = self._residual_weight(decoded_error, trial.syndrome)
            total_iterations = iteration_index + 1

            if residual_weight == 0:
                converged = True
                break

        latency_seconds = perf_counter() - start_time
        return RelayBPDecodeResult(
            converged=converged,
            iterations=total_iterations,
            total_iterations=total_iterations,
            latency_seconds=latency_seconds,
            residual_weight=residual_weight,
            decoded_error=decoded_error,
        )


# ---------------------------------------------------------------------------
# Trial generation and batch execution
# ---------------------------------------------------------------------------


class SequentialRelayBPSimulator:
    """Utility class for generating trials and running sequential decode sweeps."""

    def __init__(self, parity_check_matrix: QCParityCheckMatrix, config: RelayBPConfig):
        self.matrix = parity_check_matrix
        self.config = config
        self.decoder = SequentialRelayBPDecoder(parity_check_matrix, config)

    def generate_trial(self, error_rate: float, seed: int) -> TrialData:
        """Generate a synthetic qLDPC trial with a noisy LLR prior."""
        rng = np.random.default_rng(seed)
        true_error = (rng.random(self.matrix.n_cols) < error_rate).astype(np.uint8)
        syndrome = self.matrix.syndrome(true_error)
        prior_llr = np.where(true_error == 1, -1.0, 1.0) + rng.normal(0.0, 1.3, size=self.matrix.n_cols)
        return TrialData(syndrome=syndrome, prior_llr=prior_llr, true_error=true_error)

    def run_trial(self, trial: TrialData) -> RelayBPDecodeResult:
        return self.decoder.decode(trial)

    def run_batch(self, trials: Sequence[TrialData]) -> BatchSummary:
        summary = BatchSummary()
        for trial in trials:
            summary.trial_results.append(self.run_trial(trial))
        return summary


def build_synthetic_qc_matrix(block_rows: int = 6, block_cols: int = 6, block_size: int = 64, density: float = 0.45, seed: int = 0) -> QCParityCheckMatrix:
    """Build a synthetic block-circulant parity-check matrix for experiments."""
    rng = np.random.default_rng(seed)
    shift_table = np.full((block_rows, block_cols), -1, dtype=int)
    for br in range(block_rows):
        for bc in range(block_cols):
            if rng.random() < density:
                shift_table[br, bc] = int(rng.integers(0, block_size))
    return QCParityCheckMatrix(block_rows, block_cols, block_size, shift_table)


def _print_summary(summary: BatchSummary) -> None:
    iterations = [result.iterations for result in summary.trial_results]
    latencies = [result.latency_seconds for result in summary.trial_results]
    residuals = [result.residual_weight for result in summary.trial_results]

    print("Sequential Relay-BP batch summary")
    print("-" * 40)
    print(f"Trials:              {len(summary.trial_results)}")
    print(f"Successes:           {summary.success_count}")
    print(f"Failures:            {summary.failure_count}")
    print(f"Average iterations:  {summary.average_iterations:.2f}")
    print(f"Average latency:     {summary.average_latency_seconds * 1e3:.3f} ms")
    if iterations:
        print(f"Max iterations:      {max(iterations)}")
        print(f"Min iterations:      {min(iterations)}")
        print(f"Max latency:         {max(latencies) * 1e3:.3f} ms")
        print(f"Residual weights:    {residuals}")


def main() -> None:
    """Run a small demonstration of the sequential Relay-BP baseline."""
    matrix = build_synthetic_qc_matrix(seed=1)
    config = RelayBPConfig(
        gamma_schedule=[0.05, 0.10, 0.15, 0.15, 0.20, 0.25],
        max_iterations=60,
        noise_std=0.35,
        seed=42,
    )
    simulator = SequentialRelayBPSimulator(matrix, config)

    trials = [simulator.generate_trial(error_rate=0.13, seed=1000 + index) for index in range(20)]
    summary = simulator.run_batch(trials)
    _print_summary(summary)


if __name__ == "__main__":
    main()

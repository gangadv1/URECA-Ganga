"""
Parallel Relay-BP decoder architecture.

This module implements the proposed parallel architecture by instantiating
multiple Relay-BP decoders, feeding each decoder the same syndrome and prior
belief vector, and executing the decoders concurrently with Python threads.
The coordinator records every lane, returns the first successful decoding, and
keeps the implementation modular so it can be mapped to FPGA control blocks
later.

The original Relay implementation is not modified. Instead, this module acts
as a higher-level orchestration layer on top of the existing Relay decoder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from threading import Thread
from time import perf_counter
from typing import Sequence

import numpy as np

import sys


CURRENT_DIR = Path(__file__).resolve().parent
SEQUENTIAL_DIR = CURRENT_DIR.parent / "sequential_relay"
for search_path in (CURRENT_DIR, SEQUENTIAL_DIR):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from relay_bp_decoder import (  # type: ignore  # noqa: E402
    RelayBPDecoder,
    RelayDecodeResult,
    RelayDecoderConfig,
    RelayLegConfig,
    build_example_matrix,
)
from binary_bp_framework import ParityCheckMatrix  # type: ignore  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration and results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParallelRelayLaneConfig:
    """Configuration for one Relay lane in the parallel architecture.

    Each lane owns its own Relay configuration and seed. The gamma schedule is
    stored inside the Relay leg configurations so that each lane can follow a
    distinct trajectory even though all lanes receive the same syndrome.
    """

    label: str
    relay_config: RelayDecoderConfig
    seed: int = 0


@dataclass(frozen=True)
class ParallelRelayLaneResult:
    """Metrics collected for one Relay decoder lane."""

    lane_index: int
    label: str
    converged: bool
    relay_legs: int
    total_iterations: int
    convergence_time_seconds: float
    total_latency_seconds: float
    gamma_schedule_used: list[list[float]]
    final_syndrome: np.ndarray
    decoded_error: np.ndarray
    relay_result: RelayDecodeResult


@dataclass(frozen=True)
class ParallelRelayDecodeResult:
    """Summary of one parallel Relay-BP decode attempt."""

    converged: bool
    winning_lane: int | None
    winning_label: str | None
    convergence_time_seconds: float | None
    total_latency_seconds: float
    winning_gamma_schedule: list[list[float]] | None
    lane_results: list[ParallelRelayLaneResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parallel Relay decoder
# ---------------------------------------------------------------------------


class ParallelRelayDecoder:
    """Parallel Relay-BP architecture implemented with Python threads.

    The class instantiates one Relay decoder per lane. Every lane receives the
    same syndrome and prior belief vector, but each lane may use a different
    gamma schedule. The workers execute concurrently, and the coordinator
    records the first successful decode while still collecting all lane-level
    outcomes.
    """

    def __init__(self, parity_check_matrix: ParityCheckMatrix, lane_configs: Sequence[ParallelRelayLaneConfig]):
        """Store the code structure and the lane-specific Relay configurations."""
        if not lane_configs:
            raise ValueError("lane_configs must contain at least one lane")

        self.matrix = parity_check_matrix
        self.lane_configs = list(lane_configs)

    def _build_lane_decoders(self) -> list[RelayBPDecoder]:
        """Instantiate a fresh Relay decoder for each lane.

        Creating fresh decoders per decode call keeps the implementation
        stateless across runs and avoids accidental cross-lane state sharing.
        """
        decoders: list[RelayBPDecoder] = []
        for lane_config in self.lane_configs:
            decoder = RelayBPDecoder(
                self.matrix,
                lane_config.relay_config,
                seed=lane_config.seed,
            )
            decoders.append(decoder)
        return decoders

    def _lane_gamma_schedule(self, lane_config: ParallelRelayLaneConfig) -> list[list[float]]:
        """Extract the gamma schedule used by one lane for reporting."""
        return [list(leg_config.gamma_schedule) for leg_config in lane_config.relay_config.leg_configs]

    def _run_lane(
        self,
        lane_index: int,
        lane_config: ParallelRelayLaneConfig,
        decoder: RelayBPDecoder,
        prior_llr: np.ndarray,
        syndrome: np.ndarray,
        results_queue: Queue[ParallelRelayLaneResult],
        start_time: float,
    ) -> None:
        """Worker routine executed by a thread for one Relay lane.

        The worker runs the underlying Relay decoder and records both the
        decoder's own latency and the wall-clock time observed by the parallel
        coordinator. The same syndrome and prior state are provided to every
        lane so the only behavioral difference is the lane-specific gamma
        schedule and decoder seed.
        """
        relay_result = decoder.decode(prior_llr.copy(), syndrome.copy())
        observed_latency = perf_counter() - start_time
        results_queue.put(
            ParallelRelayLaneResult(
                lane_index=lane_index,
                label=lane_config.label,
                converged=relay_result.converged,
                relay_legs=relay_result.relay_legs,
                total_iterations=relay_result.total_iterations,
                convergence_time_seconds=relay_result.latency_seconds,
                total_latency_seconds=observed_latency,
                gamma_schedule_used=self._lane_gamma_schedule(lane_config),
                final_syndrome=relay_result.final_syndrome,
                decoded_error=relay_result.decoded_error,
                relay_result=relay_result,
            )
        )

    def decode(self, prior_llr: np.ndarray, syndrome: np.ndarray) -> ParallelRelayDecodeResult:
        """Run all Relay lanes concurrently and return the first successful result."""
        if syndrome.shape != (self.matrix.n_checks,):
            raise ValueError(f"syndrome must have shape {(self.matrix.n_checks,)}, got {syndrome.shape}")
        if prior_llr.shape != (self.matrix.n_variables,):
            raise ValueError(f"prior_llr must have shape {(self.matrix.n_variables,)}, got {prior_llr.shape}")

        start_time = perf_counter()
        results_queue: Queue[ParallelRelayLaneResult] = Queue()
        decoders = self._build_lane_decoders()

        threads: list[Thread] = []
        for lane_index, (lane_config, decoder) in enumerate(zip(self.lane_configs, decoders)):
            thread = Thread(
                target=self._run_lane,
                kwargs={
                    "lane_index": lane_index,
                    "lane_config": lane_config,
                    "decoder": decoder,
                    "prior_llr": prior_llr,
                    "syndrome": syndrome,
                    "results_queue": results_queue,
                    "start_time": start_time,
                },
                daemon=True,
                name=f"RelayLane-{lane_index}",
            )
            thread.start()
            threads.append(thread)

        collected_results: list[ParallelRelayLaneResult | None] = [None] * len(threads)
        winning_result: ParallelRelayLaneResult | None = None
        first_success_time: float | None = None

        # Collect every lane result so the caller can inspect the full ensemble,
        # but remember the first successful result as soon as it appears.
        for _ in range(len(threads)):
            lane_result = results_queue.get()
            collected_results[lane_result.lane_index] = lane_result
            if lane_result.converged and winning_result is None:
                winning_result = lane_result
                first_success_time = perf_counter() - start_time

        # Ensure all worker threads have finished before returning. This keeps
        # the framework clean for repeated experimentation and simplifies test
        # usage even though the winning result is already known.
        for thread in threads:
            thread.join()

        finalized_results = [result for result in collected_results if result is not None]
        total_latency_seconds = perf_counter() - start_time
        converged = winning_result is not None

        return ParallelRelayDecodeResult(
            converged=converged,
            winning_lane=winning_result.lane_index if winning_result else None,
            winning_label=winning_result.label if winning_result else None,
            convergence_time_seconds=first_success_time,
            total_latency_seconds=total_latency_seconds,
            winning_gamma_schedule=winning_result.gamma_schedule_used if winning_result else None,
            lane_results=finalized_results,
        )


# ---------------------------------------------------------------------------
# Demonstration helper
# ---------------------------------------------------------------------------


def build_example_parallel_decoder() -> ParallelRelayDecoder:
    """Construct a small parallel Relay decoder for demonstration runs."""
    matrix = build_example_matrix()

    lane_configs = [
        ParallelRelayLaneConfig(
            label="lane-0",
            seed=11,
            relay_config=RelayDecoderConfig(
                leg_configs=[
                    RelayLegConfig(gamma_schedule=[0.05, 0.10, 0.15, 0.20], carry_gamma=0.40),
                    RelayLegConfig(gamma_schedule=[0.15, 0.20, 0.25, 0.30], carry_gamma=0.45),
                ],
                max_iterations_per_leg=12,
                damping=0.05,
            ),
        ),
        ParallelRelayLaneConfig(
            label="lane-1",
            seed=22,
            relay_config=RelayDecoderConfig(
                leg_configs=[
                    RelayLegConfig(gamma_schedule=[0.10, 0.20, 0.30, 0.35], carry_gamma=0.50),
                    RelayLegConfig(gamma_schedule=[0.20, 0.30, 0.40, 0.45], carry_gamma=0.55),
                ],
                max_iterations_per_leg=12,
                damping=0.05,
            ),
        ),
        ParallelRelayLaneConfig(
            label="lane-2",
            seed=33,
            relay_config=RelayDecoderConfig(
                leg_configs=[
                    RelayLegConfig(gamma_schedule=[0.20, 0.25, 0.30, 0.35], carry_gamma=0.60),
                    RelayLegConfig(gamma_schedule=[0.30, 0.35, 0.40, 0.45], carry_gamma=0.65),
                ],
                max_iterations_per_leg=12,
                damping=0.05,
            ),
        ),
    ]

    return ParallelRelayDecoder(matrix, lane_configs)


def main() -> None:
    """Run a small end-to-end demonstration of the parallel Relay architecture."""
    decoder = build_example_parallel_decoder()
    prior_llr = np.array([1.2, -0.8, 0.7, 1.1, -1.0, 0.6], dtype=float)
    syndrome = decoder.matrix.syndrome(np.array([0, 1, 0, 0, 1, 0], dtype=np.uint8))
    result = decoder.decode(prior_llr, syndrome)

    print("Parallel Relay-BP decode result")
    print("-" * 40)
    print(f"Converged:             {result.converged}")
    print(f"Winning lane:          {result.winning_lane}")
    print(f"Winning label:         {result.winning_label}")
    print(f"Convergence time:      {None if result.convergence_time_seconds is None else f'{result.convergence_time_seconds * 1e3:.3f} ms'}")
    print(f"Total latency:         {result.total_latency_seconds * 1e3:.3f} ms")
    print(f"Winning gamma schedule: {result.winning_gamma_schedule}")

    for lane_result in result.lane_results:
        print(
            f"  {lane_result.label}: converged={lane_result.converged} "
            f"relay_legs={lane_result.relay_legs} "
            f"convergence_time={lane_result.convergence_time_seconds * 1e3:.3f} ms "
            f"gamma={lane_result.gamma_schedule_used}"
        )


if __name__ == "__main__":
    main()
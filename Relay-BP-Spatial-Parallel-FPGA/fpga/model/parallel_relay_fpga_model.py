"""
Top-level FPGA model for the Parallel Relay-BP architecture.

The model wires together a syndrome dispatcher, multiple Relay engines, a
convergence monitor per lane, a first-success selector, and an output buffer.
It advances the whole design one cycle at a time so the behavior mirrors the
structure of a hardware pipeline rather than a mathematical decoder.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Sequence

import numpy as np


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from convergence_monitor import ConvergenceMonitor
from first_success_selector import FirstSuccessSelector
from fpga_types import ArchitectureResult, RelayFrame, RelayLaneConfig, RelayLegSchedule
from output_buffer import OutputBuffer
from relay_engine import RelayEngine
from syndrome_dispatcher import SyndromeDispatcher


@dataclass(frozen=True)
class ParallelRelayFPGAConfig:
    """Configuration for the top-level FPGA model."""

    lane_configs: tuple[RelayLaneConfig, ...]
    max_cycles: int = 256


class ParallelRelayFPGAModel:
    """Hardware-oriented model of the Parallel Relay-BP FPGA decoder."""

    def __init__(self, config: ParallelRelayFPGAConfig):
        """Instantiate the dispatcher, lane engines, monitors, selector, and output buffer."""
        if not config.lane_configs:
            raise ValueError("lane_configs must contain at least one lane")

        self.config = config
        self.dispatcher = SyndromeDispatcher()
        self.engines = [RelayEngine(lane_index=index, config=lane_config) for index, lane_config in enumerate(config.lane_configs)]
        self.monitors = [ConvergenceMonitor() for _ in self.engines]
        self.selector = FirstSuccessSelector(lane_priority=list(range(len(self.engines))))
        self.output_buffer = OutputBuffer()
        self._current_frame: RelayFrame | None = None

    def load_frame(self, syndrome: np.ndarray, prior_llr: np.ndarray, metadata: dict | None = None, frame_id: int = 0) -> None:
        """Load a new frame into the dispatcher and distribute it to all lanes."""
        frame = RelayFrame(
            frame_id=frame_id,
            syndrome=np.array(syndrome, copy=True),
            prior_llr=np.array(prior_llr, copy=True),
            metadata=dict(metadata or {}),
        )
        self._current_frame = frame
        self.dispatcher.load_frame(frame)

        distributed_frames = self.dispatcher.dispatch(len(self.engines))
        for engine, lane_frame in zip(self.engines, distributed_frames):
            engine.load_frame(lane_frame)

        self.output_buffer.clear()

    def step(self, cycle: int) -> list[object]:
        """Advance every engine by one cycle and collect monitor snapshots."""
        snapshots: list[object] = []
        for engine, monitor in zip(self.engines, self.monitors):
            engine.tick()
            snapshots.append(monitor.observe(engine, cycle))
        return snapshots

    def run(self, syndrome: np.ndarray, prior_llr: np.ndarray, metadata: dict | None = None, frame_id: int = 0, max_cycles: int | None = None) -> ArchitectureResult:
        """Run the full FPGA model until the first lane converges or the cycle budget expires."""
        self.load_frame(syndrome=syndrome, prior_llr=prior_llr, metadata=metadata, frame_id=frame_id)

        cycle_budget = max_cycles if max_cycles is not None else self.config.max_cycles
        all_snapshots = []
        winner: RelayEngineResult | None = None
        convergence_cycle: int | None = None

        for cycle in range(cycle_budget):
            cycle_snapshots = self.step(cycle)
            all_snapshots.extend(cycle_snapshots)

            candidates = [engine.finalize_if_needed() for engine in self.engines if engine.current_result() is not None and engine.current_result().converged]
            winner = self.selector.select(candidates)
            if winner is not None:
                convergence_cycle = winner.convergence_cycle
                self.output_buffer.write(
                    winner,
                    metadata={
                        "selected_by": "FirstSuccessSelector",
                        "frame_id": frame_id,
                        "cycle": cycle,
                    },
                )
                break

            if all(engine.is_done for engine in self.engines):
                break

        lane_results = [engine.finalize_if_needed() for engine in self.engines]
        total_latency_seconds = len(all_snapshots) // len(self.engines) * (self.engines[0].config.cycle_time_seconds if self.engines else 0.0)
        selected_vector = winner.candidate_vector if winner is not None else None

        return ArchitectureResult(
            frame_id=frame_id,
            converged=winner is not None,
            winning_lane=winner.lane_index if winner is not None else None,
            winning_label=winner.label if winner is not None else None,
            winning_cycle=convergence_cycle,
            convergence_time_seconds=(convergence_cycle * self.engines[0].config.cycle_time_seconds) if convergence_cycle is not None and self.engines else None,
            total_latency_seconds=total_latency_seconds,
            selected_candidate_vector=selected_vector,
            lane_results=lane_results,
            monitor_snapshots=all_snapshots,
            output_buffer_snapshot=self.output_buffer.snapshot(),
        )


def _build_lane_configs() -> tuple[RelayLaneConfig, ...]:
    """Build a small set of lane configs for demonstration purposes."""
    return (
        RelayLaneConfig(
            label="lane-0",
            lane_seed=11,
            lane_bias=0,
            max_cycles_per_leg=8,
            cycle_time_seconds=1e-6,
            leg_schedules=(
                RelayLegSchedule(gamma_schedule=(0.05, 0.10, 0.15, 0.20), carry_factor=0.40),
                RelayLegSchedule(gamma_schedule=(0.15, 0.20, 0.25, 0.30), carry_factor=0.45),
            ),
        ),
        RelayLaneConfig(
            label="lane-1",
            lane_seed=22,
            lane_bias=1,
            max_cycles_per_leg=8,
            cycle_time_seconds=1e-6,
            leg_schedules=(
                RelayLegSchedule(gamma_schedule=(0.10, 0.20, 0.30, 0.35), carry_factor=0.50),
                RelayLegSchedule(gamma_schedule=(0.20, 0.30, 0.40, 0.45), carry_factor=0.55),
            ),
        ),
        RelayLaneConfig(
            label="lane-2",
            lane_seed=33,
            lane_bias=2,
            max_cycles_per_leg=8,
            cycle_time_seconds=1e-6,
            leg_schedules=(
                RelayLegSchedule(gamma_schedule=(0.20, 0.25, 0.30, 0.35), carry_factor=0.60),
                RelayLegSchedule(gamma_schedule=(0.30, 0.35, 0.40, 0.45), carry_factor=0.65),
            ),
        ),
        RelayLaneConfig(
            label="lane-3",
            lane_seed=44,
            lane_bias=0,
            max_cycles_per_leg=8,
            cycle_time_seconds=1e-6,
            leg_schedules=(
                RelayLegSchedule(gamma_schedule=(0.25, 0.30, 0.35, 0.40), carry_factor=0.60),
                RelayLegSchedule(gamma_schedule=(0.35, 0.40, 0.45, 0.50), carry_factor=0.70),
            ),
        ),
    )


def main() -> None:
    """Run a small FPGA-model demonstration from the command line."""
    lane_configs = _build_lane_configs()
    model = ParallelRelayFPGAModel(ParallelRelayFPGAConfig(lane_configs=lane_configs, max_cycles=64))
    syndrome = np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype=np.uint8)
    prior_llr = np.array([1.2, -0.8, 0.7, 1.1, -1.0, 0.6, 0.4, -0.2], dtype=float)

    result = model.run(syndrome=syndrome, prior_llr=prior_llr, metadata={"demo": True}, frame_id=1)

    print("Parallel Relay FPGA model result")
    print("-" * 40)
    print(f"Converged:            {result.converged}")
    print(f"Winning lane:         {result.winning_lane}")
    print(f"Winning label:        {result.winning_label}")
    print(f"Winning cycle:        {result.winning_cycle}")
    print(f"Convergence time:     {None if result.convergence_time_seconds is None else f'{result.convergence_time_seconds * 1e3:.3f} ms'}")
    print(f"Total latency:        {result.total_latency_seconds * 1e3:.3f} ms")
    print(f"Selected vector size:  {0 if result.selected_candidate_vector is None else result.selected_candidate_vector.size}")
    print(f"Output buffer valid:   {result.output_buffer_snapshot.get('valid')}")

    for lane_result in result.lane_results:
        print(
            f"  {lane_result.label}: converged={lane_result.converged} "
            f"done_cycle={lane_result.done_cycle} "
            f"latency={lane_result.latency_seconds * 1e3:.3f} ms "
            f"legs={lane_result.leg_count}"
        )


if __name__ == "__main__":
    main()

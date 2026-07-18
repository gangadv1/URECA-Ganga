"""
Relay engine model.

The Relay engine is modeled as a lane-local finite-state machine with private
BRAM, leg sequencing, gamma-scheduled activity, and convergence tracking.
This is intentionally hardware-oriented: it advances cycle by cycle and keeps
its mutable state in the BRAM model instead of recomputing values from a full
decoder algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from convergence_monitor import ConvergenceMonitor
from fpga_types import RelayEngineResult, RelayFrame, RelayLaneConfig, RelayLegSchedule
from local_bram import LocalBRAM


@dataclass
class RelayEngineState:
    """Mutable runtime state of one Relay lane."""

    active: bool = False
    done: bool = False
    converged: bool = False
    frame_id: int = -1
    cycle: int = 0
    current_leg_index: int = 0
    cycle_in_leg: int = 0
    residual_score: int = 0
    soft_state: float = 0.0
    convergence_cycle: int | None = None
    reason: str = "IDLE"
    candidate_vector: np.ndarray | None = None
    result: RelayEngineResult | None = None


class RelayEngine:
    """Hardware-oriented Relay lane model with sequential legs."""

    def __init__(self, lane_index: int, config: RelayLaneConfig) -> None:
        """Create a Relay lane with a lane-local BRAM bank."""
        self.lane_index = lane_index
        self.config = config
        self.label = config.label
        self.local_bram = LocalBRAM()
        self.monitor = ConvergenceMonitor()
        self.state = RelayEngineState()

    def load_frame(self, frame: RelayFrame) -> None:
        """Latch a new frame and initialize lane-local registers."""
        self.local_bram.reset()
        syndrome = np.array(frame.syndrome, copy=True)
        prior_llr = np.array(frame.prior_llr, copy=True)
        syndrome_weight = int(np.sum(syndrome))

        base_residual = syndrome_weight + max(1, prior_llr.size // 4) + self.config.lane_bias
        candidate_vector = np.zeros(prior_llr.size, dtype=np.uint8)

        self.local_bram.write_register("frame_id", frame.frame_id)
        self.local_bram.write_register("syndrome_weight", syndrome_weight)
        self.local_bram.write_register("current_gamma", 0.0)
        self.local_bram.write_register("residual_score", base_residual)
        self.local_bram.write_register("soft_state", 0.0)
        self.local_bram.write_register("cycle", 0)
        self.local_bram.write_register("cycle_in_leg", 0)
        self.local_bram.write_register("current_leg_index", 0)
        self.local_bram.write_vector("syndrome", syndrome)
        self.local_bram.write_vector("prior_llr", prior_llr)
        self.local_bram.write_vector("candidate_vector", candidate_vector)

        self.state = RelayEngineState(
            active=True,
            done=False,
            converged=False,
            frame_id=frame.frame_id,
            cycle=0,
            current_leg_index=0,
            cycle_in_leg=0,
            residual_score=base_residual,
            soft_state=float(base_residual),
            convergence_cycle=None,
            reason="RUNNING",
            candidate_vector=np.array(candidate_vector, copy=True),
            result=None,
        )

    def _current_leg(self) -> RelayLegSchedule | None:
        """Return the leg currently being executed, if any."""
        if self.state.current_leg_index >= len(self.config.leg_schedules):
            return None
        return self.config.leg_schedules[self.state.current_leg_index]

    def _advance_leg(self) -> None:
        """Advance to the next Relay leg while carrying forward soft state."""
        current_leg = self._current_leg()
        if current_leg is None:
            self.state.done = True
            self.state.active = False
            self.state.reason = "EXHAUSTED_LEGS"
            return

        carried_state = float(self.local_bram.read_register("soft_state", 0.0))
        updated_soft_state = current_leg.carry_factor * carried_state + float(self.state.residual_score)

        self.state.current_leg_index += 1
        self.state.cycle_in_leg = 0
        self.state.soft_state = updated_soft_state
        self.local_bram.write_register("soft_state", updated_soft_state)
        self.local_bram.write_register("current_leg_index", self.state.current_leg_index)
        self.local_bram.write_register("cycle_in_leg", self.state.cycle_in_leg)
        self.local_bram.write_register("current_gamma", 0.0)

        if self.state.current_leg_index >= len(self.config.leg_schedules):
            self.state.done = True
            self.state.active = False
            self.state.reason = "EXHAUSTED_LEGS"

    def _update_candidate_vector(self, gamma: float) -> None:
        """Toggle a small portion of the candidate vector to mimic hardware activity."""
        candidate = self.local_bram.read_vector("candidate_vector")
        if candidate is None:
            return

        index = (self.state.cycle + self.config.lane_seed + self.state.current_leg_index) % candidate.size
        toggle_value = np.uint8((candidate[index] + int(round(gamma * 10.0)) + self.config.lane_bias + 1) % 2)
        candidate[index] = toggle_value
        self.local_bram.write_vector("candidate_vector", candidate)
        self.state.candidate_vector = np.array(candidate, copy=True)

    def tick(self) -> None:
        """Advance the lane by one hardware cycle."""
        if not self.state.active or self.state.done:
            return

        current_leg = self._current_leg()
        if current_leg is None:
            self.state.done = True
            self.state.active = False
            self.state.reason = "NO_LEG_AVAILABLE"
            return

        gamma_schedule = current_leg.gamma_schedule
        gamma = float(gamma_schedule[min(self.state.cycle_in_leg, len(gamma_schedule) - 1)]) if gamma_schedule else 0.0

        residual_score = int(self.local_bram.read_register("residual_score", self.state.residual_score))
        soft_state = float(self.local_bram.read_register("soft_state", self.state.soft_state))

        # Hardware-style state update: higher gamma increases the progress per
        # cycle, while the lane bias and carried soft state modulate the pace.
        progress_step = 1 + int(round(gamma * 6.0)) + max(0, self.config.lane_bias)
        residual_score = max(0, residual_score - progress_step)
        soft_state = 0.7 * soft_state + gamma + float(progress_step)

        self._update_candidate_vector(gamma)

        self.state.cycle += 1
        self.state.cycle_in_leg += 1
        self.state.residual_score = residual_score
        self.state.soft_state = soft_state

        self.local_bram.write_register("cycle", self.state.cycle)
        self.local_bram.write_register("cycle_in_leg", self.state.cycle_in_leg)
        self.local_bram.write_register("residual_score", residual_score)
        self.local_bram.write_register("soft_state", soft_state)
        self.local_bram.write_register("current_gamma", gamma)
        self.local_bram.write_register("current_leg_index", self.state.current_leg_index)

        if residual_score == 0:
            self.state.done = True
            self.state.converged = True
            self.state.active = False
            self.state.convergence_cycle = self.state.cycle
            self.state.reason = "CONVERGED"
            self.state.result = self._build_result(gamma_schedule_used=self._collect_gamma_history())
            return

        if self.state.cycle_in_leg >= self.config.max_cycles_per_leg:
            self._advance_leg()
            if self.state.done and not self.state.converged:
                self.state.result = self._build_result(gamma_schedule_used=self._collect_gamma_history(), reason_override=self.state.reason)

    def _collect_gamma_history(self) -> list[list[float]]:
        """Collect the gamma schedules used by this lane for reporting."""
        return [list(leg.gamma_schedule) for leg in self.config.leg_schedules]

    def _build_result(self, gamma_schedule_used: list[list[float]], reason_override: str | None = None) -> RelayEngineResult:
        """Create the final immutable result object for the lane."""
        candidate = self.local_bram.read_vector("candidate_vector")
        if candidate is None:
            candidate = np.array([], dtype=np.uint8)

        done_cycle = self.state.cycle
        latency_seconds = done_cycle * self.config.cycle_time_seconds

        return RelayEngineResult(
            frame_id=self.state.frame_id,
            lane_index=self.lane_index,
            label=self.label,
            converged=self.state.converged,
            done_cycle=done_cycle,
            leg_count=self.state.current_leg_index + (1 if self.state.converged else 0),
            convergence_cycle=self.state.convergence_cycle,
            latency_seconds=latency_seconds,
            gamma_schedule_used=gamma_schedule_used,
            residual_score=self.state.residual_score,
            candidate_vector=np.array(candidate, copy=True),
            reason=reason_override or self.state.reason,
        )

    def current_result(self) -> RelayEngineResult | None:
        """Return the latched result if the lane has finished."""
        return self.state.result

    @property
    def is_done(self) -> bool:
        """Indicate whether the lane has halted."""
        return self.state.done

    @property
    def is_converged(self) -> bool:
        """Indicate whether the lane completed successfully."""
        return self.state.converged

    @property
    def current_leg_index(self) -> int:
        """Expose the current leg index for monitoring."""
        return self.state.current_leg_index

    def finalize_if_needed(self) -> RelayEngineResult:
        """Return the final result, building it on demand if necessary."""
        if self.state.result is None:
            self.state.result = self._build_result(gamma_schedule_used=self._collect_gamma_history())
        return self.state.result


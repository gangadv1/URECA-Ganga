"""
Convergence monitor model.

The monitor reads the visible state of each Relay engine and determines when
the lane has converged or stopped. This mirrors a hardware comparator and
status register rather than a mathematical decoder check.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fpga_types import MonitorSnapshot


@dataclass
class ConvergenceMonitorState:
    """History and latest state observed by the monitor."""

    snapshots: list[MonitorSnapshot] = field(default_factory=list)
    last_snapshot: MonitorSnapshot | None = None


class ConvergenceMonitor:
    """Track whether a Relay engine has finished successfully."""

    def __init__(self, residual_threshold: int = 0) -> None:
        """Create a monitor with a configurable residual threshold."""
        self.residual_threshold = residual_threshold
        self.state = ConvergenceMonitorState()

    def observe(self, engine: "RelayEngine", cycle: int) -> MonitorSnapshot:
        """Sample the engine and record the current completion status."""
        residual_score = int(engine.local_bram.read_register("residual_score", 0))
        current_gamma = float(engine.local_bram.read_register("current_gamma", 0.0))
        converged = bool(engine.is_converged)
        done = bool(engine.is_done)

        if done and converged:
            status = "CONVERGED"
        elif done:
            status = "DONE"
        elif residual_score <= self.residual_threshold:
            status = "READY"
        else:
            status = "RUNNING"

        snapshot = MonitorSnapshot(
            lane_index=engine.lane_index,
            label=engine.label,
            cycle=cycle,
            leg_index=engine.current_leg_index,
            residual_score=residual_score,
            converged=converged,
            done=done,
            current_gamma=current_gamma,
            status=status,
        )
        self.state.last_snapshot = snapshot
        self.state.snapshots.append(snapshot)
        return snapshot


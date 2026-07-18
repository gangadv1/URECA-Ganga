"""
First-success selector model.

The selector acts like a small hardware arbiter. It examines the lane results
that have become available and chooses the first successful lane according to
the observed convergence cycle and a deterministic lane priority order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from fpga_types import RelayEngineResult


@dataclass
class SelectorState:
    """Bookkeeping for the selector output and selection history."""

    selected_lane: int | None = None
    selected_cycle: int | None = None
    history: list[RelayEngineResult] = field(default_factory=list)


class FirstSuccessSelector:
    """Choose the first converged Relay engine result."""

    def __init__(self, lane_priority: Sequence[int] | None = None) -> None:
        """Initialize the selector with an optional fixed lane priority."""
        self.lane_priority = list(lane_priority) if lane_priority is not None else []
        self.state = SelectorState()

    def select(self, candidates: Sequence[RelayEngineResult]) -> RelayEngineResult | None:
        """Return the first converged result, using deterministic tie-breaking."""
        converged = [candidate for candidate in candidates if candidate.converged]
        if not converged:
            return None

        def priority_key(result: RelayEngineResult) -> tuple[int, int, int]:
            if self.lane_priority and result.lane_index in self.lane_priority:
                priority = self.lane_priority.index(result.lane_index)
            else:
                priority = result.lane_index
            convergence_cycle = result.convergence_cycle if result.convergence_cycle is not None else result.done_cycle
            return (convergence_cycle, priority, result.lane_index)

        winner = min(converged, key=priority_key)
        self.state.selected_lane = winner.lane_index
        self.state.selected_cycle = winner.convergence_cycle
        self.state.history.append(winner)
        return winner


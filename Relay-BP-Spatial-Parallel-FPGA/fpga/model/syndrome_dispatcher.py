"""
Syndrome dispatcher model.

The dispatcher accepts a single input frame and fans it out to every Relay
lane. It does not decode anything itself; it only aligns and distributes the
inputs so the downstream lanes can operate in parallel.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fpga_types import RelayFrame


@dataclass
class SyndromeDispatcherState:
    """Bookkeeping state for the dispatcher."""

    frame_id: int | None = None
    fanout_count: int = 0


class SyndromeDispatcher:
    """Broadcast a single syndrome frame to all Relay lanes."""

    def __init__(self) -> None:
        """Initialize the dispatcher state."""
        self.state = SyndromeDispatcherState()
        self.last_frame: RelayFrame | None = None

    def load_frame(self, frame: RelayFrame) -> None:
        """Latch the incoming frame at the dispatcher input."""
        self.last_frame = RelayFrame(
            frame_id=frame.frame_id,
            syndrome=np.array(frame.syndrome, copy=True),
            prior_llr=np.array(frame.prior_llr, copy=True),
            metadata=dict(frame.metadata),
        )
        self.state.frame_id = frame.frame_id

    def dispatch(self, lane_count: int) -> list[RelayFrame]:
        """Fan out the latched frame to the requested number of lanes."""
        if self.last_frame is None:
            raise RuntimeError("No frame is loaded into the dispatcher")

        self.state.fanout_count += 1
        return [
            RelayFrame(
                frame_id=self.last_frame.frame_id,
                syndrome=np.array(self.last_frame.syndrome, copy=True),
                prior_llr=np.array(self.last_frame.prior_llr, copy=True),
                metadata=dict(self.last_frame.metadata),
            )
            for _ in range(lane_count)
        ]

"""
Output buffer model.

The output buffer stores the selected Relay result before it is released to
the host or to downstream FPGA logic. This mimics a small handoff register or
FIFO stage at the end of the architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fpga_types import RelayEngineResult


@dataclass
class OutputBufferState:
    """Internal state of the output buffer."""

    valid: bool = False
    packet: RelayEngineResult | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class OutputBuffer:
    """Capture and expose the selected decoder output."""

    def __init__(self) -> None:
        """Initialize an empty output buffer."""
        self.state = OutputBufferState()

    def write(self, packet: RelayEngineResult, metadata: dict[str, Any] | None = None) -> None:
        """Latch a selected Relay result into the buffer."""
        self.state.valid = True
        self.state.packet = packet
        self.state.metadata = dict(metadata or {})

    def read(self) -> RelayEngineResult | None:
        """Read the currently latched packet without clearing the buffer."""
        return self.state.packet

    def clear(self) -> None:
        """Clear the buffer as if the downstream consumer had accepted the data."""
        self.state.valid = False
        self.state.packet = None
        self.state.metadata.clear()

    @property
    def valid(self) -> bool:
        """Indicate whether the buffer currently contains valid output."""
        return self.state.valid

    def snapshot(self) -> dict[str, Any]:
        """Return a debug snapshot of the buffer contents."""
        return {
            "valid": self.state.valid,
            "packet": self.state.packet,
            "metadata": dict(self.state.metadata),
        }


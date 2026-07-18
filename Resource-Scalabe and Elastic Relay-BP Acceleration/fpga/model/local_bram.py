"""
Local BRAM model used by each Relay engine lane.

The class mimics a small private memory block with simple scalar registers and
named vector banks. It is deliberately low-level so the RelayEngine can use it
as a stand-in for on-chip storage instead of recomputing values each cycle.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np


class LocalBRAM:
    """Simple banked memory model for lane-private FPGA state."""

    def __init__(self) -> None:
        """Initialize empty register and vector banks."""
        self._registers: dict[str, Any] = {}
        self._vectors: dict[str, np.ndarray] = {}

    def reset(self) -> None:
        """Clear all stored registers and vector banks."""
        self._registers.clear()
        self._vectors.clear()

    def write_register(self, name: str, value: Any) -> None:
        """Write a scalar or lightweight control register."""
        self._registers[name] = value

    def read_register(self, name: str, default: Any | None = None) -> Any:
        """Read a scalar register value."""
        return self._registers.get(name, default)

    def write_vector(self, name: str, value: np.ndarray) -> None:
        """Write a vector into the memory bank using a private copy."""
        self._vectors[name] = np.array(value, copy=True)

    def read_vector(self, name: str, default: np.ndarray | None = None) -> np.ndarray | None:
        """Read a vector from the memory bank using a private copy."""
        if name not in self._vectors:
            if default is None:
                return None
            return np.array(default, copy=True)
        return np.array(self._vectors[name], copy=True)

    def has_vector(self, name: str) -> bool:
        """Check whether a vector bank is present."""
        return name in self._vectors

    def snapshot(self) -> dict[str, Any]:
        """Return a deep snapshot of the current BRAM contents."""
        return {
            "registers": deepcopy(self._registers),
            "vectors": {name: np.array(vector, copy=True) for name, vector in self._vectors.items()},
        }

"""Parallel lane Relay-BP model mirror.

This module exposes the threaded Parallel Relay decoder and the FPGA-oriented
parallel architecture model through the relay_models namespace.
"""

from __future__ import annotations

from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
SIM_DIR = CURRENT_DIR.parent.parent / "simulations" / "parallel_relay"
FPGA_MODEL_DIR = CURRENT_DIR.parent.parent / "fpga" / "model"
for search_path in (CURRENT_DIR, SIM_DIR, FPGA_MODEL_DIR):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from parallel_relay_decoder import (  # type: ignore  # noqa: E402,F401
    ParallelRelayDecodeResult,
    ParallelRelayDecoder,
    ParallelRelayLaneConfig,
    ParallelRelayLaneResult,
)
from parallel_relay_fpga_model import (  # type: ignore  # noqa: E402,F401
    ParallelRelayFPGAConfig,
    ParallelRelayFPGAModel,
)

__all__ = [
    "ParallelRelayDecodeResult",
    "ParallelRelayDecoder",
    "ParallelRelayLaneConfig",
    "ParallelRelayLaneResult",
    "ParallelRelayFPGAConfig",
    "ParallelRelayFPGAModel",
]

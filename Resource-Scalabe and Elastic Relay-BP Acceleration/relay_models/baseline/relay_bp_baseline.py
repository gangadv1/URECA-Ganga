"""Baseline Relay-BP model mirror.

The actual implementation lives under simulations/sequential_relay. This module
re-exports the public classes so relay_models can be used as a stable import
surface for research notebooks, experiments, and documentation snippets.
"""

from __future__ import annotations

from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
SIM_DIR = CURRENT_DIR.parent.parent / "simulations" / "sequential_relay"
for search_path in (CURRENT_DIR, SIM_DIR):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

from binary_bp_framework import (  # type: ignore  # noqa: E402,F401
    BPConfig,
    BPDecoder,
    CheckNode,
    DecodeResult,
    ParityCheckMatrix,
    VariableNode,
    build_example_matrix,
    generate_syndrome,
)
from relay_bp_decoder import (  # type: ignore  # noqa: E402,F401
    RelayBPDecoder,
    RelayDecodeResult,
    RelayDecoderConfig,
    RelayLegConfig,
    RelayLegResult,
)

__all__ = [
    "BPConfig",
    "BPDecoder",
    "CheckNode",
    "DecodeResult",
    "ParityCheckMatrix",
    "VariableNode",
    "build_example_matrix",
    "generate_syndrome",
    "RelayBPDecoder",
    "RelayDecodeResult",
    "RelayDecoderConfig",
    "RelayLegConfig",
    "RelayLegResult",
]

"""Compatibility wrapper for the floating-point Relay-BP reference."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from relay_reference import FloatRelayBPDecoder as _FloatRelayBPDecoder
from relay_reference import RelayDecodeResult, RelayLegConfig, RelayTraceRecord


@dataclass(frozen=True)
class FloatRelayResult:
    converged: bool
    total_iterations: int
    relay_legs: int
    decoded_error: np.ndarray
    final_syndrome: np.ndarray
    beliefs: np.ndarray
    relay_memory: np.ndarray
    trace: list[RelayTraceRecord] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "converged": self.converged,
            "total_iterations": self.total_iterations,
            "relay_legs": self.relay_legs,
            "decoded_error": self.decoded_error.tolist(),
            "final_syndrome": self.final_syndrome.tolist(),
            "beliefs": self.beliefs.tolist(),
            "relay_memory": self.relay_memory.tolist(),
            "trace": [record.__dict__ for record in self.trace],
            "metadata": self.metadata,
        }


class FloatRelayBPDecoder:
    """Deterministic floating-point Relay-BP reference."""

    def __init__(
        self,
        h_matrix: np.ndarray | Path | str,
        max_iterations: int = 3,
        gamma: float = 0.25,
        leg_configs: Sequence[RelayLegConfig] | None = None,
        trace_messages: bool = False,
    ):
        self._decoder = _FloatRelayBPDecoder(
            h_matrix,
            max_iterations=max_iterations,
            gamma=gamma,
            leg_configs=leg_configs,
            trace_messages=trace_messages,
        )

    @classmethod
    def from_package(
        cls,
        package_path: Path | str,
        *,
        max_iterations: int = 3,
        gamma: float = 0.25,
        leg_configs: Sequence[RelayLegConfig] | None = None,
        trace_messages: bool = False,
    ) -> "FloatRelayBPDecoder":
        return cls(
            package_path,
            max_iterations=max_iterations,
            gamma=gamma,
            leg_configs=leg_configs,
            trace_messages=trace_messages,
        )

    def decode(self, prior: Sequence[float | int], syndrome: Sequence[int], trace_path: Path | None = None) -> FloatRelayResult:
        result = self._decoder.decode(prior, syndrome, trace_path=trace_path)
        return FloatRelayResult(
            converged=result.converged,
            total_iterations=result.total_iterations,
            relay_legs=result.relay_legs,
            decoded_error=result.decoded_error,
            final_syndrome=result.final_syndrome,
            beliefs=result.beliefs,
            relay_memory=result.relay_memory,
            trace=result.trace,
            metadata=result.metadata,
        )

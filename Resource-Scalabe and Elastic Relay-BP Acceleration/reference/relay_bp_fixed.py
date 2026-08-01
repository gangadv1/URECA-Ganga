"""Compatibility wrapper for the fixed-point Relay-BP reference."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from fixedpoint import FixedConfig
from relay_reference import FixedPointRelayBPDecoder as _FixedPointRelayBPDecoder
from relay_reference import RelayLegConfig, RelayTraceRecord


@dataclass(frozen=True)
class FixedRelayLegConfig:
    gamma_schedule: Sequence[float]
    carry_gamma: float = 0.5


@dataclass(frozen=True)
class FixedRelayConfig:
    fixed: FixedConfig = field(default_factory=FixedConfig)
    leg_configs: Sequence[FixedRelayLegConfig] = field(default_factory=lambda: (FixedRelayLegConfig((0.0,), 0.5),))
    max_iterations_per_leg: int = 10
    gamma_scale: int = 16


@dataclass(frozen=True)
class FixedRelayResult:
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


class FixedRelayBPDecoder:
    """Minimal decoder used to generate fixed-point Relay-BP traces."""

    def __init__(self, h_matrix: np.ndarray | Path | str, config: FixedRelayConfig):
        leg_configs = tuple(RelayLegConfig(tuple(leg.gamma_schedule), carry_gamma=float(leg.carry_gamma)) for leg in config.leg_configs)
        self._decoder = _FixedPointRelayBPDecoder(
            h_matrix,
            fixed=config.fixed,
            leg_configs=leg_configs,
            max_iterations_per_leg=config.max_iterations_per_leg,
            gamma_scale=config.gamma_scale,
        )

    def decode(self, prior: Sequence[float | int], syndrome: Sequence[int], trace_path: Path | None = None) -> FixedRelayResult:
        result = self._decoder.decode(prior, syndrome, trace_path=trace_path)
        return FixedRelayResult(
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

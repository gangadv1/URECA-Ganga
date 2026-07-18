"""
Shared FPGA model data types.

These data classes are intentionally lightweight and hardware-oriented. They
represent the packets, configuration records, monitor snapshots, and final
results exchanged by the dispatcher, Relay engines, selector, and output
buffer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np


@dataclass(frozen=True)
class RelayLegSchedule:
    """Per-leg gamma schedule used by one Relay engine lane."""

    gamma_schedule: tuple[float, ...]
    carry_factor: float = 0.5


@dataclass(frozen=True)
class RelayLaneConfig:
    """Hardware configuration for one Relay engine lane."""

    label: str
    leg_schedules: tuple[RelayLegSchedule, ...]
    lane_bias: int = 0
    lane_seed: int = 0
    max_cycles_per_leg: int = 8
    cycle_time_seconds: float = 1e-6


@dataclass(frozen=True)
class RelayFrame:
    """Input frame broadcast by the syndrome dispatcher."""

    frame_id: int
    syndrome: np.ndarray
    prior_llr: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MonitorSnapshot:
    """Snapshot of one engine captured by the convergence monitor."""

    lane_index: int
    label: str
    cycle: int
    leg_index: int
    residual_score: int
    converged: bool
    done: bool
    current_gamma: float
    status: str


@dataclass(frozen=True)
class RelayEngineResult:
    """Final result emitted by one Relay engine lane."""

    frame_id: int
    lane_index: int
    label: str
    converged: bool
    done_cycle: int
    leg_count: int
    convergence_cycle: int | None
    latency_seconds: float
    gamma_schedule_used: list[list[float]]
    residual_score: int
    candidate_vector: np.ndarray
    reason: str


@dataclass(frozen=True)
class ArchitectureResult:
    """Summary emitted by the top-level FPGA model."""

    frame_id: int
    converged: bool
    winning_lane: int | None
    winning_label: str | None
    winning_cycle: int | None
    convergence_time_seconds: float | None
    total_latency_seconds: float
    selected_candidate_vector: np.ndarray | None
    lane_results: list[RelayEngineResult] = field(default_factory=list)
    monitor_snapshots: list[MonitorSnapshot] = field(default_factory=list)
    output_buffer_snapshot: dict[str, Any] = field(default_factory=dict)

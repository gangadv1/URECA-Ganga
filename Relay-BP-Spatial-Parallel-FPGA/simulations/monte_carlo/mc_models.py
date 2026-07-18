"""
Data models and configuration helpers for the Monte Carlo framework.

This module keeps the study configuration and CSV-friendly result structures
separate from the execution logic so the reporting and analysis code can reuse
the same schema without duplicating field definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


def _default_sequential_gamma_schedules() -> tuple[tuple[float, ...], ...]:
    """Return a conservative set of gamma schedules for the sequential Relay run."""
    return (
        (0.05, 0.10, 0.15, 0.20),
        (0.20, 0.25, 0.30, 0.35),
        (0.35, 0.40, 0.45, 0.50),
    )


def _default_sequential_carry_gammas() -> tuple[float, ...]:
    """Return the carry-gamma values paired with the sequential gamma schedules."""
    return (0.40, 0.55, 0.65)


def _default_parallel_lane_gamma_schedules() -> tuple[tuple[tuple[float, ...], ...], ...]:
    """Return lane-specific gamma schedules for the parallel Relay experiment."""
    return (
        (
            (0.05, 0.10, 0.15, 0.20),
            (0.15, 0.20, 0.25, 0.30),
        ),
        (
            (0.10, 0.20, 0.30, 0.35),
            (0.20, 0.30, 0.40, 0.45),
        ),
        (
            (0.20, 0.25, 0.30, 0.35),
            (0.30, 0.35, 0.40, 0.45),
        ),
        (
            (0.30, 0.35, 0.40, 0.45),
            (0.40, 0.45, 0.50, 0.55),
        ),
    )


def _default_parallel_lane_carry_gammas() -> tuple[tuple[float, ...], ...]:
    """Return carry-gamma values for the parallel Relay lanes."""
    return (
        (0.40, 0.45),
        (0.50, 0.55),
        (0.60, 0.65),
        (0.65, 0.70),
    )


def _default_parallel_lane_labels() -> tuple[str, ...]:
    """Return labels used to identify each parallel lane in plots and CSV files."""
    return ("lane-0", "lane-1", "lane-2", "lane-3")


def _default_parallel_lane_seeds() -> tuple[int, ...]:
    """Return deterministic per-lane seeds so repeated studies are reproducible."""
    return (11, 22, 33, 44)


@dataclass(frozen=True)
class MonteCarloConfig:
    """Top-level configuration for the Monte Carlo study.

    The defaults generate thousands of random error patterns, use a fixed
    synthetic parity-check matrix, and save CSV and plot outputs into folders
    beneath the Monte Carlo module directory.
    """

    trial_count: int = 1000
    error_rate: float = 0.13
    llr_magnitude: float = 1.0
    llr_noise_std: float = 1.3
    base_seed: int = 1000
    matrix_seed: int = 1
    matrix_checks: int = 8
    matrix_variables: int = 16
    ones_per_variable: int = 3
    relay_max_iterations_per_leg: int = 15
    relay_damping: float = 0.05
    sequential_gamma_schedules: tuple[tuple[float, ...], ...] = field(default_factory=_default_sequential_gamma_schedules)
    sequential_carry_gammas: tuple[float, ...] = field(default_factory=_default_sequential_carry_gammas)
    parallel_lane_gamma_schedules: tuple[tuple[tuple[float, ...], ...], ...] = field(default_factory=_default_parallel_lane_gamma_schedules)
    parallel_lane_carry_gammas: tuple[tuple[float, ...], ...] = field(default_factory=_default_parallel_lane_carry_gammas)
    parallel_lane_labels: tuple[str, ...] = field(default_factory=_default_parallel_lane_labels)
    parallel_lane_seeds: tuple[int, ...] = field(default_factory=_default_parallel_lane_seeds)
    output_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent)
    csv_dir_name: str = "results"
    plot_dir_name: str = "plots"
    csv_trial_filename: str = "trial_results.csv"
    csv_summary_filename: str = "summary_results.csv"
    plot_dpi: int = 200
    histogram_bins: int = 40

    @property
    def csv_output_dir(self) -> Path:
        """Return the directory where CSV output files should be written."""
        return self.output_dir / self.csv_dir_name

    @property
    def plot_output_dir(self) -> Path:
        """Return the directory where matplotlib plots should be written."""
        return self.output_dir / self.plot_dir_name


@dataclass(frozen=True)
class MonteCarloTrialRecord:
    """CSV-friendly summary of a single sequential-versus-parallel trial."""

    trial_index: int
    error_weight: int
    syndrome_weight: int
    sequential_converged: bool
    sequential_relay_legs: int
    sequential_iterations: int
    sequential_latency_ms: float
    sequential_gamma_schedule: str
    parallel_converged: bool
    parallel_winning_lane: int | None
    parallel_winning_label: str | None
    parallel_relay_legs: int
    parallel_iterations: int
    parallel_convergence_time_ms: float | None
    parallel_total_latency_ms: float
    parallel_effective_latency_ms: float
    parallel_gamma_schedule: str | None
    latency_improvement_percent: float


@dataclass(frozen=True)
class MonteCarloSummary:
    """Aggregate metrics for a Monte Carlo study."""

    trial_count: int
    sequential_average_latency_ms: float
    parallel_average_latency_ms: float
    sequential_worst_latency_ms: float
    parallel_worst_latency_ms: float
    sequential_average_iterations: float
    parallel_average_iterations: float
    sequential_success_rate: float
    parallel_success_rate: float
    average_latency_improvement_percent: float
    parallel_winning_lane_histogram_text: str


@dataclass(frozen=True)
class MonteCarloRunResult:
    """Bundle together the summary statistics and trial-level records."""

    summary: MonteCarloSummary
    trial_records: list[MonteCarloTrialRecord]


def format_gamma_schedule_text(schedules: Sequence[Sequence[float]]) -> str:
    """Render a nested gamma schedule as a CSV-friendly string."""
    parts: list[str] = []
    for schedule in schedules:
        parts.append("[" + ", ".join(f"{value:.3f}" for value in schedule) + "]")
    return " | ".join(parts)


def format_histogram_text(histogram: dict[int, int]) -> str:
    """Render a lane histogram in a compact, human-readable form."""
    if not histogram:
        return "{}"
    return ", ".join(f"lane-{lane}:{count}" for lane, count in sorted(histogram.items()))

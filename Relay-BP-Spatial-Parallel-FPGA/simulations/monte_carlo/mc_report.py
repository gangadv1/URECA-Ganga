"""
CSV and plotting utilities for the Monte Carlo framework.

This module keeps result export separate from the simulation logic so the
study runner can focus on decoding while the reporting layer handles file
generation and matplotlib visualizations.
"""

from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from mc_models import MonteCarloRunResult, MonteCarloSummary, MonteCarloTrialRecord


def save_trial_csv(records: list[MonteCarloTrialRecord], output_path: Path) -> None:
    """Write the per-trial results to a CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(asdict(records[0]).keys()) if records else [])
        if records:
            writer.writeheader()
            for record in records:
                writer.writerow(asdict(record))


def save_summary_csv(summary: MonteCarloSummary, output_path: Path) -> None:
    """Write the aggregate Monte Carlo summary to a CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(asdict(summary).keys()))
        writer.writeheader()
        writer.writerow(asdict(summary))


def plot_latency_distribution(run_result: MonteCarloRunResult, output_dir: Path, dpi: int, bins: int) -> Path:
    """Create a histogram comparing sequential and parallel latencies."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sequential_latencies = np.array([record.sequential_latency_ms for record in run_result.trial_records], dtype=float)
    parallel_latencies = np.array([record.parallel_effective_latency_ms for record in run_result.trial_records], dtype=float)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(sequential_latencies, bins=bins, alpha=0.65, label="Sequential Relay-BP")
    ax.hist(parallel_latencies, bins=bins, alpha=0.65, label="Parallel Relay-BP")
    ax.set_title("Latency Distribution")
    ax.set_xlabel("Latency (ms)")
    ax.set_ylabel("Count")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.tight_layout()

    output_path = output_dir / "latency_distribution.png"
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path


def plot_iteration_distribution(run_result: MonteCarloRunResult, output_dir: Path, dpi: int, bins: int) -> Path:
    """Create a histogram comparing sequential and parallel iteration counts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sequential_iterations = np.array([record.sequential_iterations for record in run_result.trial_records], dtype=float)
    parallel_iterations = np.array([record.parallel_iterations for record in run_result.trial_records], dtype=float)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(sequential_iterations, bins=bins, alpha=0.65, label="Sequential Relay-BP")
    ax.hist(parallel_iterations, bins=bins, alpha=0.65, label="Parallel Relay-BP")
    ax.set_title("Iteration Distribution")
    ax.set_xlabel("Iterations")
    ax.set_ylabel("Count")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.tight_layout()

    output_path = output_dir / "iteration_distribution.png"
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path


def plot_summary_bars(summary: MonteCarloSummary, output_dir: Path, dpi: int) -> Path:
    """Create a bar chart for the key summary metrics."""
    output_dir.mkdir(parents=True, exist_ok=True)

    labels = ["Avg Latency", "Worst Latency", "Avg Iterations", "Success Rate"]
    sequential_values = [
        summary.sequential_average_latency_ms,
        summary.sequential_worst_latency_ms,
        summary.sequential_average_iterations,
        summary.sequential_success_rate * 100.0,
    ]
    parallel_values = [
        summary.parallel_average_latency_ms,
        summary.parallel_worst_latency_ms,
        summary.parallel_average_iterations,
        summary.parallel_success_rate * 100.0,
    ]

    indices = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(indices - width / 2, sequential_values, width=width, label="Sequential")
    ax.bar(indices + width / 2, parallel_values, width=width, label="Parallel")
    ax.set_xticks(indices)
    ax.set_xticklabels(labels, rotation=18, ha="right")
    ax.set_title("Monte Carlo Summary Metrics")
    ax.set_ylabel("Metric Value")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.25)
    fig.tight_layout()

    output_path = output_dir / "summary_metrics.png"
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path


def save_all_outputs(run_result: MonteCarloRunResult, csv_dir: Path, plot_dir: Path, trial_filename: str, summary_filename: str, dpi: int, bins: int) -> dict[str, Path]:
    """Save both CSV files and all plots for one Monte Carlo run."""
    trial_csv_path = csv_dir / trial_filename
    summary_csv_path = csv_dir / summary_filename
    save_trial_csv(run_result.trial_records, trial_csv_path)
    save_summary_csv(run_result.summary, summary_csv_path)

    latency_plot = plot_latency_distribution(run_result, plot_dir, dpi=dpi, bins=bins)
    iteration_plot = plot_iteration_distribution(run_result, plot_dir, dpi=dpi, bins=bins)
    summary_plot = plot_summary_bars(run_result.summary, plot_dir, dpi=dpi)

    return {
        "trial_csv": trial_csv_path,
        "summary_csv": summary_csv_path,
        "latency_plot": latency_plot,
        "iteration_plot": iteration_plot,
        "summary_plot": summary_plot,
    }

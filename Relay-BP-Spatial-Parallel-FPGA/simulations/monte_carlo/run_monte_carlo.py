"""
Command-line entry point for the Monte Carlo Relay-BP comparison.

This script wires together the reusable study, reporting, and configuration
modules so the full workflow can be launched from the command line. The
default configuration generates thousands of random error patterns, runs both
the sequential and parallel Relay decoders, writes CSV outputs, and saves
matplotlib plots.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mc_models import MonteCarloConfig
from mc_report import save_all_outputs
from mc_study import MonteCarloStudy


def _build_config_from_args(args: argparse.Namespace) -> MonteCarloConfig:
    """Construct the Monte Carlo configuration from CLI arguments."""
    return MonteCarloConfig(
        trial_count=args.trials,
        error_rate=args.error_rate,
        base_seed=args.base_seed,
        matrix_seed=args.matrix_seed,
        matrix_checks=args.matrix_checks,
        matrix_variables=args.matrix_variables,
        ones_per_variable=args.ones_per_variable,
        output_dir=Path(args.output_dir),
    )


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for the Monte Carlo framework."""
    parser = argparse.ArgumentParser(description="Monte Carlo comparison of Sequential and Parallel Relay-BP")
    parser.add_argument("--trials", type=int, default=1000, help="Number of random error patterns to simulate")
    parser.add_argument("--error-rate", type=float, default=0.13, help="Bit error rate used to generate random trials")
    parser.add_argument("--base-seed", type=int, default=1000, help="Base seed used to generate trial randomness")
    parser.add_argument("--matrix-seed", type=int, default=1, help="Seed used to build the synthetic parity-check matrix")
    parser.add_argument("--matrix-checks", type=int, default=8, help="Number of parity-check rows in the synthetic matrix")
    parser.add_argument("--matrix-variables", type=int, default=16, help="Number of variables in the synthetic matrix")
    parser.add_argument("--ones-per-variable", type=int, default=3, help="Number of ones inserted per variable column")
    parser.add_argument("--output-dir", type=str, default=str(Path(__file__).resolve().parent), help="Directory where CSV files and plots will be saved")
    return parser


def main() -> None:
    """Run the Monte Carlo framework and write CSV and plot outputs."""
    parser = build_argument_parser()
    args = parser.parse_args()

    config = _build_config_from_args(args)
    study = MonteCarloStudy(config)
    run_result = study.run()

    output_paths = save_all_outputs(
        run_result=run_result,
        csv_dir=config.csv_output_dir,
        plot_dir=config.plot_output_dir,
        trial_filename=config.csv_trial_filename,
        summary_filename=config.csv_summary_filename,
        dpi=config.plot_dpi,
        bins=config.histogram_bins,
    )

    print("Monte Carlo Relay-BP comparison complete")
    print("-" * 60)
    print(f"Trials:                         {run_result.summary.trial_count}")
    print(f"Average latency (sequential):    {run_result.summary.sequential_average_latency_ms:.3f} ms")
    print(f"Average latency (parallel):      {run_result.summary.parallel_average_latency_ms:.3f} ms")
    print(f"Worst-case latency (sequential): {run_result.summary.sequential_worst_latency_ms:.3f} ms")
    print(f"Worst-case latency (parallel):   {run_result.summary.parallel_worst_latency_ms:.3f} ms")
    print(f"Average iterations (sequential): {run_result.summary.sequential_average_iterations:.2f}")
    print(f"Average iterations (parallel):   {run_result.summary.parallel_average_iterations:.2f}")
    print(f"Success rate (sequential):       {run_result.summary.sequential_success_rate * 100.0:.1f}%")
    print(f"Success rate (parallel):         {run_result.summary.parallel_success_rate * 100.0:.1f}%")
    print(f"Average latency improvement:     {run_result.summary.average_latency_improvement_percent:.2f}%")
    print(f"Outputs written to:              {config.csv_output_dir}")
    print(f"Plots written to:                {config.plot_output_dir}")
    print(f"Trial CSV:                       {output_paths['trial_csv']}")
    print(f"Summary CSV:                     {output_paths['summary_csv']}")


if __name__ == "__main__":
    main()

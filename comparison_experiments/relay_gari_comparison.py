#!/usr/bin/env python3
"""
Controlled software-only comparison between Relay-BP and GARI-NMS decoders.

This script runs a fair, apples-to-apples comparison on the [[144,12,12]]
bivariate bicycle code with matched noise models, shot counts, and iteration
limits. It measures decoding iterations and syndrome convergence. Logical
correctness is not reported because this simulator does not evaluate logical
observables or stabilizer-equivalence of the decoded correction.

USAGE:
    python3 relay_gari_comparison.py \
        --shots 10000 \
        --error-rate 0.003 \
        --max-iters 60 \
        --n-trajectories 1,2,4 \
        --output-dir ./results

AUTHOR: Ganga Devaraju (URECA)
DATE: 2025-09-07
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


# ============================================================================
# CONFIGURATION AND DATA STRUCTURES
# ============================================================================


@dataclass(frozen=True)
class ExperimentConfig:
    """Configuration for the comparison experiment."""

    # Code and noise
    code_name: str = "[[144,12,12]] Bivariate Bicycle (Gross)"
    code_n: int = 144  # code length
    code_k: int = 12   # code dimension
    code_d: int = 12   # code distance
    physical_error_rate: float = 0.003
    noise_model: str = "Depolarizing (Gross circuit-level memory-Z)"
    
    # Experiment size
    num_shots: int = 10000
    max_iterations: int = 60
    relay_trajectories: Tuple[int, ...] = (1, 2, 4)
    
    # Relay-BP specific
    relay_gamma_schedule: Tuple[float, ...] = (0.5, 0.6, 0.65, 0.7, 0.75)
    relay_seeds: Tuple[int, ...] = (11, 22, 33, 44)
    
    # GARI specific
    gari_ensemble_size: int = 1
    
    # Output
    output_dir: Path = Path("./results")
    seed_base: int = 12345


@dataclass(frozen=True)
class DecodingMetrics:
    """Metrics from a single decoding trial."""
    
    converged: bool
    iterations: int
    residual_weight: int
    latency_seconds: float
    decoded_error: Optional[np.ndarray] = None


@dataclass(frozen=True)
class TrialSummary:
    """Summary statistics for a collection of trials."""
    
    name: str
    num_trials: int
    num_converged: int
    num_nonconverged: int
    num_logically_correct: Optional[int]
    num_logical_failures: Optional[int]
    convergence_rate: float
    nonconvergence_rate: float
    
    # Iteration statistics
    mean_iterations: float
    median_iterations: float
    std_iterations: float
    p95_iterations: float
    p99_iterations: float
    max_iterations: float
    min_iterations: float
    
    # Latency statistics
    mean_latency_ms: float
    total_latency_ms: float


# ============================================================================
# RELAY-BP IMPLEMENTATION
# ============================================================================


class RelayBPDecoder:
    """Simplified Relay-BP decoder for fair comparison with GARI."""
    
    def __init__(self, hx: np.ndarray, config: ExperimentConfig):
        """Initialize decoder with code matrices."""
        self.hx = hx  # For now, use X-checks only for fair comparison
        self.n_checks, self.n_variables = hx.shape
        self.config = config
        
        # Build adjacency from sparse matrix
        self._build_adjacency()
        
    def _build_adjacency(self) -> None:
        """Build variable-to-check and check-to-variable adjacency lists."""
        self.var_to_checks: List[List[int]] = [[] for _ in range(self.n_variables)]
        self.check_to_vars: List[List[int]] = [[] for _ in range(self.n_checks)]
        
        for i in range(self.n_checks):
            for j in range(self.n_variables):
                if self.hx[i, j]:
                    self.check_to_vars[i].append(j)
                    self.var_to_checks[j].append(i)
    
    def _syndrome(self, error_vector: np.ndarray) -> np.ndarray:
        """Compute syndrome H * e mod 2."""
        return (self.hx @ error_vector) % 2
    
    def _hard_decision(self, llr: np.ndarray) -> np.ndarray:
        """Hard decision: estimate based on LLR sign."""
        return (llr < 0).astype(np.uint8)
    
    def _residual_weight(self, decoded_error: np.ndarray, syndrome: np.ndarray) -> int:
        """Compute residual syndrome weight."""
        residual = self._syndrome(decoded_error) ^ syndrome
        return int(np.sum(residual))
    
    def decode_min_sum(
        self,
        syndrome: np.ndarray,
        prior_llr: np.ndarray,
        gamma_schedule: Tuple[float, ...],
        seed: int,
    ) -> DecodingMetrics:
        """
        Relay-BP decoder using min-sum with gamma schedule.
        
        Args:
            syndrome: Target syndrome (parity checks)
            prior_llr: Prior log-likelihood ratio from channel
            gamma_schedule: Relay memory strength schedule
            seed: Random seed for lane perturbation
        
        Returns:
            DecodingMetrics with convergence and iteration info
        """
        rng = np.random.default_rng(seed)
        start_time = time.perf_counter()
        
        # Initialize messages
        L_var = prior_llr.copy().astype(float)
        L_var_prev = L_var.copy()
        msg_v2c: Dict[Tuple[int, int], float] = {
            (j, i): prior_llr[j] for j in range(self.n_variables) for i in self.var_to_checks[j]
        }
        
        for iteration in range(self.config.max_iterations):
            gamma = gamma_schedule[min(iteration, len(gamma_schedule) - 1)]
            
            # Check-to-variable messages (min-sum)
            msg_c2v: Dict[Tuple[int, int], float] = {}
            for check_idx in range(self.n_checks):
                vars_in_check = self.check_to_vars[check_idx]
                syndrome_sign = -1.0 if syndrome[check_idx] else 1.0
                
                for var_idx in vars_in_check:
                    incoming = [msg_v2c[(v, check_idx)] for v in vars_in_check if v != var_idx]
                    
                    if not incoming:
                        msg_c2v[(check_idx, var_idx)] = 0.0
                        continue
                    
                    sign_product = np.prod([1.0 if v >= 0 else -1.0 for v in incoming])
                    magnitude = min(abs(v) for v in incoming)
                    msg_c2v[(check_idx, var_idx)] = syndrome_sign * sign_product * magnitude
            
            # Variable-to-check messages with relay memory
            L_var_new = prior_llr.copy().astype(float)
            for var_idx in range(self.n_variables):
                incoming = sum(msg_c2v[(check_idx, var_idx)] for check_idx in self.var_to_checks[var_idx])
                # Add relay memory term and noise
                noise = rng.normal(0, 0.35)
                L_var_new[var_idx] = prior_llr[var_idx] + incoming + gamma * L_var_prev[var_idx] + noise
                
                for check_idx in self.var_to_checks[var_idx]:
                    msg_v2c[(var_idx, check_idx)] = L_var_new[var_idx] - msg_c2v[(check_idx, var_idx)]
            
            L_var_prev = L_var
            L_var = L_var_new
            
            # Check convergence
            decoded_error = self._hard_decision(L_var)
            residual_weight = self._residual_weight(decoded_error, syndrome)
            
            if residual_weight == 0:
                latency = time.perf_counter() - start_time
                return DecodingMetrics(
                    converged=True,
                    iterations=iteration + 1,
                    residual_weight=0,
                    latency_seconds=latency,
                    decoded_error=decoded_error,
                )
        
        # Failed to converge
        latency = time.perf_counter() - start_time
        decoded_error = self._hard_decision(L_var)
        residual_weight = self._residual_weight(decoded_error, syndrome)
        return DecodingMetrics(
            converged=False,
            iterations=self.config.max_iterations,
            residual_weight=residual_weight,
            latency_seconds=latency,
            decoded_error=decoded_error,
        )
    
    def run_ensemble(
        self,
        syndrome: np.ndarray,
        prior_llr: np.ndarray,
        n_trajectories: int,
    ) -> DecodingMetrics:
        """
        Run N parallel trajectories and return first-to-converge result.
        
        Args:
            syndrome: Target syndrome
            prior_llr: Prior LLR
            n_trajectories: Number of parallel trajectories (N)
        
        Returns:
            Metrics from the winning trajectory
        """
        best_iters = self.config.max_iterations
        any_converged = False
        best_latency = float('inf')
        
        for lane_idx in range(n_trajectories):
            gamma_schedule = self.config.relay_gamma_schedule
            seed = self.config.relay_seeds[lane_idx % len(self.config.relay_seeds)]
            
            result = self.decode_min_sum(syndrome, prior_llr, gamma_schedule, seed)
            
            if result.converged:
                any_converged = True
                if result.iterations < best_iters:
                    best_iters = result.iterations
                    best_latency = result.latency_seconds
        
        if not any_converged:
            best_iters = self.config.max_iterations
            best_latency = 0.0  # Placeholder
        
        return DecodingMetrics(
            converged=any_converged,
            iterations=best_iters if any_converged else self.config.max_iterations,
            residual_weight=0 if any_converged else 1,
            latency_seconds=best_latency,
        )


# ============================================================================
# GARI DECODER WRAPPER
# ============================================================================


class GARIDecoder:
    """Wrapper for GARI-NMS normalized min-sum decoder."""
    
    def __init__(self, hx: np.ndarray, hz: np.ndarray, config: ExperimentConfig):
        """Initialize GARI decoder."""
        self.hx = hx
        self.hz = hz
        self.config = config
        self.gari_available = False
        
        # Try to import GARI wrapper
        try:
            import ctypes
            gari_so_path = Path("/tmp/gari-nms/my_decoders/hbplib_v2.so")
            if gari_so_path.exists():
                sys.path.insert(0, "/tmp/gari-nms")
                sys.path.insert(0, "/tmp/gari-nms/my_decoders")
                
                # Load the shared library directly
                lib = ctypes.CDLL(str(gari_so_path))
                
                # Define the decoder function
                lib.ldpc_dec_msaa_quantum_serial_big_matrix_c.argtypes = [
                    ctypes.POINTER(ctypes.c_double), ctypes.c_int,
                    ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int,
                    ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int,
                    ctypes.c_double, ctypes.POINTER(ctypes.c_int8),
                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                    ctypes.c_int, ctypes.c_int,
                    ctypes.POINTER(ctypes.c_int8), ctypes.POINTER(ctypes.c_double)
                ]
                lib.ldpc_dec_msaa_quantum_serial_big_matrix_c.restype = ctypes.c_int
                
                self.lib = lib
                self.gari_available = True
            else:
                print(f"Warning: GARI .so file not found at {gari_so_path}")
        except Exception as e:
            print(f"Warning: GARI decoder not available: {e}")
            self.gari_available = False
    
    def _build_hx_format(self) -> Tuple[np.ndarray, np.ndarray]:
        """Convert dense matrix to GARI's sparse format (rows and columns)."""
        # Build row format: Hrows[i][j] = column index of j-th non-zero in row i
        max_row_weight = int(np.max(np.sum(self.hx, axis=1)))
        Hrows = np.full((self.hx.shape[0], max_row_weight), -1, dtype=np.int32)
        
        for i in range(self.hx.shape[0]):
            cols = np.where(self.hx[i] > 0)[0]
            Hrows[i, :len(cols)] = cols
        
        # Build column format
        max_col_weight = int(np.max(np.sum(self.hx, axis=0)))
        Hcols = np.full((self.hx.shape[1], max_col_weight), -1, dtype=np.int32)
        
        for j in range(self.hx.shape[1]):
            rows = np.where(self.hx[:, j] > 0)[0]
            Hcols[j, :len(rows)] = rows
        
        return Hrows, Hcols
    
    def decode(
        self,
        syndrome: np.ndarray,
        prior_llr: np.ndarray,
    ) -> DecodingMetrics:
        """
        Decode using GARI normalized min-sum.
        
        Args:
            syndrome: Target syndrome
            prior_llr: Prior LLR from channel
        
        Returns:
            DecodingMetrics with convergence info
        """
        if not self.gari_available:
            # Return dummy result if GARI not available
            return DecodingMetrics(
                converged=False,
                iterations=0,
                residual_weight=-1,
                latency_seconds=0.0,
            )
        
        start_time = time.perf_counter()
        
        try:
            import ctypes
            Hrows, Hcols = self._build_hx_format()
            
            # Prepare arrays
            llr = np.ascontiguousarray(prior_llr, dtype=np.float64)
            Hrows_c = np.ascontiguousarray(Hrows, dtype=np.int32)
            Hcols_c = np.ascontiguousarray(Hcols, dtype=np.int32)
            Syn_x = np.ascontiguousarray(syndrome, dtype=np.int8)
            
            N = llr.shape[0]
            Hdec_out = np.zeros(N, dtype=np.int8)
            lambda_out = np.zeros(N, dtype=np.float64)
            
            # Call GARI decoder
            iterations = self.lib.ldpc_dec_msaa_quantum_serial_big_matrix_c(
                llr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), ctypes.c_int(self.config.max_iterations),
                Hrows_c.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), ctypes.c_int(Hrows_c.shape[0]), ctypes.c_int(Hrows_c.shape[1]),
                Hcols_c.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), ctypes.c_int(Hcols_c.shape[0]), ctypes.c_int(Hcols_c.shape[1]),
                ctypes.c_double(0.9),  # alpha normalization
                Syn_x.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
                ctypes.c_int(0), ctypes.c_int(self.hx.shape[0]), ctypes.c_int(self.hx.shape[1]),
                ctypes.c_int(0), ctypes.c_int(0),
                Hdec_out.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
                lambda_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
            )
            
            latency = time.perf_counter() - start_time
            
            # Check if converged
            residual = (self.hx @ Hdec_out) % 2
            residual_weight = int(np.sum(residual ^ syndrome))
            converged = (residual_weight == 0)
            
            return DecodingMetrics(
                converged=converged,
                iterations=int(iterations),
                residual_weight=residual_weight,
                latency_seconds=latency,
                decoded_error=Hdec_out,
            )
        
        except Exception as e:
            print(f"Error in GARI decode: {e}")
            import traceback
            traceback.print_exc()
            return DecodingMetrics(
                converged=False,
                iterations=self.config.max_iterations,
                residual_weight=-1,
                latency_seconds=0.0,
            )


# ============================================================================
# EXPERIMENT RUNNER
# ============================================================================


class ComparisonExperiment:
    """Main experiment runner."""
    
    def __init__(self, config: ExperimentConfig):
        self.config = config
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load code matrices
        self._load_code_matrices()
        
        # Initialize decoders
        self.relay_bp = RelayBPDecoder(self.hx, config)
        self.gari = GARIDecoder(self.hx, self.hz, config)
        
        # Results storage
        self.results: Dict[str, List[DecodingMetrics]] = {}
        self._trial_cache: Dict[int, Tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    
    def _load_code_matrices(self) -> None:
        """Load [[144,12,12]] Gross code matrices."""
        code_dir = Path("/Users/gangadevi.aa/Desktop/URECA-Ganga/Resource-Scalabe and Elastic Relay-BP Acceleration/graphs/generated/gross_code")
        
        self.hx = np.loadtxt(code_dir / "hx.csv", delimiter=",", dtype=np.uint8)
        self.hz = np.loadtxt(code_dir / "hz.csv", delimiter=",", dtype=np.uint8)
        
        print(f"Loaded code: Hx shape {self.hx.shape}, Hz shape {self.hz.shape}")
    
    def _generate_trial(self, shot_idx: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate a random trial: error pattern, syndrome, prior LLR.
        
        Args:
            shot_idx: Trial index (used for seed)
        
        Returns:
            (syndrome, prior_llr, true_error)
        """
        if shot_idx in self._trial_cache:
            return self._trial_cache[shot_idx]

        rng = np.random.default_rng(self.config.seed_base + shot_idx)
        
        # Generate random error
        true_error = (rng.random(self.config.code_n) < self.config.physical_error_rate).astype(np.uint8)
        
        # Compute syndrome
        syndrome = (self.hx @ true_error) % 2
        
        # Generate prior LLR with noise
        # Prior: -1 if error, +1 if no error, corrupted by Gaussian noise
        clean_prior = np.where(true_error == 1, -1.0, 1.0)
        noise = rng.normal(0, 1.3, size=self.config.code_n)
        prior_llr = clean_prior + noise
        
        trial = (syndrome.astype(np.uint8), prior_llr, true_error)
        self._trial_cache[shot_idx] = trial
        return trial
    
    def run_relay_bp_trials(self, n_trajectories: int) -> None:
        """Run Relay-BP trials with N trajectories."""
        result_key = f"relay_bp_n{n_trajectories}"
        self.results[result_key] = []
        
        print(f"\n{'='*70}")
        print(f"Running Relay-BP with N={n_trajectories} trajectories")
        print(f"Shots: {self.config.num_shots}, Max iterations: {self.config.max_iterations}")
        print(f"{'='*70}")
        
        for shot_idx in range(self.config.num_shots):
            syndrome, prior_llr, _ = self._generate_trial(shot_idx)
            
            if n_trajectories == 1:
                # Single trajectory
                result = self.relay_bp.decode_min_sum(
                    syndrome,
                    prior_llr,
                    self.config.relay_gamma_schedule,
                    self.config.relay_seeds[0],
                )
            else:
                # Ensemble of N trajectories
                result = self.relay_bp.run_ensemble(
                    syndrome,
                    prior_llr,
                    n_trajectories,
                )
            
            self.results[result_key].append(result)
            
            if (shot_idx + 1) % max(1, self.config.num_shots // 10) == 0:
                print(f"  Progress: {shot_idx + 1}/{self.config.num_shots}")
    
    def run_gari_trials(self) -> None:
        """Run GARI-NMS trials."""
        result_key = "gari_nms"
        self.results[result_key] = []
        
        print(f"\n{'='*70}")
        print(f"Running GARI-NMS decoder")
        print(f"Shots: {self.config.num_shots}, Max iterations: {self.config.max_iterations}")
        print(f"{'='*70}")
        
        for shot_idx in range(self.config.num_shots):
            syndrome, prior_llr, _ = self._generate_trial(shot_idx)
            result = self.gari.decode(syndrome, prior_llr)
            self.results[result_key].append(result)
            
            if (shot_idx + 1) % max(1, self.config.num_shots // 10) == 0:
                print(f"  Progress: {shot_idx + 1}/{self.config.num_shots}")
    
    def compute_trial_summary(self, result_key: str, name: str) -> TrialSummary:
        """Compute summary statistics for a set of trials."""
        trials = self.results[result_key]
        
        converged = sum(1 for r in trials if r.converged)
        nonconverged = len(trials) - converged
        
        iterations = [r.iterations for r in trials]
        latencies = [r.latency_seconds * 1000 for r in trials]  # Convert to ms
        
        return TrialSummary(
            name=name,
            num_trials=len(trials),
            num_converged=converged,
            num_nonconverged=nonconverged,
            # This simulator checks only Hx * decoded_error == syndrome. It
            # does not evaluate logical observables or stabilizer equivalence.
            num_logically_correct=None,
            num_logical_failures=None,
            convergence_rate=converged / len(trials) if trials else 0.0,
            nonconvergence_rate=nonconverged / len(trials) if trials else 1.0,
            mean_iterations=np.mean(iterations),
            median_iterations=np.median(iterations),
            std_iterations=np.std(iterations),
            p95_iterations=np.percentile(iterations, 95),
            p99_iterations=np.percentile(iterations, 99),
            max_iterations=np.max(iterations),
            min_iterations=np.min(iterations),
            mean_latency_ms=np.mean(latencies),
            total_latency_ms=np.sum(latencies),
        )
    
    def save_results(self) -> None:
        """Save all results to CSV and JSON."""
        # Compute summaries
        summaries = []
        for result_key in self.results.keys():
            if "relay_bp" in result_key:
                n = int(result_key.split("n")[1])
                name = f"Relay-BP N={n}"
            else:
                name = "GARI-NMS"
            
            summary = self.compute_trial_summary(result_key, name)
            summaries.append(summary)
        
        # Save summary as CSV
        summary_file = self.config.output_dir / "comparison_summary.csv"
        with summary_file.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(summaries[0]).keys()))
            writer.writeheader()
            for s in summaries:
                writer.writerow(asdict(s))
        
        print(f"\nSaved summary to {summary_file}")
        
        # Save detailed results
        detailed_file = self.config.output_dir / "detailed_results.json"
        detailed_data = {
            "config": asdict(self.config),
            "summaries": [asdict(s) for s in summaries],
        }
        
        with detailed_file.open("w") as f:
            json.dump(detailed_data, f, indent=2, default=str)
        
        print(f"Saved detailed results to {detailed_file}")
        
        return summaries
    
    def print_summary(self) -> None:
        """Print summary table to console."""
        print(f"\n{'='*90}")
        print("COMPARISON SUMMARY")
        print(f"{'='*90}\n")
        
        for result_key in sorted(self.results.keys()):
            if "relay_bp" in result_key:
                n = int(result_key.split("n")[1])
                name = f"Relay-BP N={n}"
            else:
                name = "GARI-NMS"
            
            summary = self.compute_trial_summary(result_key, name)
            
            print(f"Decoder: {summary.name}")
            print(f"  Trials: {summary.num_trials}")
            print(f"  Converged: {summary.num_converged} ({summary.convergence_rate:.6f})")
            print(f"  Non-converged/timeout: {summary.num_nonconverged} ({summary.nonconvergence_rate:.6f})")
            print("  Logical correctness: unavailable (no logical-observable check)")
            print(f"  Iterations: mean={summary.mean_iterations:.2f}, median={summary.median_iterations:.0f}, "
                  f"P95={summary.p95_iterations:.0f}, P99={summary.p99_iterations:.0f}, max={summary.max_iterations:.0f}")
            print(f"  Latency: mean={summary.mean_latency_ms:.3f}ms, total={summary.total_latency_ms:.1f}ms")
            print()


# ============================================================================
# MAIN
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Controlled software-only Relay-BP vs GARI-NMS comparison"
    )
    parser.add_argument("--shots", type=int, default=10000, help="Number of shots")
    parser.add_argument("--error-rate", type=float, default=0.003, help="Physical error rate")
    parser.add_argument("--max-iters", type=int, default=60, help="Maximum iterations")
    parser.add_argument("--n-trajectories", type=str, default="1,2,4",
                        help="Comma-separated trajectory counts for Relay-BP")
    parser.add_argument("--output-dir", type=Path, default=Path("./comparison_experiments/raw_results"))
    parser.add_argument("--skip-gari", action="store_true", help="Skip GARI runs")
    
    args = parser.parse_args()
    
    n_traj = tuple(int(x) for x in args.n_trajectories.split(","))
    
    config = ExperimentConfig(
        physical_error_rate=args.error_rate,
        num_shots=args.shots,
        max_iterations=args.max_iters,
        relay_trajectories=n_traj,
        output_dir=args.output_dir,
    )
    
    print("=" * 90)
    print("RELAY-BP vs GARI-NMS SOFTWARE-ONLY COMPARISON")
    print("=" * 90)
    print(f"\nExperiment Configuration:")
    print(f"  Code: {config.code_name}")
    print(f"  Noise model: {config.noise_model}")
    print(f"  Physical error rate: {config.physical_error_rate}")
    print(f"  Number of shots: {config.num_shots}")
    print(f"  Max iterations: {config.max_iterations}")
    print(f"  Relay-BP trajectories: {config.relay_trajectories}")
    print(f"  Output dir: {config.output_dir}\n")
    
    # Run experiment
    exp = ComparisonExperiment(config)
    
    # Run Relay-BP with different N
    for n_traj in config.relay_trajectories:
        exp.run_relay_bp_trials(n_traj)
    
    # Run GARI
    if not args.skip_gari:
        exp.run_gari_trials()
    
    # Print and save results
    exp.print_summary()
    exp.save_results()
    
    print("\nExperiment complete!")


if __name__ == "__main__":
    main()

"""
Synthetic trial generation for the Monte Carlo framework.

This module is responsible for creating random binary error patterns, turning
them into syndromes, and assembling the prior LLR vectors that are fed into
the sequential and parallel decoders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from pathlib import Path
import sys


CURRENT_DIR = Path(__file__).resolve().parent
SEQUENTIAL_DIR = CURRENT_DIR.parent / "sequential_relay"
if str(SEQUENTIAL_DIR) not in sys.path:
    sys.path.insert(0, str(SEQUENTIAL_DIR))

from binary_bp_framework import ParityCheckMatrix  # type: ignore  # noqa: E402


@dataclass(frozen=True)
class MonteCarloTrialSample:
    """Container holding one random error pattern and its derived data."""

    trial_index: int
    error_vector: np.ndarray
    syndrome: np.ndarray
    prior_llr: np.ndarray
    error_weight: int
    syndrome_weight: int


def build_monte_carlo_matrix(
    n_checks: int,
    n_variables: int,
    ones_per_variable: int,
    seed: int,
) -> ParityCheckMatrix:
    """Build a reproducible sparse binary parity-check matrix.

    The matrix is synthetic but structured enough to create a nontrivial
    decoding workload for the study. Every column is given a small number of
    ones, and any empty row is repaired so that all checks participate.
    """
    rng = np.random.default_rng(seed)
    matrix = np.zeros((n_checks, n_variables), dtype=np.uint8)

    degree = max(1, min(ones_per_variable, n_checks))
    for variable_index in range(n_variables):
        connected_checks = rng.choice(n_checks, size=degree, replace=False)
        matrix[connected_checks, variable_index] = 1

    for check_index in range(n_checks):
        if not np.any(matrix[check_index]):
            variable_index = int(rng.integers(0, n_variables))
            matrix[check_index, variable_index] = 1

    return ParityCheckMatrix(matrix)


class MonteCarloTrialGenerator:
    """Generate random error patterns and the corresponding decoder inputs."""

    def __init__(self, matrix: ParityCheckMatrix, error_rate: float, llr_magnitude: float, llr_noise_std: float):
        self.matrix = matrix
        self.error_rate = error_rate
        self.llr_magnitude = llr_magnitude
        self.llr_noise_std = llr_noise_std

    def generate_trial(self, trial_index: int, seed: int) -> MonteCarloTrialSample:
        """Generate one random error pattern, syndrome, and noisy LLR prior."""
        rng = np.random.default_rng(seed)
        error_vector = (rng.random(self.matrix.n_variables) < self.error_rate).astype(np.uint8)
        syndrome = self.matrix.syndrome(error_vector)
        prior_llr = np.where(error_vector == 1, -self.llr_magnitude, self.llr_magnitude).astype(float)
        prior_llr += rng.normal(0.0, self.llr_noise_std, size=self.matrix.n_variables)
        return MonteCarloTrialSample(
            trial_index=trial_index,
            error_vector=error_vector,
            syndrome=syndrome,
            prior_llr=prior_llr,
            error_weight=int(np.sum(error_vector)),
            syndrome_weight=int(np.sum(syndrome)),
        )

    def generate_trials(self, trial_count: int, base_seed: int) -> list[MonteCarloTrialSample]:
        """Generate a reproducible list of random test cases."""
        return [self.generate_trial(trial_index=index, seed=base_seed + index) for index in range(trial_count)]

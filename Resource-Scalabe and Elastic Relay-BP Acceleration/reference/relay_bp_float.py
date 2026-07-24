"""Deterministic floating-point Relay-BP baseline for paired format studies."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FloatRelayResult:
    converged: bool
    total_iterations: int
    decoded_error: np.ndarray
    final_syndrome: np.ndarray


class FloatRelayBPDecoder:
    """Small, deterministic min-sum baseline sharing the fixed reference order.

    This is a paired-comparison baseline, not yet a canonical literature trace
    oracle; the separate faithfulness audit remains the release gate.
    """

    def __init__(self, h_matrix: np.ndarray, max_iterations: int = 3, gamma: float = 0.25):
        self.h = h_matrix.astype(np.uint8)
        self.max_iterations = max_iterations
        self.gamma = gamma
        self.check_to_vars = [list(np.flatnonzero(row)) for row in self.h]
        self.var_to_checks = [list(np.flatnonzero(self.h[:, col])) for col in range(self.h.shape[1])]

    def decode(self, prior: np.ndarray, syndrome: np.ndarray) -> FloatRelayResult:
        belief = prior.astype(float).copy()
        memory = np.zeros(self.h.shape[1], dtype=float)
        v_to_c = np.zeros(self.h.shape, dtype=float)
        c_to_v = np.zeros(self.h.shape, dtype=float)
        for iteration in range(1, self.max_iterations + 1):
            for variable, checks in enumerate(self.var_to_checks):
                belief[variable] = prior[variable] + memory[variable] * self.gamma + sum(c_to_v[check, variable] for check in checks)
                for check in checks:
                    v_to_c[check, variable] = belief[variable] - c_to_v[check, variable]
            for check, variables in enumerate(self.check_to_vars):
                for variable in variables:
                    others = [v_to_c[check, other] for other in variables if other != variable]
                    if not others:
                        c_to_v[check, variable] = 0.0
                        continue
                    sign = -1.0 if syndrome[check] else 1.0
                    for value in others:
                        if value < 0:
                            sign *= -1.0
                    c_to_v[check, variable] = sign * min(abs(value) for value in others)
            decoded = (belief < 0).astype(np.uint8)
            residual = ((self.h @ decoded) % 2) ^ syndrome
            if not residual.any():
                return FloatRelayResult(True, iteration, decoded, residual)
        return FloatRelayResult(False, self.max_iterations, decoded, residual)

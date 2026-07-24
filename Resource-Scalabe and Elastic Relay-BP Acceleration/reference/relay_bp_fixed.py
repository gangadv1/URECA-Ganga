"""A small fixed-point Relay-BP decoder for early tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from fixedpoint import FixedConfig, beta_to_int, check_node_update, memory_mix, round_div, sat_b, variable_belief


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


class FixedRelayBPDecoder:
    """Minimal decoder used to generate early integer traces."""

    def __init__(self, h_matrix: np.ndarray, config: FixedRelayConfig):
        self.h = h_matrix.astype(np.uint8)
        self.config = config
        self.check_to_vars = [list(np.flatnonzero(row)) for row in self.h]
        self.var_to_checks = [list(np.flatnonzero(self.h[:, col])) for col in range(self.h.shape[1])]

    def _gamma_int(self, gamma: float) -> int:
        return beta_to_int(gamma, self.config.gamma_scale)

    def _syndrome(self, decoded_error: np.ndarray, target_syndrome: np.ndarray) -> np.ndarray:
        return ((self.h @ decoded_error.astype(np.uint8)) % 2) ^ target_syndrome.astype(np.uint8)

    def decode(self, prior: np.ndarray, syndrome: np.ndarray) -> FixedRelayResult:
        fixed = self.config.fixed
        prior_int = np.array([sat_b(int(value), fixed) for value in prior], dtype=int)
        relay_memory = np.zeros(self.h.shape[1], dtype=int)
        beliefs = prior_int.copy()
        var_to_check = np.zeros(self.h.shape, dtype=int)
        check_to_var = np.zeros(self.h.shape, dtype=int)
        decoded = (beliefs < 0).astype(np.uint8)
        final_syndrome = self._syndrome(decoded, syndrome)
        total_iterations = 0
        legs_used = 0

        for leg_index, leg in enumerate(self.config.leg_configs):
            legs_used = leg_index + 1
            for iteration in range(self.config.max_iterations_per_leg):
                gamma = leg.gamma_schedule[min(iteration, len(leg.gamma_schedule) - 1)] if leg.gamma_schedule else 0.0
                gamma_int = self._gamma_int(float(gamma))

                for var in range(self.h.shape[1]):
                    relay_term = round_div(int(relay_memory[var]) * gamma_int, self.config.gamma_scale)
                    incoming = [check_to_var[check, var] for check in self.var_to_checks[var]]
                    beliefs[var] = variable_belief(prior_int[var], incoming, relay_term, fixed)
                    for check in self.var_to_checks[var]:
                        var_to_check[check, var] = sat_b(beliefs[var] - check_to_var[check, var], fixed)

                for check, variables in enumerate(self.check_to_vars):
                    incoming = [var_to_check[check, var] for var in variables]
                    outgoing = check_node_update(incoming, int(syndrome[check]), fixed)
                    for var, message in zip(variables, outgoing):
                        check_to_var[check, var] = message

                decoded = (beliefs < 0).astype(np.uint8)
                final_syndrome = self._syndrome(decoded, syndrome)
                total_iterations += 1
                if np.all(final_syndrome == 0):
                    return FixedRelayResult(True, total_iterations, legs_used, decoded, final_syndrome, beliefs.copy(), relay_memory.copy())

            for var in range(self.h.shape[1]):
                decision = int(decoded[var])
                y_new = int(beliefs[var]) - 2 * decision
                relay_memory[var] = memory_mix(
                    y_prev=int(relay_memory[var]),
                    y_new=y_new,
                    beta_int=beta_to_int(leg.carry_gamma, fixed.coefficient_M),
                    config=fixed,
                )
                prior_int[var] = sat_b(int(beliefs[var]) + int(relay_memory[var]), fixed)

        return FixedRelayResult(False, total_iterations, legs_used, decoded, final_syndrome, beliefs.copy(), relay_memory.copy())


"""Canonical sparse fixed-point DMem-BP and Relay-BP-S implementation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np
from scipy import sparse

from fixedpoint import FixedConfig


@dataclass(frozen=True)
class FixedRelayLegConfig:
    max_iterations: int
    gamma: float | Sequence[float] | None = None
    gamma_range: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        if self.max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        if (self.gamma is None) == (self.gamma_range is None):
            raise ValueError("specify exactly one of gamma or gamma_range")
        if self.gamma_range is not None and self.gamma_range[0] > self.gamma_range[1]:
            raise ValueError("gamma_range lower bound must not exceed upper bound")


@dataclass(frozen=True)
class FixedRelayConfig:
    fixed: FixedConfig = field(default_factory=FixedConfig)
    leg_configs: Sequence[FixedRelayLegConfig] = field(
        default_factory=lambda: (FixedRelayLegConfig(max_iterations=10, gamma=0.0),)
    )
    S: int = 1
    R: int | None = None
    seed: int = 0
    trace_iterations: bool = False


@dataclass(frozen=True)
class FixedRelayResult:
    converged: bool
    total_iterations: int
    relay_legs: int
    decoded_error: np.ndarray
    final_syndrome: np.ndarray
    beliefs: np.ndarray
    solutions_found: int
    solution_weights: tuple[float, ...] = ()
    saturation_counts: dict[str, int] = field(default_factory=dict)
    trace: list[dict[str, object]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def relay_memory(self) -> np.ndarray:
        """Compatibility view; canonical fixed Relay-BP has no relay-memory state."""
        return np.zeros_like(self.beliefs)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "converged": self.converged,
            "total_iterations": self.total_iterations,
            "relay_legs": self.relay_legs,
            "decoded_error": self.decoded_error.tolist(),
            "final_syndrome": self.final_syndrome.tolist(),
            "beliefs": self.beliefs.tolist(),
            "solutions_found": self.solutions_found,
            "solution_weights": list(self.solution_weights),
            "saturation_counts": self.saturation_counts,
            "trace": self.trace,
            "metadata": self.metadata,
        }


class FixedRelayBPDecoder:
    """Fixed-point realization of the canonical float Relay-BP semantics.

    Stored priors, edge messages, biases, and marginals use signed ``b``-bit
    saturation. Variable-node sums use a signed ``b+g``-bit guard accumulator.
    Gamma is quantized on the independent power-of-two coefficient scale ``M``.
    Every division rounds to nearest with ties away from zero.
    """

    def __init__(self, h_matrix: np.ndarray | sparse.spmatrix | Path | str, config: FixedRelayConfig):
        if isinstance(h_matrix, (Path, str)):
            raise ValueError("Tier-2 fixed decoding requires an explicit sparse incidence matrix")
        if sparse.issparse(h_matrix):
            h = h_matrix.tocsr().astype(np.uint8)
            if h.nnz:
                h.data &= 1
                h.eliminate_zeros()
        else:
            h = sparse.csr_matrix(np.asarray(h_matrix, dtype=np.uint8) & 1)
        if h.ndim != 2:
            raise ValueError("h_matrix must be two-dimensional")
        if config.S <= 0:
            raise ValueError("S must be positive")
        if not config.leg_configs:
            raise ValueError("leg_configs must not be empty")
        self.h_matrix = h
        self.config = config
        self.fixed = config.fixed
        self.S = int(config.S)
        self.R = min(len(config.leg_configs), config.R or len(config.leg_configs))
        self.seed = int(config.seed)
        self._rng = np.random.default_rng(self.seed)
        self._check_indptr = h.indptr.astype(np.int64, copy=True)
        self._edge_variables = h.indices.astype(np.int32, copy=True)
        self._edge_checks = np.repeat(np.arange(h.shape[0], dtype=np.int32), np.diff(h.indptr))
        self._saturations: dict[str, int] = {}

    @property
    def message_min(self) -> int:
        return self.fixed.min_value

    @property
    def message_max(self) -> int:
        return self.fixed.max_value

    @property
    def guard_min(self) -> int:
        return -(1 << (self.fixed.b + self.fixed.g - 1))

    @property
    def guard_max(self) -> int:
        return (1 << (self.fixed.b + self.fixed.g - 1)) - 1

    def _sat(self, values: np.ndarray | int, category: str) -> np.ndarray:
        array = np.asarray(values, dtype=np.int64)
        count = int(np.count_nonzero((array < self.message_min) | (array > self.message_max)))
        self._saturations[category] = self._saturations.get(category, 0) + count
        return np.clip(array, self.message_min, self.message_max).astype(np.int64)

    def _sat_guard(self, values: np.ndarray, category: str) -> np.ndarray:
        array = np.asarray(values, dtype=np.int64)
        count = int(np.count_nonzero((array < self.guard_min) | (array > self.guard_max)))
        self._saturations[category] = self._saturations.get(category, 0) + count
        return np.clip(array, self.guard_min, self.guard_max).astype(np.int64)

    def _gamma_vector(self, leg: FixedRelayLegConfig) -> tuple[np.ndarray, np.ndarray]:
        variables = self.h_matrix.shape[1]
        if leg.gamma_range is not None:
            gamma_float = self._rng.uniform(*leg.gamma_range, size=variables)
        elif np.isscalar(leg.gamma):
            gamma_float = np.full(variables, float(leg.gamma), dtype=float)
        else:
            gamma_float = np.asarray(leg.gamma, dtype=float)
            if gamma_float.shape != (variables,):
                raise ValueError(f"per-node gamma must have shape {(variables,)}")
        scaled = gamma_float * self.fixed.coefficient_M
        gamma_int = (np.sign(scaled) * np.floor(np.abs(scaled) + 0.5)).astype(np.int64)
        return gamma_float, gamma_int

    @staticmethod
    def _round_div_array(values: np.ndarray, denominator: int) -> np.ndarray:
        magnitudes = np.abs(values)
        quotient = magnitudes // denominator
        remainder = magnitudes % denominator
        quotient += (2 * remainder >= denominator).astype(np.int64)
        return np.sign(values).astype(np.int64) * quotient

    def _syndrome(self, decision: np.ndarray) -> np.ndarray:
        counts = np.bincount(
            self._edge_checks,
            weights=decision[self._edge_variables],
            minlength=self.h_matrix.shape[0],
        ).astype(np.int64)
        return (counts & 1).astype(np.uint8)

    def _check_update(self, nu_previous: np.ndarray, syndrome: np.ndarray) -> np.ndarray:
        mu = np.empty_like(nu_previous)
        for check in range(self.h_matrix.shape[0]):
            start = int(self._check_indptr[check])
            stop = int(self._check_indptr[check + 1])
            degree = stop - start
            if degree == 0:
                continue
            syndrome_sign = -1 if syndrome[check] else 1
            if degree == 1:
                mu[start] = syndrome_sign * self.message_max
                continue
            values = nu_previous[start:stop]
            magnitudes = np.abs(values)
            minimum_index = int(np.argmin(magnitudes))
            minimum = int(magnitudes[minimum_index])
            masked = magnitudes.copy()
            masked[minimum_index] = np.iinfo(np.int64).max
            second = int(np.min(masked))
            total_negative = int(np.count_nonzero(values < 0))
            signs = np.where(
                ((total_negative - (values < 0).astype(np.int8)) & 1) != 0,
                -syndrome_sign,
                syndrome_sign,
            )
            outgoing = np.full(degree, minimum, dtype=np.int64)
            outgoing[minimum_index] = second
            mu[start:stop] = self._sat(signs * outgoing, "check_messages")
        return mu

    def decode(
        self,
        prior: Sequence[float | int],
        syndrome: Sequence[int],
        trace_path: Path | None = None,
    ) -> FixedRelayResult:
        prior_float = np.asarray(prior, dtype=float)
        syndrome_array = np.asarray(syndrome, dtype=np.uint8) & 1
        variables = self.h_matrix.shape[1]
        if prior_float.shape != (variables,):
            raise ValueError(f"prior must have shape {(variables,)}")
        if syndrome_array.shape != (self.h_matrix.shape[0],):
            raise ValueError(f"syndrome must have shape {(self.h_matrix.shape[0],)}")
        self._saturations = {}
        rounded_prior = (np.sign(prior_float) * np.floor(np.abs(prior_float) + 0.5)).astype(np.int64)
        physical_prior = self._sat(rounded_prior, "physical_prior")
        initial_marginals = physical_prior.copy()
        final_marginals = physical_prior.copy()
        last_decision = (final_marginals <= 0).astype(np.uint8)
        best_solution: np.ndarray | None = None
        best_marginals: np.ndarray | None = None
        best_weight = np.inf
        weights: list[float] = []
        total_iterations = 0
        legs_executed = 0
        trace: list[dict[str, object]] = []

        for leg_index, leg in enumerate(self.config.leg_configs[: self.R]):
            legs_executed = leg_index + 1
            gamma_float, gamma_int = self._gamma_vector(leg)
            nu_previous = physical_prior[self._edge_variables].copy()
            marginals_previous = initial_marginals.copy()
            for iteration in range(1, leg.max_iterations + 1):
                numerator = (
                    (self.fixed.coefficient_M - gamma_int) * physical_prior
                    + gamma_int * marginals_previous
                )
                lambda_unclipped = self._round_div_array(numerator, self.fixed.coefficient_M)
                lambda_bias = self._sat(lambda_unclipped, "lambda_bias")
                mu = self._check_update(nu_previous, syndrome_array)
                incoming_wide = np.bincount(
                    self._edge_variables, weights=mu, minlength=variables
                ).astype(np.int64)
                incoming = self._sat_guard(incoming_wide, "guard_accumulator")
                nu_unclipped = (
                    lambda_bias[self._edge_variables] + incoming[self._edge_variables] - mu
                )
                nu_current = self._sat(nu_unclipped, "variable_messages")
                final_marginals = self._sat(lambda_bias + incoming, "marginals")
                last_decision = (final_marginals <= 0).astype(np.uint8)
                residual = self._syndrome(last_decision) ^ syndrome_array
                total_iterations += 1
                if self.config.trace_iterations:
                    trace.append(
                        {
                            "leg": leg_index,
                            "iteration": iteration,
                            "residual_weight": int(residual.sum()),
                            "decision_weight": int(last_decision.sum()),
                            "belief_min": int(final_marginals.min()),
                            "belief_max": int(final_marginals.max()),
                            "saturation_counts": dict(self._saturations),
                        }
                    )
                nu_previous = nu_current
                marginals_previous = final_marginals
                if not residual.any():
                    weight = float(np.dot(last_decision, prior_float))
                    weights.append(weight)
                    if weight < best_weight:
                        best_weight = weight
                        best_solution = last_decision.copy()
                        best_marginals = final_marginals.copy()
                    break
            initial_marginals = final_marginals.copy()
            if len(weights) >= self.S:
                break

        converged = best_solution is not None
        decoded = best_solution if best_solution is not None else last_decision
        selected_marginals = best_marginals if best_marginals is not None else final_marginals
        final_residual = self._syndrome(decoded) ^ syndrome_array
        result = FixedRelayResult(
            converged=converged,
            total_iterations=total_iterations,
            relay_legs=legs_executed,
            decoded_error=decoded,
            final_syndrome=final_residual,
            beliefs=selected_marginals,
            solutions_found=len(weights),
            solution_weights=tuple(weights),
            saturation_counts=dict(self._saturations),
            trace=trace,
            metadata={
                "S": self.S,
                "R": self.R,
                "seed": self.seed,
                "best_weight": None if best_solution is None else best_weight,
                "arithmetic": {
                    "message_width_b": self.fixed.b,
                    "guard_bits_g": self.fixed.g,
                    "coefficient_scale_M": self.fixed.coefficient_M,
                    "message_min": self.message_min,
                    "message_max": self.message_max,
                    "guard_min": self.guard_min,
                    "guard_max": self.guard_max,
                    "clip": self.fixed.clip,
                    "rounding": "nearest, ties away from zero",
                    "saturation": "signed clamp after stored-message operations",
                },
                "relay_handoff": "previous leg final marginals only",
                "legacy_relay_memory_used": False,
                "gamma_quantization": "round(gamma*M), per node, fixed within leg",
            },
        )
        if trace_path is not None:
            trace_path.write_text(json.dumps(result.to_json_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

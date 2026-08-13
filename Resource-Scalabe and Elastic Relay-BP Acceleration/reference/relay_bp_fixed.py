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


class BlockFloatingRelayBPDecoder(FixedRelayBPDecoder):
    """Iteration-normalized block-floating variant of the fixed-point model.

    The immutable physical-prior block uses exponent zero.  All mutable
    quantities (biases, both edge-message directions, and marginals) share one
    signed power-of-two exponent per iteration.  The exponent is the smallest
    non-negative integer that fits the provisional iteration outputs in the
    configured signed mantissa.  Exponent changes therefore require only
    arithmetic shifts; gamma remains on the independent ``M`` scale.
    """

    @staticmethod
    def _choose_exponent(maximum_magnitude: float, mantissa_max: int) -> int:
        if maximum_magnitude <= mantissa_max or maximum_magnitude == 0.0:
            return 0
        return max(0, int(np.ceil(np.log2(maximum_magnitude / mantissa_max))))

    @staticmethod
    def _quantize_real(values: np.ndarray, exponent: int) -> np.ndarray:
        scaled = np.asarray(values, dtype=float) / float(2**exponent)
        return (np.sign(scaled) * np.floor(np.abs(scaled) + 0.5)).astype(np.int64)

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
        physical_prior = self._sat(self._quantize_real(prior_float, 0), "physical_prior")
        prior_real = physical_prior.astype(float)
        initial_marginals_real = prior_real.copy()
        final_marginals_real = prior_real.copy()
        last_decision = (final_marginals_real <= 0).astype(np.uint8)
        best_solution: np.ndarray | None = None
        best_marginals: np.ndarray | None = None
        best_weight = np.inf
        weights: list[float] = []
        total_iterations = 0
        legs_executed = 0
        exponent_history: list[int] = []
        exponent_changes = 0
        rescale_nonzero_to_zero = 0
        quantized_value_count = 0
        trace: list[dict[str, object]] = []
        previous_exponent = 0

        for leg_index, leg in enumerate(self.config.leg_configs[: self.R]):
            legs_executed = leg_index + 1
            _, gamma_int = self._gamma_vector(leg)
            gamma_quantized = gamma_int.astype(float) / self.fixed.coefficient_M
            nu_previous_real = prior_real[self._edge_variables].copy()
            marginals_previous_real = initial_marginals_real.copy()

            for iteration in range(1, leg.max_iterations + 1):
                lambda_provisional = (
                    (1.0 - gamma_quantized) * prior_real
                    + gamma_quantized * marginals_previous_real
                )
                mu_provisional = self._check_update_real(nu_previous_real, syndrome_array)
                incoming_provisional = np.bincount(
                    self._edge_variables, weights=mu_provisional, minlength=variables
                )
                nu_provisional = (
                    lambda_provisional[self._edge_variables]
                    + incoming_provisional[self._edge_variables]
                    - mu_provisional
                )
                marginal_provisional = lambda_provisional + incoming_provisional
                maximum = max(
                    float(np.max(np.abs(lambda_provisional))),
                    float(np.max(np.abs(mu_provisional))),
                    float(np.max(np.abs(nu_provisional))),
                    float(np.max(np.abs(marginal_provisional))),
                )
                exponent = self._choose_exponent(maximum, self.message_max)
                if exponent != previous_exponent:
                    exponent_changes += 1
                previous_exponent = exponent
                exponent_history.append(exponent)

                lambda_raw = self._quantize_real(lambda_provisional, exponent)
                mu_raw = self._quantize_real(mu_provisional, exponent)
                for provisional, raw in ((lambda_provisional, lambda_raw), (mu_provisional, mu_raw)):
                    rescale_nonzero_to_zero += int(np.count_nonzero((provisional != 0.0) & (raw == 0)))
                    quantized_value_count += int(raw.size)
                lambda_mantissa = self._sat(lambda_raw, "lambda_bias")
                mu_mantissa = self._sat(mu_raw, "check_messages")
                incoming_wide = np.bincount(
                    self._edge_variables, weights=mu_mantissa, minlength=variables
                ).astype(np.int64)
                incoming = self._sat_guard(incoming_wide, "guard_accumulator")
                nu_raw = lambda_mantissa[self._edge_variables] + incoming[self._edge_variables] - mu_mantissa
                marginal_raw = lambda_mantissa + incoming
                nu_mantissa = self._sat(nu_raw, "variable_messages")
                marginal_mantissa = self._sat(marginal_raw, "marginals")
                nu_previous_real = np.ldexp(nu_mantissa.astype(float), exponent)
                final_marginals_real = np.ldexp(marginal_mantissa.astype(float), exponent)
                marginals_previous_real = final_marginals_real
                last_decision = (marginal_mantissa <= 0).astype(np.uint8)
                residual = self._syndrome(last_decision) ^ syndrome_array
                total_iterations += 1
                if self.config.trace_iterations:
                    trace.append({
                        "leg": leg_index,
                        "iteration": iteration,
                        "exponent": exponent,
                        "residual_weight": int(residual.sum()),
                        "decision_weight": int(last_decision.sum()),
                        "mantissa_min": int(marginal_mantissa.min()),
                        "mantissa_max": int(marginal_mantissa.max()),
                        "saturation_counts": dict(self._saturations),
                    })
                if not residual.any():
                    weight = float(np.dot(last_decision, prior_float))
                    weights.append(weight)
                    if weight < best_weight:
                        best_weight = weight
                        best_solution = last_decision.copy()
                        best_marginals = final_marginals_real.copy()
                    break

            initial_marginals_real = final_marginals_real.copy()
            if len(weights) >= self.S:
                break

        converged = best_solution is not None
        decoded = best_solution if best_solution is not None else last_decision
        selected_marginals = best_marginals if best_marginals is not None else final_marginals_real
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
                    "representation": "iteration-shared block floating",
                    "mantissa_width_b": self.fixed.b,
                    "guard_bits_g": self.fixed.g,
                    "coefficient_scale_M": self.fixed.coefficient_M,
                    "physical_prior_exponent": 0,
                    "mutable_block_exponent_selection": "min e>=0 such that provisional max_abs/2^e <= mantissa_max",
                    "rounding": "nearest, ties away from zero",
                },
                "block_floating": {
                    "exponent_history": exponent_history,
                    "exponent_changes": exponent_changes,
                    "exponent_min": min(exponent_history, default=0),
                    "exponent_max": max(exponent_history, default=0),
                    "rescale_nonzero_to_zero": rescale_nonzero_to_zero,
                    "quantized_value_count": quantized_value_count,
                },
                "relay_handoff": "previous leg final marginals only",
                "legacy_relay_memory_used": False,
                "gamma_quantization": "round(gamma*M), per node, fixed within leg",
            },
        )
        if trace_path is not None:
            trace_path.write_text(json.dumps(result.to_json_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result

    def _check_update_real(self, nu_previous: np.ndarray, syndrome: np.ndarray) -> np.ndarray:
        mu = np.empty_like(nu_previous, dtype=float)
        maximum = float(self.message_max)
        for check in range(self.h_matrix.shape[0]):
            start = int(self._check_indptr[check])
            stop = int(self._check_indptr[check + 1])
            degree = stop - start
            if degree == 0:
                continue
            syndrome_sign = -1.0 if syndrome[check] else 1.0
            if degree == 1:
                mu[start] = syndrome_sign * maximum
                continue
            values = nu_previous[start:stop]
            magnitudes = np.abs(values)
            minimum_index = int(np.argmin(magnitudes))
            minimum = float(magnitudes[minimum_index])
            masked = magnitudes.copy()
            masked[minimum_index] = np.inf
            second = float(np.min(masked))
            total_negative = int(np.count_nonzero(values < 0.0))
            signs = np.where(
                ((total_negative - (values < 0.0).astype(np.int8)) & 1) != 0,
                -syndrome_sign,
                syndrome_sign,
            )
            outgoing = np.full(degree, minimum, dtype=float)
            outgoing[minimum_index] = second
            mu[start:stop] = signs * outgoing
        return mu


class SeparatedExponentRelayBPDecoder(BlockFloatingRelayBPDecoder):
    """Per-iteration block floating with separate edge and node-state scales.

    ``mu`` and ``nu`` share the edge exponent. ``lambda`` and the marginals
    share the state exponent. Cross-block additions are aligned using rounded
    power-of-two shifts. The immutable physical prior remains at exponent zero.
    """

    def __init__(
        self,
        h_matrix: np.ndarray | sparse.spmatrix | Path | str,
        config: FixedRelayConfig,
        *,
        headroom_fraction: float = 1.0,
        state_percentile: float | None = None,
        exponent_bits: int = 6,
    ):
        super().__init__(h_matrix, config)
        if not 0.0 < headroom_fraction <= 1.0:
            raise ValueError("headroom_fraction must be in (0, 1]")
        self.headroom_fraction = float(headroom_fraction)
        if state_percentile is not None and not 0.0 < state_percentile <= 100.0:
            raise ValueError("state_percentile must be in (0, 100]")
        self.state_percentile = state_percentile
        if exponent_bits <= 0:
            raise ValueError("exponent_bits must be positive")
        self.exponent_bits = int(exponent_bits)
        self.exponent_max = (1 << self.exponent_bits) - 1

    @staticmethod
    def _align_mantissa(values: np.ndarray, source_exponent: int, target_exponent: int) -> np.ndarray:
        values = np.asarray(values, dtype=np.int64)
        shift = source_exponent - target_exponent
        if shift == 0:
            return values.copy()
        if shift > 0:
            return values * (1 << shift)
        return FixedRelayBPDecoder._round_div_array(values, 1 << (-shift))

    def _block_exponent(self, maximum_magnitude: float) -> int:
        target = max(1, int(np.floor(self.message_max * self.headroom_fraction)))
        return min(self.exponent_max, self._choose_exponent(maximum_magnitude, target))

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
        physical_prior = self._sat(self._quantize_real(prior_float, 0), "physical_prior")
        prior_real = physical_prior.astype(float)
        initial_marginals_real = prior_real.copy()
        final_marginals_real = prior_real.copy()
        last_decision = (final_marginals_real <= 0).astype(np.uint8)
        best_solution: np.ndarray | None = None
        best_marginals: np.ndarray | None = None
        best_weight = np.inf
        weights: list[float] = []
        total_iterations = 0
        legs_executed = 0
        edge_history: list[int] = []
        state_history: list[int] = []
        edge_changes = 0
        state_changes = 0
        previous_edge_exponent = 0
        previous_state_exponent = 0
        edge_zeroed = 0
        state_zeroed = 0
        edge_values = 0
        state_values = 0
        state_deliberately_clipped = 0
        state_clip_candidates = 0
        threshold_bucket_equal = 0
        threshold_bucket_above = 0
        trace: list[dict[str, object]] = []

        for leg_index, leg in enumerate(self.config.leg_configs[: self.R]):
            legs_executed = leg_index + 1
            _, gamma_int = self._gamma_vector(leg)
            gamma_quantized = gamma_int.astype(float) / self.fixed.coefficient_M
            nu_previous_real = prior_real[self._edge_variables].copy()
            marginals_previous_real = initial_marginals_real.copy()

            for iteration in range(1, leg.max_iterations + 1):
                lambda_provisional = (
                    (1.0 - gamma_quantized) * prior_real
                    + gamma_quantized * marginals_previous_real
                )
                mu_provisional = self._check_update_real(nu_previous_real, syndrome_array)
                incoming_provisional = np.bincount(
                    self._edge_variables, weights=mu_provisional, minlength=variables
                )
                nu_provisional = (
                    lambda_provisional[self._edge_variables]
                    + incoming_provisional[self._edge_variables]
                    - mu_provisional
                )
                marginal_provisional = lambda_provisional + incoming_provisional

                edge_exponent = self._block_exponent(max(
                    float(np.max(np.abs(mu_provisional))),
                    float(np.max(np.abs(nu_provisional))),
                ))
                state_magnitudes = np.concatenate((
                    np.abs(lambda_provisional), np.abs(marginal_provisional)
                ))
                if self.state_percentile is None or self.state_percentile == 100.0:
                    state_threshold = float(np.max(state_magnitudes))
                else:
                    state_threshold = float(np.percentile(
                        state_magnitudes, self.state_percentile, method="linear"
                    ))
                state_clip_candidates += int(state_magnitudes.size)
                state_deliberately_clipped += int(np.count_nonzero(state_magnitudes > state_threshold))
                if state_threshold > 0.0:
                    threshold_bucket = int(np.floor(np.log2(state_threshold)))
                    positive = state_magnitudes[state_magnitudes > 0.0]
                    buckets = np.floor(np.log2(positive)).astype(np.int64)
                    threshold_bucket_equal += int(np.count_nonzero(buckets == threshold_bucket))
                    threshold_bucket_above += int(np.count_nonzero(buckets > threshold_bucket))
                state_exponent = self._block_exponent(state_threshold)
                edge_changes += edge_exponent != previous_edge_exponent
                state_changes += state_exponent != previous_state_exponent
                previous_edge_exponent = edge_exponent
                previous_state_exponent = state_exponent
                edge_history.append(edge_exponent)
                state_history.append(state_exponent)

                lambda_clipped = np.clip(lambda_provisional, -state_threshold, state_threshold)
                lambda_raw = self._quantize_real(lambda_clipped, state_exponent)
                mu_raw = self._quantize_real(mu_provisional, edge_exponent)
                state_zeroed += int(np.count_nonzero((lambda_clipped != 0.0) & (lambda_raw == 0)))
                edge_zeroed += int(np.count_nonzero((mu_provisional != 0.0) & (mu_raw == 0)))
                state_values += int(lambda_raw.size)
                edge_values += int(mu_raw.size)
                lambda_mantissa = self._sat(lambda_raw, "state_lambda")
                mu_mantissa = self._sat(mu_raw, "edge_mu")

                incoming_edge_wide = np.bincount(
                    self._edge_variables, weights=mu_mantissa, minlength=variables
                ).astype(np.int64)
                incoming_edge = self._sat_guard(incoming_edge_wide, "guard_accumulator")
                lambda_at_edge = self._align_mantissa(
                    lambda_mantissa, state_exponent, edge_exponent
                )
                nu_raw = (
                    lambda_at_edge[self._edge_variables]
                    + incoming_edge[self._edge_variables]
                    - mu_mantissa
                )
                nu_mantissa = self._sat(nu_raw, "edge_nu")

                incoming_at_state = self._align_mantissa(
                    incoming_edge, edge_exponent, state_exponent
                )
                marginal_raw = lambda_mantissa + incoming_at_state
                state_cap_mantissa = max(0, int(np.floor(state_threshold / float(2**state_exponent))))
                marginal_raw = np.clip(marginal_raw, -state_cap_mantissa, state_cap_mantissa)
                marginal_mantissa = self._sat(marginal_raw, "state_marginals")
                edge_zeroed += int(np.count_nonzero((nu_raw != 0) & (nu_mantissa == 0)))
                marginal_clipped = np.clip(
                    marginal_provisional, -state_threshold, state_threshold
                )
                state_zeroed += int(np.count_nonzero(
                    (marginal_clipped != 0.0) & (marginal_mantissa == 0)
                ))
                edge_values += int(nu_mantissa.size)
                state_values += int(marginal_mantissa.size)

                nu_previous_real = np.ldexp(nu_mantissa.astype(float), edge_exponent)
                final_marginals_real = np.ldexp(marginal_mantissa.astype(float), state_exponent)
                marginals_previous_real = final_marginals_real
                last_decision = (marginal_mantissa <= 0).astype(np.uint8)
                residual = self._syndrome(last_decision) ^ syndrome_array
                total_iterations += 1
                if self.config.trace_iterations:
                    trace.append({
                        "leg": leg_index,
                        "iteration": iteration,
                        "edge_exponent": edge_exponent,
                        "state_exponent": state_exponent,
                        "residual_weight": int(residual.sum()),
                        "decision_weight": int(last_decision.sum()),
                        "saturation_counts": dict(self._saturations),
                    })
                if not residual.any():
                    weight = float(np.dot(last_decision, prior_float))
                    weights.append(weight)
                    if weight < best_weight:
                        best_weight = weight
                        best_solution = last_decision.copy()
                        best_marginals = final_marginals_real.copy()
                    break

            initial_marginals_real = final_marginals_real.copy()
            if len(weights) >= self.S:
                break

        converged = best_solution is not None
        decoded = best_solution if best_solution is not None else last_decision
        selected_marginals = best_marginals if best_marginals is not None else final_marginals_real
        result = FixedRelayResult(
            converged=converged,
            total_iterations=total_iterations,
            relay_legs=legs_executed,
            decoded_error=decoded,
            final_syndrome=self._syndrome(decoded) ^ syndrome_array,
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
                    "representation": "iteration-shared separate edge/state block floating",
                    "mantissa_width_b": self.fixed.b,
                    "guard_bits_g": self.fixed.g,
                    "coefficient_scale_M": self.fixed.coefficient_M,
                    "headroom_fraction": self.headroom_fraction,
                    "state_percentile": self.state_percentile,
                    "exponent_bits": self.exponent_bits,
                    "exponent_unsigned_max": self.exponent_max,
                    "rounding": "nearest, ties away from zero",
                    "cross_block_alignment": "rounded power-of-two shifts",
                },
                "block_floating": {
                    "edge_exponent_history": edge_history,
                    "state_exponent_history": state_history,
                    "edge_exponent_changes": edge_changes,
                    "state_exponent_changes": state_changes,
                    "edge_exponent_min": min(edge_history, default=0),
                    "edge_exponent_max": max(edge_history, default=0),
                    "state_exponent_min": min(state_history, default=0),
                    "state_exponent_max": max(state_history, default=0),
                    "edge_nonzero_to_zero": edge_zeroed,
                    "state_nonzero_to_zero": state_zeroed,
                    "edge_value_count": edge_values,
                    "state_value_count": state_values,
                    "state_deliberately_clipped": state_deliberately_clipped,
                    "state_clip_candidates": state_clip_candidates,
                    "threshold_leading_one_bucket_equal": threshold_bucket_equal,
                    "threshold_leading_one_bucket_above": threshold_bucket_above,
                },
                "relay_handoff": "previous leg final marginals only",
                "legacy_relay_memory_used": False,
                "gamma_quantization": "round(gamma*M), per node, fixed within leg",
            },
        )
        if trace_path is not None:
            trace_path.write_text(json.dumps(result.to_json_dict(), indent=2, sort_keys=True) + "\n")
        return result

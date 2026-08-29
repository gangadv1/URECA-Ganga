"""Floating-point implementation of DMem-BP and Relay-BP-S.

This module follows Algorithm 1 and Equations (1)--(4) of the Relay-BP
paper.  It is deliberately independent of the integer/fixed-point reference
so changes to the canonical floating-point algorithm do not alter those
models.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

try:
    from scipy import sparse
except ModuleNotFoundError:  # pragma: no cover - dense use remains supported
    sparse = None


@dataclass(frozen=True)
class RelayLegConfig:
    """Configuration for one DMem-BP relay leg.

    ``gamma`` is either a scalar (uniform memory strength) or one value per
    variable node.  ``gamma_range`` requests independent uniform samples and
    is mutually exclusive with ``gamma``.
    """

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
class FloatRelayTraceRecord:
    leg_index: int
    iteration: int
    gamma: list[float]
    lambda_bias: list[float]
    beliefs: list[float]
    decoded_error: list[int]
    residual: list[int]
    residual_score: int
    converged: bool
    var_to_check: list[list[float]] | None = None
    check_to_var: list[list[float]] | None = None


@dataclass(frozen=True)
class FloatRelayResult:
    converged: bool
    total_iterations: int
    relay_legs: int
    decoded_error: np.ndarray
    final_syndrome: np.ndarray
    beliefs: np.ndarray
    solutions_found: int
    solution_weights: tuple[float, ...] = ()
    trace: list[FloatRelayTraceRecord] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

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
            "trace": [asdict(record) for record in self.trace],
            "metadata": self.metadata,
        }

    def write_trace(self, path: Path) -> Path:
        path.write_text(json.dumps(self.to_json_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


class FloatRelayBPDecoder:
    """Floating-point Relay-BP-S decoder.

    With no explicit legacy ``max_iterations``/``gamma`` or ``leg_configs``,
    the constructor uses the gross-code settings reported in the paper: a
    uniform first leg at gamma=0.125 for 80 iterations, followed by up to
    ``R - 1`` 60-iteration legs sampled from [-0.24, 0.66].
    """

    def __init__(
        self,
        h_matrix: np.ndarray | Path | str,
        max_iterations: int | None = None,
        gamma: float | None = None,
        leg_configs: Sequence[RelayLegConfig] | None = None,
        trace_messages: bool = False,
        iteration_callback: Callable[[dict[str, object]], None] | None = None,
        *,
        S: int = 1,
        R: int = 301,
        seed: int = 0,
        relay_handoff: bool = True,
    ):
        if isinstance(h_matrix, (Path, str)):
            from graph_loader import load_graph_package

            h = load_graph_package(Path(h_matrix)).h_matrix
        else:
            h = h_matrix
        if sparse is not None and sparse.issparse(h):
            h = h.tocsr().astype(np.uint8)
            if h.nnz:
                h.data &= 1
                h.eliminate_zeros()
        else:
            h = np.asarray(h)
        if h.ndim != 2:
            raise ValueError("h_matrix must be two-dimensional")
        self.h_matrix = h if sparse is not None and sparse.issparse(h) else np.asarray(h, dtype=np.uint8) & 1
        if S <= 0 or R <= 0:
            raise ValueError("S and R must be positive")
        self.S = int(S)
        self.R = int(R)
        self.seed = int(seed)
        self.relay_handoff = bool(relay_handoff)
        # Match the official decoder's RNG lifetime: gamma sampling advances
        # one persistent stream across sequential decode calls.
        self._rng = np.random.default_rng(self.seed)
        self.trace_messages = bool(trace_messages)
        # Optional analysis-only observation hook.  The callback is disabled by
        # default and is deliberately outside the decoder's state transitions:
        # it observes the completed iteration before the normal convergence
        # break and must not mutate the supplied arrays.
        self.iteration_callback = iteration_callback

        if leg_configs is not None:
            if not leg_configs:
                raise ValueError("leg_configs must not be empty")
            self.leg_configs = tuple(leg_configs[: self.R])
        elif max_iterations is not None or gamma is not None:
            # Backward-compatible explicit one-leg construction.
            self.leg_configs = (
                RelayLegConfig(
                    max_iterations=3 if max_iterations is None else int(max_iterations),
                    gamma=0.25 if gamma is None else float(gamma),
                ),
            )
        else:
            self.leg_configs = (
                RelayLegConfig(max_iterations=80, gamma=0.125),
                *(RelayLegConfig(max_iterations=60, gamma_range=(-0.24, 0.66)) for _ in range(self.R - 1)),
            )

        if sparse is not None and sparse.issparse(self.h_matrix):
            h_csr = self.h_matrix.tocsr()
            h_csc = self.h_matrix.tocsc()
            self.check_to_vars = [
                h_csr.indices[h_csr.indptr[check] : h_csr.indptr[check + 1]].tolist()
                for check in range(h_csr.shape[0])
            ]
            self.var_to_checks = [
                h_csc.indices[h_csc.indptr[variable] : h_csc.indptr[variable + 1]].tolist()
                for variable in range(h_csc.shape[1])
            ]
        else:
            self.check_to_vars = [list(np.flatnonzero(row)) for row in self.h_matrix]
            self.var_to_checks = [list(np.flatnonzero(self.h_matrix[:, col])) for col in range(self.h_matrix.shape[1])]
        self._check_indptr = np.zeros(self.h_matrix.shape[0] + 1, dtype=np.int64)
        self._check_indptr[1:] = np.cumsum([len(neighbors) for neighbors in self.check_to_vars], dtype=np.int64)
        self._edge_variables = np.asarray(
            [variable for neighbors in self.check_to_vars for variable in neighbors], dtype=np.int32
        )
        self._edge_checks = np.repeat(
            np.arange(self.h_matrix.shape[0], dtype=np.int32), np.diff(self._check_indptr)
        )

    @classmethod
    def from_package(cls, package_path: Path | str, **kwargs: object) -> "FloatRelayBPDecoder":
        return cls(package_path, **kwargs)

    def _gamma_vector(self, config: RelayLegConfig, rng: np.random.Generator) -> np.ndarray:
        variables = self.h_matrix.shape[1]
        if config.gamma_range is not None:
            low, high = config.gamma_range
            return rng.uniform(low, high, size=variables)
        if np.isscalar(config.gamma):
            return np.full(variables, float(config.gamma), dtype=float)
        values = np.asarray(config.gamma, dtype=float)
        if values.shape != (variables,):
            raise ValueError(f"per-node gamma must have shape {(variables,)}, got {values.shape}")
        return values.copy()

    def _syndrome(self, decision: np.ndarray) -> np.ndarray:
        parity_counts = np.bincount(
            self._edge_checks,
            weights=decision[self._edge_variables],
            minlength=self.h_matrix.shape[0],
        ).astype(np.int64)
        return (parity_counts & 1).astype(np.uint8)

    def _check_update(self, nu_previous: np.ndarray, syndrome_array: np.ndarray) -> np.ndarray:
        mu = np.empty_like(nu_previous)
        maximum = np.finfo(float).max
        for check in range(self.h_matrix.shape[0]):
            start = int(self._check_indptr[check])
            stop = int(self._check_indptr[check + 1])
            values = nu_previous[start:stop]
            degree = stop - start
            syndrome_sign = -1.0 if syndrome_array[check] else 1.0
            if degree == 0:
                continue
            if degree == 1:
                mu[start] = syndrome_sign * maximum
                continue
            magnitudes = np.abs(values)
            minimum_index = int(np.argmin(magnitudes))
            minimum = float(magnitudes[minimum_index])
            masked = magnitudes.copy()
            masked[minimum_index] = np.inf
            second_minimum = float(np.min(masked))
            total_negative = int(np.count_nonzero(values < 0.0))
            excluded_negative = (values < 0.0).astype(np.int8)
            signs = np.where(((total_negative - excluded_negative) & 1) != 0, -syndrome_sign, syndrome_sign)
            outgoing_magnitudes = np.full(degree, minimum, dtype=float)
            outgoing_magnitudes[minimum_index] = second_minimum
            mu[start:stop] = signs * outgoing_magnitudes
        return mu

    def _trace_message_matrices(self, nu: np.ndarray, mu: np.ndarray) -> tuple[list[list[float]], list[list[float]]]:
        checks, variables = self.h_matrix.shape
        nu_dense = np.zeros((checks, variables), dtype=float)
        mu_dense = np.zeros((checks, variables), dtype=float)
        nu_dense[self._edge_checks, self._edge_variables] = nu
        mu_dense[self._edge_checks, self._edge_variables] = mu
        return nu_dense.tolist(), mu_dense.tolist()

    @staticmethod
    def _hard_decision(marginals: np.ndarray) -> np.ndarray:
        # Match the official implementation's tie convention: a zero
        # posterior is decoded as an error.
        return (marginals <= 0.0).astype(np.uint8)

    def decode(
        self,
        prior: Sequence[float | int],
        syndrome: Sequence[int],
        trace_path: Path | None = None,
    ) -> FloatRelayResult:
        lambdas = np.asarray(prior, dtype=float)
        syndrome_array = np.asarray(syndrome, dtype=np.uint8) & 1
        variables = self.h_matrix.shape[1]
        checks = self.h_matrix.shape[0]
        if lambdas.shape != (variables,):
            raise ValueError(f"prior must have shape {(variables,)}, got {lambdas.shape}")
        if syndrome_array.shape != (checks,):
            raise ValueError(f"syndrome must have shape {(checks,)}, got {syndrome_array.shape}")

        initial_marginals = lambdas.copy()
        final_marginals = initial_marginals.copy()
        last_decision = self._hard_decision(final_marginals)
        last_residual = self._syndrome(last_decision) ^ syndrome_array
        best_solution: np.ndarray | None = None
        best_weight = np.inf
        best_marginals: np.ndarray | None = None
        solution_weights: list[float] = []
        total_iterations = 0
        legs_executed = 0
        leg_gamma_summaries: list[dict[str, float | int]] = []
        trace: list[FloatRelayTraceRecord] = []

        for leg_index, leg_config in enumerate(self.leg_configs[: self.R]):
            legs_executed = leg_index + 1
            gamma_values = self._gamma_vector(leg_config, self._rng)
            leg_gamma_summaries.append(
                {
                    "minimum": float(np.min(gamma_values)),
                    "maximum": float(np.max(gamma_values)),
                    "negative_count": int(np.count_nonzero(gamma_values < 0.0)),
                }
            )

            # Algorithm 1 restarts edge messages from the physical LLRs for
            # every leg and carries only M(0) between legs.
            nu_previous = lambdas[self._edge_variables].copy()

            marginals_previous = initial_marginals.copy()
            for iteration in range(1, leg_config.max_iterations + 1):
                # Eq. (4): the paper uses a plus sign before gamma*M(t-1).
                lambda_bias = (1.0 - gamma_values) * lambdas + gamma_values * marginals_previous

                # Eq. (1): check-to-variable update from nu(t-1).
                mu = self._check_update(nu_previous, syndrome_array)

                # Eq. (2): variable-to-check update from current mu(t).
                incoming_total = np.bincount(
                    self._edge_variables, weights=mu, minlength=variables
                )
                nu_current = lambda_bias[self._edge_variables] + incoming_total[self._edge_variables] - mu

                # Eq. (3), hard decision, and H*e_hat == syndrome.
                final_marginals = lambda_bias + incoming_total
                last_decision = self._hard_decision(final_marginals)
                last_residual = self._syndrome(last_decision) ^ syndrome_array
                converged = not bool(last_residual.any())
                total_iterations += 1

                if self.trace_messages:
                    nu_trace, mu_trace = self._trace_message_matrices(nu_current, mu)
                    trace.append(
                        FloatRelayTraceRecord(
                            leg_index=leg_index,
                            iteration=iteration,
                            gamma=gamma_values.tolist(),
                            lambda_bias=lambda_bias.tolist(),
                            beliefs=final_marginals.tolist(),
                            decoded_error=last_decision.astype(int).tolist(),
                            residual=last_residual.astype(int).tolist(),
                            residual_score=int(last_residual.sum()),
                            converged=converged,
                            var_to_check=nu_trace,
                            check_to_var=mu_trace,
                        )
                    )

                if self.iteration_callback is not None:
                    self.iteration_callback(
                        {
                            "leg_index": leg_index,
                            "iteration": iteration,
                            "global_iteration": total_iterations,
                            "gamma": gamma_values,
                            "lambda_bias": lambda_bias,
                            "beliefs": final_marginals,
                            "decoded_error": last_decision,
                            "residual": last_residual,
                            "converged": converged,
                        }
                    )

                nu_previous = nu_current
                marginals_previous = final_marginals
                if converged:
                    weight = float(np.dot(last_decision, lambdas))
                    solution_weights.append(weight)
                    if weight < best_weight:
                        best_weight = weight
                        best_solution = last_decision.copy()
                        best_marginals = final_marginals.copy()
                    break

            # Relay exactly the final marginal, including after a successful
            # leg when Relay-BP-S still seeks more solutions.
            initial_marginals = final_marginals.copy() if self.relay_handoff else lambdas.copy()
            if len(solution_weights) >= self.S:
                break

        converged = best_solution is not None
        decoded_error = best_solution if best_solution is not None else last_decision
        final_residual = self._syndrome(decoded_error) ^ syndrome_array
        selected_marginals = best_marginals if best_marginals is not None else final_marginals
        result = FloatRelayResult(
            converged=converged,
            total_iterations=total_iterations,
            relay_legs=legs_executed,
            decoded_error=decoded_error,
            final_syndrome=final_residual,
            beliefs=selected_marginals,
            solutions_found=len(solution_weights),
            solution_weights=tuple(solution_weights),
            trace=trace,
            metadata={
                "S": self.S,
                "R": self.R,
                "seed": self.seed,
                "relay_handoff": self.relay_handoff,
                "leg_gamma_summaries": leg_gamma_summaries,
                "best_weight": None if best_solution is None else best_weight,
                "leg_max_iterations": [leg.max_iterations for leg in self.leg_configs[: self.R]],
            },
        )
        if trace_path is not None:
            result.write_trace(trace_path)
        return result

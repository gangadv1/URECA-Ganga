"""
Binary belief-propagation decoder framework.

This module provides a modular, object-oriented Binary BP implementation that
can later be extended into Relay-BP by adding memory terms or alternative
update schedules. The current code focuses on the core message-passing loop
used by a classical sum-product / min-sum style decoder for binary parity-
check matrices.

The design intentionally keeps the major responsibilities separate:

- ParityCheckMatrix stores the code structure and adjacency information.
- VariableNode stores state local to each variable node.
- CheckNode stores state local to each check node.
- BPDecoder coordinates message passing, syndrome checks, and stopping logic.

This separation makes it easier to add Relay-style memory, per-lane schedules,
or hardware-oriented optimizations later without rewriting the decoder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Dict, Iterable, List, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecodeResult:
    """Summary of a single BP decode attempt.

    The result records the final hard decision, whether the syndrome became
    zero, how many iterations were executed, and the last syndrome value.
    These fields are useful for research analysis and later comparison with
    Relay-BP variants.
    """

    converged: bool
    iterations: int
    latency_seconds: float
    final_syndrome: np.ndarray
    decoded_error: np.ndarray


@dataclass(frozen=True)
class BPConfig:
    """Configuration for the BP decoder.

    The decoder uses a maximum iteration limit and a message damping factor.
    Damping is kept separate from Relay memory so the current framework stays
    a clean baseline that can later accept Relay-specific terms.
    """

    max_iterations: int = 50
    damping: float = 0.0


# ---------------------------------------------------------------------------
# Parity-check matrix
# ---------------------------------------------------------------------------


class ParityCheckMatrix:
    """Binary parity-check matrix with cached graph connectivity.

    The class accepts a dense binary matrix and converts it into adjacency
    lists. Those adjacency lists are then reused by the variable and check
    node objects during message passing.
    """

    def __init__(self, matrix: np.ndarray):
        if matrix.ndim != 2:
            raise ValueError("Parity-check matrix must be two-dimensional")
        if not np.array_equal(matrix, matrix.astype(np.uint8)):
            raise ValueError("Parity-check matrix must contain only binary values")

        self.matrix = matrix.astype(np.uint8).copy()
        self.n_checks, self.n_variables = self.matrix.shape
        self._variable_to_checks, self._check_to_variables = self._build_adjacency()

    @classmethod
    def from_dense(cls, matrix: Sequence[Sequence[int]]) -> "ParityCheckMatrix":
        """Construct a parity-check matrix from any dense binary-like input."""
        return cls(np.array(matrix, dtype=np.uint8))

    def _build_adjacency(self) -> tuple[list[list[int]], list[list[int]]]:
        """Build variable-to-check and check-to-variable adjacency lists."""
        variable_to_checks = [[] for _ in range(self.n_variables)]
        check_to_variables = [[] for _ in range(self.n_checks)]

        for check_index in range(self.n_checks):
            for variable_index in range(self.n_variables):
                if self.matrix[check_index, variable_index] == 1:
                    variable_to_checks[variable_index].append(check_index)
                    check_to_variables[check_index].append(variable_index)

        return variable_to_checks, check_to_variables

    @property
    def variable_to_checks(self) -> list[list[int]]:
        """Return the checks connected to each variable node."""
        return self._variable_to_checks

    @property
    def check_to_variables(self) -> list[list[int]]:
        """Return the variables connected to each check node."""
        return self._check_to_variables

    def syndrome(self, error_vector: np.ndarray) -> np.ndarray:
        """Compute the binary syndrome Hx mod 2."""
        if error_vector.shape != (self.n_variables,):
            raise ValueError(f"error_vector must have shape {(self.n_variables,)}, got {error_vector.shape}")
        if error_vector.dtype != np.uint8:
            error_vector = error_vector.astype(np.uint8)
        return (self.matrix @ error_vector) % 2


# ---------------------------------------------------------------------------
# Node state
# ---------------------------------------------------------------------------


class VariableNode:
    """Stateful variable-node object used by the BP decoder.

    Each variable node stores its prior log-likelihood ratio and the current
    messages exchanged with adjacent check nodes. The node does not decide the
    global stopping condition; it only maintains local state and computes the
    outgoing messages requested by the decoder.
    """

    def __init__(self, index: int, connected_checks: Sequence[int], prior_llr: float):
        self.index = index
        self.connected_checks = list(connected_checks)
        self.prior_llr = float(prior_llr)
        self.belief = float(prior_llr)
        self.incoming_messages: Dict[int, float] = {check_index: 0.0 for check_index in self.connected_checks}
        self.outgoing_messages: Dict[int, float] = {check_index: 0.0 for check_index in self.connected_checks}

    def reset(self, prior_llr: float) -> None:
        """Reset the node state for a new decoding attempt."""
        self.prior_llr = float(prior_llr)
        self.belief = float(prior_llr)
        for check_index in self.connected_checks:
            self.incoming_messages[check_index] = 0.0
            self.outgoing_messages[check_index] = 0.0

    def update_incoming(self, check_index: int, message: float) -> None:
        """Store a message received from one adjacent check node."""
        self.incoming_messages[check_index] = float(message)

    def compute_belief(self, relay_memory_term: float = 0.0) -> float:
        """Compute the current belief from the prior and all incoming messages.

        The optional relay_memory_term is deliberately included as a hook for
        later Relay-BP work. In the baseline BP decoder it remains zero, but a
        Relay implementation can use this parameter to inject a memory term or
        a schedule-dependent state contribution.
        """
        self.belief = self.prior_llr + sum(self.incoming_messages.values()) + relay_memory_term
        return self.belief

    def hard_decision(self) -> np.uint8:
        """Return the binary hard decision derived from the current belief."""
        return np.uint8(self.belief < 0)

    def compute_outgoing_messages(self, damping: float = 0.0, relay_memory_term: float = 0.0) -> Dict[int, float]:
        """Compute outgoing messages to every adjacent check node.

        The message to one check excludes the message that came from that same
        check. Damping is applied as a simple baseline stabilization mechanism.
        The relay_memory_term is included so the decoder can later be extended
        into Relay-BP without changing the node API.
        """
        self.compute_belief(relay_memory_term=relay_memory_term)
        outgoing: Dict[int, float] = {}
        for check_index in self.connected_checks:
            excluded_sum = self.prior_llr + sum(
                message for neighbor_check, message in self.incoming_messages.items() if neighbor_check != check_index
            )
            message = excluded_sum + relay_memory_term
            if damping != 0.0:
                previous = self.outgoing_messages[check_index]
                message = (1.0 - damping) * message + damping * previous
            self.outgoing_messages[check_index] = float(message)
            outgoing[check_index] = float(message)
        return outgoing


class CheckNode:
    """Stateful check-node object used by the BP decoder.

    Each check node gathers messages from connected variable nodes and returns
    updated messages based on the parity constraint. The baseline decoder uses
    a min-sum update rule because it is straightforward to implement and easy
    to extend later for Relay-style experiments.
    """

    def __init__(self, index: int, connected_variables: Sequence[int]):
        self.index = index
        self.connected_variables = list(connected_variables)
        self.incoming_messages: Dict[int, float] = {variable_index: 0.0 for variable_index in self.connected_variables}
        self.outgoing_messages: Dict[int, float] = {variable_index: 0.0 for variable_index in self.connected_variables}

    def reset(self) -> None:
        """Clear all stored messages before a new decode attempt."""
        for variable_index in self.connected_variables:
            self.incoming_messages[variable_index] = 0.0
            self.outgoing_messages[variable_index] = 0.0

    def update_incoming(self, variable_index: int, message: float) -> None:
        """Store a message received from one adjacent variable node."""
        self.incoming_messages[variable_index] = float(message)

    def compute_outgoing_messages(self, syndrome_bit: int) -> Dict[int, float]:
        """Compute check-to-variable messages using a min-sum style rule."""
        outgoing: Dict[int, float] = {}
        syndrome_sign = -1 if syndrome_bit else 1

        for variable_index in self.connected_variables:
            incoming = [
                message for neighbor_variable, message in self.incoming_messages.items() if neighbor_variable != variable_index
            ]
            if not incoming:
                outgoing[variable_index] = 0.0
                self.outgoing_messages[variable_index] = 0.0
                continue

            sign_product = 1
            for message in incoming:
                sign_product *= 1 if message >= 0 else -1
            magnitude = min(abs(message) for message in incoming)
            message = syndrome_sign * sign_product * magnitude
            self.outgoing_messages[variable_index] = float(message)
            outgoing[variable_index] = float(message)

        return outgoing


# ---------------------------------------------------------------------------
# BP decoder
# ---------------------------------------------------------------------------


class BPDecoder:
    """Binary BP decoder with explicit node objects and a relay-ready hook.

    The decoder performs iterative message passing between variable and check
    nodes, computes the syndrome after every iteration, and stops when the
    syndrome becomes zero or the iteration limit is reached. The protected
    method `_relay_memory_term` is intentionally isolated so that a future
    Relay-BP extension can add memory without restructuring the decoding loop.
    """

    def __init__(self, parity_check_matrix: ParityCheckMatrix, config: BPConfig | None = None, seed: int = 0):
        self.matrix = parity_check_matrix
        self.config = config or BPConfig()
        self.rng = np.random.default_rng(seed)
        self.variable_nodes: list[VariableNode] = []
        self.check_nodes: list[CheckNode] = []
        self._build_nodes()

    def _build_nodes(self) -> None:
        """Build node objects from the parity-check matrix connectivity."""
        self.variable_nodes = [
            VariableNode(index=variable_index, connected_checks=self.matrix.variable_to_checks[variable_index], prior_llr=0.0)
            for variable_index in range(self.matrix.n_variables)
        ]
        self.check_nodes = [
            CheckNode(index=check_index, connected_variables=self.matrix.check_to_variables[check_index])
            for check_index in range(self.matrix.n_checks)
        ]

    def _relay_memory_term(self, variable_node: VariableNode, iteration_index: int) -> float:
        """Relay-memory hook reserved for later extension.

        The baseline decoder returns zero here. A Relay-BP subclass or a future
        variant can override this method to inject iteration-dependent memory,
        schedule-dependent weighting, or other trajectory state.
        """
        return 0.0

    def _initialize_state(self, prior_llr: np.ndarray) -> None:
        """Reset node state for a new decode attempt."""
        if prior_llr.shape != (self.matrix.n_variables,):
            raise ValueError(f"prior_llr must have shape {(self.matrix.n_variables,)}, got {prior_llr.shape}")

        for variable_node, llr in zip(self.variable_nodes, prior_llr):
            variable_node.reset(float(llr))
        for check_node in self.check_nodes:
            check_node.reset()

    def _propagate_variable_to_check(self, iteration_index: int) -> None:
        """Push variable-node messages toward adjacent check nodes."""
        for variable_node in self.variable_nodes:
            relay_memory_term = self._relay_memory_term(variable_node, iteration_index)
            outgoing_messages = variable_node.compute_outgoing_messages(
                damping=self.config.damping,
                relay_memory_term=relay_memory_term,
            )
            for check_index, message in outgoing_messages.items():
                self.check_nodes[check_index].update_incoming(variable_node.index, message)

    def _propagate_check_to_variable(self, syndrome: np.ndarray) -> None:
        """Push check-node messages back to adjacent variable nodes."""
        for check_node in self.check_nodes:
            outgoing_messages = check_node.compute_outgoing_messages(int(syndrome[check_node.index]))
            for variable_index, message in outgoing_messages.items():
                self.variable_nodes[variable_index].update_incoming(check_node.index, message)

    def _hard_decision(self) -> np.ndarray:
        """Form the current hard decision from all variable-node beliefs."""
        return np.array([node.hard_decision() for node in self.variable_nodes], dtype=np.uint8)

    def _compute_syndrome(self, decoded_error: np.ndarray) -> np.ndarray:
        """Compute the syndrome after an iteration using the parity-check matrix."""
        return self.matrix.syndrome(decoded_error)

    def decode(self, prior_llr: np.ndarray, syndrome: np.ndarray) -> DecodeResult:
        """Run BP until convergence or until the maximum iteration count is reached."""
        if syndrome.shape != (self.matrix.n_checks,):
            raise ValueError(f"syndrome must have shape {(self.matrix.n_checks,)}, got {syndrome.shape}")

        self._initialize_state(prior_llr)

        start_time = perf_counter()
        current_syndrome = syndrome.astype(np.uint8).copy()
        decoded_error = self._hard_decision()
        iterations = 0

        for iteration_index in range(self.config.max_iterations):
            self._propagate_variable_to_check(iteration_index)
            self._propagate_check_to_variable(current_syndrome)

            decoded_error = self._hard_decision()
            current_syndrome = self._compute_syndrome(decoded_error)
            iterations = iteration_index + 1

            if np.all(current_syndrome == 0):
                break

        latency_seconds = perf_counter() - start_time
        return DecodeResult(
            converged=bool(np.all(current_syndrome == 0)),
            iterations=iterations,
            latency_seconds=latency_seconds,
            final_syndrome=current_syndrome,
            decoded_error=decoded_error,
        )


# ---------------------------------------------------------------------------
# Simple synthetic example helpers
# ---------------------------------------------------------------------------


def generate_syndrome(prior_llr: np.ndarray, parity_check_matrix: ParityCheckMatrix, error_rate: float, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Generate a synthetic binary error pattern and its noisy prior LLR vector.

    This helper is intended for quick experimentation and documentation. It is
    not required by the decoder itself, but it makes the module immediately
    usable for standalone testing.
    """
    rng = np.random.default_rng(seed)
    error_vector = (rng.random(parity_check_matrix.n_variables) < error_rate).astype(np.uint8)
    syndrome = parity_check_matrix.syndrome(error_vector)
    noisy_prior = prior_llr.astype(float) + rng.normal(0.0, 0.5, size=prior_llr.shape)
    return syndrome, noisy_prior


def build_example_matrix() -> ParityCheckMatrix:
    """Build a small example parity-check matrix for quick testing."""
    return ParityCheckMatrix.from_dense(
        [
            [1, 1, 0, 1, 0, 0],
            [0, 1, 1, 0, 1, 0],
            [1, 0, 1, 0, 0, 1],
        ]
    )


def main() -> None:
    """Run a small demonstration of the BP framework."""
    matrix = build_example_matrix()
    decoder = BPDecoder(matrix, BPConfig(max_iterations=20, damping=0.1), seed=7)

    prior_llr = np.array([1.2, -0.8, 0.7, 1.1, -1.0, 0.6], dtype=float)
    syndrome, noisy_prior = generate_syndrome(prior_llr, matrix, error_rate=0.15, seed=21)
    result = decoder.decode(noisy_prior, syndrome)

    print("Binary BP decode result")
    print("-" * 30)
    print(f"Converged:      {result.converged}")
    print(f"Iterations:     {result.iterations}")
    print(f"Latency:        {result.latency_seconds * 1e3:.3f} ms")
    print(f"Final syndrome: {result.final_syndrome.tolist()}")
    print(f"Decoded error:   {result.decoded_error.tolist()}")


if __name__ == "__main__":
    main()
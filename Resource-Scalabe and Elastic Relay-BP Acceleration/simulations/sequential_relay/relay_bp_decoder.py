"""
Relay-BP decoder built on top of the Binary BP framework.

This module extends the baseline BPDecoder without rewriting the BP core.
The Relay decoder adds relay-memory state, configurable gamma schedules, and
multiple sequential decoding legs. Between legs, the decoder carries forward
its soft state so that later legs can continue from the trajectory produced
by earlier legs.

The implementation is intentionally modular so the same structure can later
be mapped to FPGA lanes, local memories, and leg-control logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Sequence

import numpy as np

import sys


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from binary_bp_framework import (  # type: ignore  # noqa: E402
    BPConfig,
    BPDecoder,
    DecodeResult,
    ParityCheckMatrix,
    VariableNode,
    build_example_matrix,
)


# ---------------------------------------------------------------------------
# Relay-specific configuration and results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelayLegConfig:
    """Configuration for one Relay decoding leg.

    Each leg can use its own gamma schedule. The schedule is applied during
    the leg's iterations and can be used to bias the trajectory toward a new
    convergence path.
    """

    gamma_schedule: Sequence[float]
    carry_gamma: float = 0.5


@dataclass(frozen=True)
class RelayDecoderConfig:
    """Top-level configuration for the sequential Relay-BP decoder."""

    leg_configs: Sequence[RelayLegConfig]
    max_iterations_per_leg: int = 20
    damping: float = 0.0


@dataclass(frozen=True)
class RelayLegResult:
    """Metrics collected for one Relay decoding leg."""

    leg_index: int
    iterations: int
    converged: bool
    latency_seconds: float
    final_syndrome: np.ndarray
    decoded_error: np.ndarray
    relay_memory_snapshot: np.ndarray


@dataclass(frozen=True)
class RelayDecodeResult:
    """Summary of a full multi-leg Relay decode attempt."""

    relay_legs: int
    total_iterations: int
    converged: bool
    latency_seconds: float
    final_syndrome: np.ndarray
    decoded_error: np.ndarray
    leg_results: list[RelayLegResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Relay decoder
# ---------------------------------------------------------------------------


class RelayBPDecoder(BPDecoder):
    """Relay-BP decoder implemented as a subclass of the BP decoder.

    The class reuses the BP node graph and message passing machinery from the
    baseline framework, but adds relay-memory variables and leg scheduling.
    Multiple legs are executed sequentially. If a leg does not converge, the
    decoder carries the current soft state forward into the next leg.
    """

    def __init__(
        self,
        parity_check_matrix: ParityCheckMatrix,
        config: RelayDecoderConfig,
        seed: int = 0,
    ):
        """Create a Relay decoder on top of the baseline BP node graph."""
        base_config = BPConfig(
            max_iterations=config.max_iterations_per_leg,
            damping=config.damping,
        )
        super().__init__(parity_check_matrix, base_config, seed=seed)
        self.relay_config = config
        self.relay_memory = np.zeros(self.matrix.n_variables, dtype=float)
        self._current_gamma_schedule: list[float] = []
        self._active_leg_index = 0

    def _relay_memory_term(self, variable_node: VariableNode, iteration_index: int) -> float:
        """Return the relay-memory contribution for one variable node.

        The base BP decoder returns zero here. Relay-BP uses the stored memory
        vector so that each variable node can retain a soft-state hint from a
        previous leg or iteration.
        """
        return float(self.relay_memory[variable_node.index])

    def _initialize_relay_state(self, prior_llr: np.ndarray) -> None:
        """Initialize the BP state and clear any stale relay memory."""
        self._initialize_state(prior_llr)
        self.relay_memory = np.zeros(self.matrix.n_variables, dtype=float)

    def _gamma_for_iteration(self, iteration_index: int, leg_config: RelayLegConfig) -> float:
        """Return the gamma value for one iteration of a specific leg."""
        if not leg_config.gamma_schedule:
            return 0.0
        return float(leg_config.gamma_schedule[min(iteration_index, len(leg_config.gamma_schedule) - 1)])

    def _propagate_variable_to_check_with_leg(self, iteration_index: int, leg_config: RelayLegConfig) -> None:
        """Run the variable-to-check message pass for the active leg."""
        for variable_node in self.variable_nodes:
            relay_memory_term = self._relay_memory_term(variable_node, iteration_index)
            gamma_value = self._gamma_for_iteration(iteration_index, leg_config)

            # Relay-memory is blended into the effective prior so the leg can
            # continue from the previous trajectory rather than restarting.
            previous_belief = variable_node.belief
            effective_memory = relay_memory_term * gamma_value
            outgoing_messages = variable_node.compute_outgoing_messages(
                damping=self.config.damping,
                relay_memory_term=effective_memory,
            )
            variable_node.belief = previous_belief

            for check_index, message in outgoing_messages.items():
                self.check_nodes[check_index].update_incoming(variable_node.index, message)

    def _update_relay_memory(self, leg_config: RelayLegConfig) -> None:
        """Carry the current soft state forward into the next Relay leg."""
        current_beliefs = np.array([node.belief for node in self.variable_nodes], dtype=float)
        current_decision = np.array([node.hard_decision() for node in self.variable_nodes], dtype=float)

        # The memory vector stores a soft trace of the current state. The
        # carry_gamma parameter controls how much of the previous memory is
        # retained versus how strongly the current leg overwrites it.
        self.relay_memory = (
            leg_config.carry_gamma * self.relay_memory
            + (1.0 - leg_config.carry_gamma) * (current_beliefs - 2.0 * current_decision)
        )

        # Feed the updated soft state back into the variable-node priors so the
        # next leg starts from the Relay trajectory rather than a cold restart.
        for node, memory_value in zip(self.variable_nodes, self.relay_memory):
            node.prior_llr = float(node.belief + memory_value)

    def _run_single_leg(self, prior_syndrome: np.ndarray, leg_index: int, leg_config: RelayLegConfig) -> RelayLegResult:
        """Execute one Relay decoding leg using the current internal state."""
        start_time = perf_counter()
        self._active_leg_index = leg_index
        self._current_gamma_schedule = list(leg_config.gamma_schedule)

        decoded_error = self._hard_decision()
        current_syndrome = self._compute_syndrome(decoded_error)
        iterations = 0

        for iteration_index in range(self.relay_config.max_iterations_per_leg):
            self._propagate_variable_to_check_with_leg(iteration_index, leg_config)
            self._propagate_check_to_variable(prior_syndrome)

            decoded_error = self._hard_decision()
            current_syndrome = self._compute_syndrome(decoded_error)
            iterations = iteration_index + 1

            if np.all(current_syndrome == 0):
                break

        latency_seconds = perf_counter() - start_time
        converged = bool(np.all(current_syndrome == 0))
        relay_memory_snapshot = self.relay_memory.copy()

        return RelayLegResult(
            leg_index=leg_index,
            iterations=iterations,
            converged=converged,
            latency_seconds=latency_seconds,
            final_syndrome=current_syndrome,
            decoded_error=decoded_error,
            relay_memory_snapshot=relay_memory_snapshot,
        )

    def decode(self, prior_llr: np.ndarray, syndrome: np.ndarray) -> RelayDecodeResult:
        """Run all Relay legs sequentially and return the first successful result."""
        if syndrome.shape != (self.matrix.n_checks,):
            raise ValueError(f"syndrome must have shape {(self.matrix.n_checks,)}, got {syndrome.shape}")

        self._initialize_relay_state(prior_llr)

        start_time = perf_counter()
        leg_results: list[RelayLegResult] = []
        total_iterations = 0
        converged = False
        final_syndrome = syndrome.astype(np.uint8).copy()
        decoded_error = np.zeros(self.matrix.n_variables, dtype=np.uint8)

        for leg_index, leg_config in enumerate(self.relay_config.leg_configs):
            leg_result = self._run_single_leg(syndrome, leg_index, leg_config)
            leg_results.append(leg_result)
            total_iterations += leg_result.iterations
            final_syndrome = leg_result.final_syndrome
            decoded_error = leg_result.decoded_error

            if leg_result.converged:
                converged = True
                break

            # Carry the state into the next leg only when the current leg has
            # not converged. This mirrors the Relay idea of reusing soft state
            # across sequential decoding legs.
            self._update_relay_memory(leg_config)

        latency_seconds = perf_counter() - start_time
        return RelayDecodeResult(
            relay_legs=len(leg_results),
            total_iterations=total_iterations,
            converged=converged,
            latency_seconds=latency_seconds,
            final_syndrome=final_syndrome,
            decoded_error=decoded_error,
            leg_results=leg_results,
        )


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------


def main() -> None:
    """Run a small Relay-BP demonstration from the command line."""
    matrix = build_example_matrix()
    config = RelayDecoderConfig(
        leg_configs=[
            RelayLegConfig(gamma_schedule=[0.05, 0.10, 0.15, 0.20], carry_gamma=0.40),
            RelayLegConfig(gamma_schedule=[0.20, 0.25, 0.30, 0.35], carry_gamma=0.55),
            RelayLegConfig(gamma_schedule=[0.35, 0.40, 0.45, 0.50], carry_gamma=0.65),
        ],
        max_iterations_per_leg=15,
        damping=0.05,
    )

    decoder = RelayBPDecoder(matrix, config, seed=7)
    prior_llr = np.array([1.2, -0.8, 0.7, 1.1, -1.0, 0.6], dtype=float)
    syndrome = matrix.syndrome(np.array([0, 1, 0, 0, 1, 0], dtype=np.uint8))
    result = decoder.decode(prior_llr, syndrome)

    print("Relay-BP decode result")
    print("-" * 30)
    print(f"Relay legs:      {result.relay_legs}")
    print(f"Converged:       {result.converged}")
    print(f"Iterations:      {result.total_iterations}")
    print(f"Latency:         {result.latency_seconds * 1e3:.3f} ms")
    print(f"Final syndrome:  {result.final_syndrome.tolist()}")
    print(f"Decoded error:    {result.decoded_error.tolist()}")

    for leg_result in result.leg_results:
        print(
            f"  leg {leg_result.leg_index}: converged={leg_result.converged} "
            f"iters={leg_result.iterations} latency={leg_result.latency_seconds * 1e3:.3f} ms"
        )


if __name__ == "__main__":
    main()
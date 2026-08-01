"""Shared Relay-BP reference implementation for float, integer, and fixed-point modes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from math import floor
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from configs.manifest import ManifestConfig, write_manifest
from fixedpoint import FixedConfig, beta_to_int, check_node_update, memory_mix, round_div, sat_b
from graph_loader import GraphPackage, load_graph_package


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GRAPH_PACKAGE = PROJECT_ROOT / "graphs" / "generated" / "gross_code_capacity" / "package.json"


@dataclass(frozen=True)
class RelayLegConfig:
    gamma_schedule: tuple[float, ...]
    carry_gamma: float = 0.5


@dataclass(frozen=True)
class RelayRuntimeConfig:
    leg_configs: tuple[RelayLegConfig, ...]
    max_iterations_per_leg: int = 10
    gamma_scale: int = 16
    trace_messages: bool = False


@dataclass(frozen=True)
class RelayReplayCase:
    graph_package: str
    syndrome: list[int]
    prior: list[float | int]
    seed: int | None = None
    note: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"


@dataclass(frozen=True)
class RelayTraceRecord:
    phase: str
    leg_index: int
    iteration: int | None
    gamma: float | int
    beliefs: list[float | int]
    relay_memory: list[float | int]
    decoded_error: list[int]
    residual: list[int]
    residual_score: int
    converged: bool
    message_summary: dict[str, int] = field(default_factory=dict)
    var_to_check: list[list[float | int]] | None = None
    check_to_var: list[list[float | int]] | None = None


@dataclass(frozen=True)
class RelayDecodeResult:
    converged: bool
    total_iterations: int
    relay_legs: int
    decoded_error: np.ndarray
    final_syndrome: np.ndarray
    beliefs: np.ndarray
    relay_memory: np.ndarray
    trace: list[RelayTraceRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decoded_error"] = self.decoded_error.tolist()
        data["final_syndrome"] = self.final_syndrome.tolist()
        data["beliefs"] = self.beliefs.tolist()
        data["relay_memory"] = self.relay_memory.tolist()
        return data

    def write_trace(self, path: Path) -> Path:
        path.write_text(json.dumps(self.to_json_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


def load_replay_case(path: Path) -> RelayReplayCase:
    data = json.loads(path.read_text(encoding="utf-8"))
    return RelayReplayCase(
        graph_package=str(data["graph_package"]),
        syndrome=[int(value) for value in data["syndrome"]],
        prior=list(data["prior"]),
        seed=data.get("seed"),
        note=str(data.get("note", "")),
    )


def write_replay_case(case: RelayReplayCase, path: Path) -> Path:
    path.write_text(case.to_json(), encoding="utf-8")
    return path


def save_trace_manifest(out_dir: Path, records: list[RelayTraceRecord], artifact_paths: Sequence[Path], notes: list[str]) -> Path:
    return write_manifest(
        ManifestConfig(
            experiment={"purpose": "Relay-BP reference trace"},
            notes=notes,
        ),
        out_dir,
        artifact_paths=artifact_paths,
    )


def _as_graph_package(graph: GraphPackage | np.ndarray | Path | str) -> GraphPackage:
    if isinstance(graph, GraphPackage):
        return graph
    if isinstance(graph, (Path, str)):
        return load_graph_package(Path(graph))
    h_matrix = np.asarray(graph, dtype=np.uint8)
    return GraphPackage(h_matrix=h_matrix, priors=np.zeros(h_matrix.shape[1], dtype=float), metadata={})


def _zero_matrix(rows: int, cols: int, value: float | int) -> list[list[float | int]]:
    return [[value for _ in range(cols)] for _ in range(rows)]


def _round_ties_away_from_zero(value: float) -> int:
    sign = -1 if value < 0 else 1
    return sign * int(floor(abs(float(value)) + 0.5))


def _trace_record(
    *,
    phase: str,
    leg_index: int,
    iteration: int | None,
    gamma: float | int,
    beliefs: Sequence[float | int],
    relay_memory: Sequence[float | int],
    decoded_error: np.ndarray,
    residual: np.ndarray,
    converged: bool,
    message_summary: dict[str, int],
    var_to_check: list[list[float | int]] | None,
    check_to_var: list[list[float | int]] | None,
) -> RelayTraceRecord:
    return RelayTraceRecord(
        phase=phase,
        leg_index=leg_index,
        iteration=iteration,
        gamma=gamma,
        beliefs=[value for value in beliefs],
        relay_memory=[value for value in relay_memory],
        decoded_error=decoded_error.astype(int).tolist(),
        residual=residual.astype(int).tolist(),
        residual_score=int(residual.sum()),
        converged=converged,
        message_summary=message_summary,
        var_to_check=[[value for value in row] for row in var_to_check] if var_to_check is not None else None,
        check_to_var=[[value for value in row] for row in check_to_var] if check_to_var is not None else None,
    )


class _FloatOps:
    def zero(self) -> float:
        return 0.0

    def coerce_prior(self, value: float | int) -> float:
        return float(value)

    def coerce_gamma(self, gamma: float, gamma_scale: int) -> float:
        return float(gamma)

    def relay_term(self, memory_value: float, gamma_value: float, gamma_scale: int) -> float:
        return float(memory_value) * float(gamma_value)

    def belief(self, prior: float, incoming: Sequence[float], relay_term: float) -> float:
        return float(prior) + float(relay_term) + sum(float(value) for value in incoming)

    def outgoing_message(self, belief: float, previous_check_message: float) -> float:
        return float(belief) - float(previous_check_message)

    def check_node_update(self, incoming: Sequence[float], syndrome_bit: int) -> list[float]:
        syndrome_sign = -1.0 if syndrome_bit else 1.0
        outgoing: list[float] = []
        for edge_index in range(len(incoming)):
            others = [float(value) for idx, value in enumerate(incoming) if idx != edge_index]
            if not others:
                outgoing.append(0.0)
                continue
            sign = syndrome_sign
            for value in others:
                if value < 0:
                    sign *= -1.0
            magnitude = min(abs(value) for value in others)
            outgoing.append(sign * magnitude)
        return outgoing

    def carry_gamma(self, gamma: float, gamma_scale: int) -> float:
        return float(gamma)

    def memory_mix(self, y_prev: float, y_new: float, beta_value: float, beta_scale: int) -> float:
        return float(beta_value) * float(y_prev) + (1.0 - float(beta_value)) * float(y_new)

    def decision(self, belief: float) -> int:
        return int(float(belief) < 0.0)

    def residual(self, h_matrix: np.ndarray, decoded: np.ndarray, syndrome: np.ndarray) -> np.ndarray:
        return ((h_matrix @ decoded) % 2) ^ syndrome

    def prior_next_leg(self, belief: float, relay_memory: float) -> float:
        return float(belief) + float(relay_memory)


class _IntegerOps:
    def __init__(self, scale: int = 1 << 20):
        self.scale = scale

    def zero(self) -> int:
        return 0

    def coerce_prior(self, value: float | int) -> int:
        if isinstance(value, (int, np.integer)):
            return int(value)
        return _round_ties_away_from_zero(float(value) * self.scale)

    def coerce_gamma(self, gamma: float, gamma_scale: int) -> int:
        return _round_ties_away_from_zero(float(gamma) * gamma_scale)

    def relay_term(self, memory_value: int, gamma_value: int, gamma_scale: int) -> int:
        return round_div(int(memory_value) * int(gamma_value), gamma_scale)

    def belief(self, prior: int, incoming: Sequence[int], relay_term: int) -> int:
        return int(prior) + int(relay_term) + sum(int(value) for value in incoming)

    def outgoing_message(self, belief: int, previous_check_message: int) -> int:
        return int(belief) - int(previous_check_message)

    def check_node_update(self, incoming: Sequence[int], syndrome_bit: int) -> list[int]:
        syndrome_sign = -1 if syndrome_bit else 1
        outgoing: list[int] = []
        for edge_index in range(len(incoming)):
            others = [int(value) for idx, value in enumerate(incoming) if idx != edge_index]
            if not others:
                outgoing.append(0)
                continue
            sign = syndrome_sign
            for value in others:
                if value < 0:
                    sign *= -1
            magnitude = min(abs(value) for value in others)
            outgoing.append(sign * magnitude)
        return outgoing

    def carry_gamma(self, gamma: float, gamma_scale: int) -> int:
        return _round_ties_away_from_zero(float(gamma) * gamma_scale)

    def memory_mix(self, y_prev: int, y_new: int, beta_value: int, beta_scale: int) -> int:
        numerator = int(beta_value) * int(y_prev) + (int(beta_scale) - int(beta_value)) * int(y_new)
        return round_div(numerator, beta_scale)

    def decision(self, belief: int) -> int:
        return int(int(belief) < 0)

    def residual(self, h_matrix: np.ndarray, decoded: np.ndarray, syndrome: np.ndarray) -> np.ndarray:
        return ((h_matrix @ decoded) % 2) ^ syndrome

    def prior_next_leg(self, belief: int, relay_memory: int) -> int:
        return int(belief) + int(relay_memory)


class _FixedPointOps:
    def __init__(self, config: FixedConfig):
        self.config = config

    def zero(self) -> int:
        return 0

    def coerce_prior(self, value: float | int) -> int:
        if isinstance(value, (int, np.integer)):
            return sat_b(value, self.config)
        return sat_b(_round_ties_away_from_zero(float(value)), self.config)

    def coerce_gamma(self, gamma: float, gamma_scale: int) -> int:
        return beta_to_int(float(gamma), gamma_scale)

    def relay_term(self, memory_value: int, gamma_value: int, gamma_scale: int) -> int:
        return round_div(int(memory_value) * int(gamma_value), gamma_scale)

    def belief(self, prior: int, incoming: Sequence[int], relay_term: int) -> int:
        total = int(prior) + int(relay_term) + sum(int(value) for value in incoming)
        return sat_b(total, self.config)

    def outgoing_message(self, belief: int, previous_check_message: int) -> int:
        return sat_b(int(belief) - int(previous_check_message), self.config)

    def check_node_update(self, incoming: Sequence[int], syndrome_bit: int) -> list[int]:
        return check_node_update(incoming, syndrome_bit, self.config)

    def carry_gamma(self, gamma: float, gamma_scale: int) -> int:
        return beta_to_int(float(gamma), gamma_scale)

    def memory_mix(self, y_prev: int, y_new: int, beta_value: int, beta_scale: int) -> int:
        return memory_mix(int(y_prev), int(y_new), int(beta_value), self.config)

    def decision(self, belief: int) -> int:
        return int(int(belief) < 0)

    def residual(self, h_matrix: np.ndarray, decoded: np.ndarray, syndrome: np.ndarray) -> np.ndarray:
        return ((h_matrix @ decoded) % 2) ^ syndrome

    def prior_next_leg(self, belief: int, relay_memory: int) -> int:
        return sat_b(int(belief) + int(relay_memory), self.config)


def _validate_input_arrays(
    prior: Sequence[float | int],
    syndrome: Sequence[int],
    graph: GraphPackage,
) -> tuple[list[float | int], np.ndarray]:
    h_matrix = graph.h_matrix.astype(np.uint8)
    syndrome_array = np.asarray(syndrome, dtype=np.uint8)
    if syndrome_array.shape != (h_matrix.shape[0],):
        raise ValueError(f"syndrome must have shape {(h_matrix.shape[0],)}, got {syndrome_array.shape}")
    prior_list = list(prior)
    if len(prior_list) != h_matrix.shape[1]:
        raise ValueError(f"prior must have length {h_matrix.shape[1]}, got {len(prior_list)}")
    return prior_list, syndrome_array


def run_relay_decode(
    graph: GraphPackage | np.ndarray | Path | str,
    prior: Sequence[float | int],
    syndrome: Sequence[int],
    config: RelayRuntimeConfig,
    ops: Any,
    *,
    trace_path: Path | None = None,
) -> RelayDecodeResult:
    graph_package = _as_graph_package(graph)
    h_matrix = graph_package.h_matrix.astype(np.uint8)
    prior_list, syndrome_array = _validate_input_arrays(prior, syndrome, graph_package)

    check_to_vars = [list(np.flatnonzero(row)) for row in h_matrix]
    var_to_checks = [list(np.flatnonzero(h_matrix[:, col])) for col in range(h_matrix.shape[1])]

    prior_state = [ops.coerce_prior(value) for value in prior_list]
    relay_memory = [ops.zero() for _ in range(h_matrix.shape[1])]
    beliefs = prior_state.copy()
    check_to_var = _zero_matrix(h_matrix.shape[0], h_matrix.shape[1], ops.zero())
    var_to_check = _zero_matrix(h_matrix.shape[0], h_matrix.shape[1], ops.zero())

    total_iterations = 0
    relay_legs = 0
    decoded_error = np.zeros(h_matrix.shape[1], dtype=np.uint8)
    final_syndrome = syndrome_array.copy()
    trace: list[RelayTraceRecord] = []
    converged = False

    for leg_index, leg_config in enumerate(config.leg_configs):
        relay_legs = leg_index + 1
        for iteration in range(config.max_iterations_per_leg):
            gamma = leg_config.gamma_schedule[min(iteration, len(leg_config.gamma_schedule) - 1)] if leg_config.gamma_schedule else 0.0
            gamma_value = ops.coerce_gamma(gamma, config.gamma_scale)

            for variable in range(h_matrix.shape[1]):
                incoming = [check_to_var[check][variable] for check in var_to_checks[variable]]
                relay_term = ops.relay_term(relay_memory[variable], gamma_value, config.gamma_scale)
                beliefs[variable] = ops.belief(prior_state[variable], incoming, relay_term)
                for check in var_to_checks[variable]:
                    var_to_check[check][variable] = ops.outgoing_message(beliefs[variable], check_to_var[check][variable])

            for check, variables in enumerate(check_to_vars):
                incoming = [var_to_check[check][variable] for variable in variables]
                outgoing = ops.check_node_update(incoming, int(syndrome_array[check]))
                for variable, message in zip(variables, outgoing):
                    check_to_var[check][variable] = message

            decoded_error = np.asarray([ops.decision(value) for value in beliefs], dtype=np.uint8)
            final_syndrome = ops.residual(h_matrix, decoded_error, syndrome_array)
            total_iterations += 1

            trace.append(
                _trace_record(
                    phase="iteration",
                    leg_index=leg_index,
                    iteration=iteration,
                    gamma=gamma_value,
                    beliefs=beliefs,
                    relay_memory=relay_memory,
                    decoded_error=decoded_error,
                    residual=final_syndrome,
                    converged=bool(not final_syndrome.any()),
                    message_summary={"variables": h_matrix.shape[1], "checks": h_matrix.shape[0], "edges": int(h_matrix.sum())},
                    var_to_check=var_to_check if config.trace_messages else None,
                    check_to_var=check_to_var if config.trace_messages else None,
                )
            )

            if not final_syndrome.any():
                converged = True
                break

        if converged:
            break

        beta_value = ops.carry_gamma(leg_config.carry_gamma, config.gamma_scale)
        for variable in range(h_matrix.shape[1]):
            y_new = beliefs[variable] - 2 * int(decoded_error[variable])
            relay_memory[variable] = ops.memory_mix(relay_memory[variable], y_new, beta_value, config.gamma_scale)
            prior_state[variable] = ops.prior_next_leg(beliefs[variable], relay_memory[variable])

        trace.append(
            _trace_record(
                phase="leg_update",
                leg_index=leg_index,
                iteration=None,
                gamma=beta_value,
                beliefs=beliefs,
                relay_memory=relay_memory,
                decoded_error=decoded_error,
                residual=final_syndrome,
                converged=False,
                message_summary={"variables": h_matrix.shape[1], "checks": h_matrix.shape[0], "edges": int(h_matrix.sum())},
                var_to_check=None,
                check_to_var=None,
            )
        )

    result = RelayDecodeResult(
        converged=converged,
        total_iterations=total_iterations,
        relay_legs=relay_legs,
        decoded_error=decoded_error,
        final_syndrome=final_syndrome,
        beliefs=np.asarray(beliefs),
        relay_memory=np.asarray(relay_memory),
        trace=trace,
        metadata={
            "graph_hash": graph_package.metadata.get("source_graph_hash"),
            "graph_tier": graph_package.metadata.get("tier"),
            "leg_configs": [asdict(leg) for leg in config.leg_configs],
            "max_iterations_per_leg": config.max_iterations_per_leg,
            "gamma_scale": config.gamma_scale,
            "trace_messages": config.trace_messages,
        },
    )
    if trace_path is not None:
        trace_path.write_text(json.dumps(result.to_json_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


class FloatRelayBPDecoder:
    """Deterministic floating-point Relay-BP reference."""

    def __init__(
        self,
        graph: GraphPackage | np.ndarray | Path | str,
        max_iterations: int = 3,
        gamma: float = 0.25,
        leg_configs: Sequence[RelayLegConfig] | None = None,
        trace_messages: bool = False,
    ):
        self.graph = _as_graph_package(graph)
        if leg_configs is None:
            leg_configs = (RelayLegConfig(tuple([float(gamma)] * max_iterations), carry_gamma=0.5),)
        self.config = RelayRuntimeConfig(
            leg_configs=tuple(leg_configs),
            max_iterations_per_leg=max_iterations,
            gamma_scale=16,
            trace_messages=trace_messages,
        )
        self.ops = _FloatOps()

    @classmethod
    def from_package(
        cls,
        package_path: Path | str,
        *,
        max_iterations: int = 3,
        gamma: float = 0.25,
        leg_configs: Sequence[RelayLegConfig] | None = None,
        trace_messages: bool = False,
    ) -> "FloatRelayBPDecoder":
        return cls(Path(package_path), max_iterations=max_iterations, gamma=gamma, leg_configs=leg_configs, trace_messages=trace_messages)

    def decode(self, prior: Sequence[float | int], syndrome: Sequence[int], trace_path: Path | None = None) -> RelayDecodeResult:
        return run_relay_decode(self.graph, prior, syndrome, self.config, self.ops, trace_path=trace_path)


class HighPrecisionRelayBPDecoder:
    """Deterministic high-precision integer Relay-BP reference."""

    def __init__(
        self,
        graph: GraphPackage | np.ndarray | Path | str,
        scale: int = 1 << 20,
        max_iterations: int = 3,
        gamma: float = 0.25,
        leg_configs: Sequence[RelayLegConfig] | None = None,
        trace_messages: bool = False,
    ):
        self.graph = _as_graph_package(graph)
        if leg_configs is None:
            leg_configs = (RelayLegConfig(tuple([float(gamma)] * max_iterations), carry_gamma=0.5),)
        self.config = RelayRuntimeConfig(
            leg_configs=tuple(leg_configs),
            max_iterations_per_leg=max_iterations,
            gamma_scale=scale,
            trace_messages=trace_messages,
        )
        self.ops = _IntegerOps(scale=scale)

    def decode(self, prior: Sequence[float | int], syndrome: Sequence[int], trace_path: Path | None = None) -> RelayDecodeResult:
        return run_relay_decode(self.graph, prior, syndrome, self.config, self.ops, trace_path=trace_path)


class FixedPointRelayBPDecoder:
    """Shared fixed-point Relay-BP reference that supports separate-M mode."""

    def __init__(
        self,
        graph: GraphPackage | np.ndarray | Path | str,
        fixed: FixedConfig,
        leg_configs: Sequence[RelayLegConfig],
        max_iterations_per_leg: int,
        gamma_scale: int = 16,
        trace_messages: bool = False,
    ):
        self.graph = _as_graph_package(graph)
        self.fixed = fixed
        self.config = RelayRuntimeConfig(
            leg_configs=tuple(leg_configs),
            max_iterations_per_leg=max_iterations_per_leg,
            gamma_scale=gamma_scale,
            trace_messages=trace_messages,
        )
        self.ops = _FixedPointOps(fixed)

    def decode(self, prior: Sequence[float | int], syndrome: Sequence[int], trace_path: Path | None = None) -> RelayDecodeResult:
        return run_relay_decode(self.graph, prior, syndrome, self.config, self.ops, trace_path=trace_path)


def default_tier1_package_path() -> Path:
    return DEFAULT_GRAPH_PACKAGE

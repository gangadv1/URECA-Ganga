"""Directed tests for the fixed-point arithmetic."""

from __future__ import annotations

import json
import random
from pathlib import Path
import sys

import numpy as np

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
for path in (CURRENT_DIR, PROJECT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from fixedpoint import (
    FixedConfig,
    beta_to_int,
    check_node_update,
    clip_to_bounds,
    memory_mix,
    round_div_power_of_two,
    sat_b,
    saturate_value,
    scale_beta,
    signed_add,
    signed_mul,
    signed_sub,
    widened_product,
    widened_sum,
)
from graph_loader import load_graph_package
from relay_bp_fixed import FixedRelayBPDecoder, FixedRelayConfig, FixedRelayLegConfig
from relay_bp_float import FloatRelayBPDecoder
from relay_reference import HighPrecisionRelayBPDecoder


def test_saturation_endpoints() -> None:
    config = FixedConfig(b=4, g=2, M=8, clip=6)
    assert sat_b(100, config) == 6
    assert sat_b(-100, config) == -6
    assert sat_b(3, config) == 3


def test_rounding_ties_away_from_zero() -> None:
    assert round_div_power_of_two(1, 1) == 1
    assert round_div_power_of_two(-1, 1) == -1
    assert round_div_power_of_two(5, 1) == 3
    assert round_div_power_of_two(-5, 1) == -3


def test_beta_to_int() -> None:
    assert beta_to_int(0.0, 8) == 0
    assert beta_to_int(1.0, 8) == 8
    assert beta_to_int(0.5, 8) == 4


def test_memory_mix_endpoints_and_middle() -> None:
    config = FixedConfig(b=4, g=2, M=8, clip=7)
    assert memory_mix(y_prev=3, y_new=-5, beta_int=0, config=config) == -5
    assert memory_mix(y_prev=3, y_new=-5, beta_int=8, config=config) == 3
    assert memory_mix(y_prev=3, y_new=-5, beta_int=4, config=config) == -1


def test_memory_mix_saturates() -> None:
    config = FixedConfig(b=4, g=2, M=8, clip=6)
    assert memory_mix(y_prev=20, y_new=20, beta_int=4, config=config) == 6
    assert memory_mix(y_prev=-20, y_new=-20, beta_int=4, config=config) == -6


def test_check_node_all_equal() -> None:
    config = FixedConfig(b=5, g=2, M=8, clip=15)
    assert check_node_update([3, -3, 3], 0, config) == [-3, 3, -3]
    assert check_node_update([3, -3, 3], 1, config) == [3, -3, 3]


def test_check_node_smallest_edges() -> None:
    config = FixedConfig(b=5, g=2, M=8, clip=15)
    assert check_node_update([5, -2, 7], 0, config) == [-2, 5, -2]


def test_check_node_zero_magnitude_sign() -> None:
    config = FixedConfig(b=5, g=2, M=8, clip=15)
    assert check_node_update([0, -4, 5], 0, config) == [-4, 0, 0]


def test_shared_scale_control_rounds_coefficient_toward_zero() -> None:
    # A1 control: the separate scale keeps an independent coefficient scale M,
    # so a small memory weight survives; the shared-scale control ties the
    # coefficient to the message scale 2**(b-1), which rounds the same weight to
    # zero at low b and drops the previous memory from the mix.
    beta = 0.05
    separate = FixedConfig(b=4, g=2, M=16, clip=7, separate_scale=True)
    shared = FixedConfig(b=4, g=2, M=16, clip=7, separate_scale=False)
    assert separate.coefficient_M == 16
    assert shared.coefficient_M == 8
    assert beta_to_int(beta, separate.coefficient_M) == 1
    assert beta_to_int(beta, shared.coefficient_M) == 0
    assert memory_mix(y_prev=6, y_new=-6, beta_int=beta_to_int(beta, separate.coefficient_M), config=separate) == -5
    assert memory_mix(y_prev=6, y_new=-6, beta_int=beta_to_int(beta, shared.coefficient_M), config=shared) == -6


def test_v0_primitive_arithmetic_exact_cases() -> None:
    config = FixedConfig(b=4, g=2, M=8, clip=7)
    assert signed_add(3, 4) == 7
    assert signed_add(-3, -4) == -7
    assert signed_sub(3, 4) == -1
    assert signed_sub(-3, -4) == 1
    assert signed_mul(3, -4) == -12
    assert widened_product(-7, 7) == -49
    assert widened_sum([7, -3, -4, 10]) == 10
    assert clip_to_bounds(12, -5, 5) == 5
    assert clip_to_bounds(-12, -5, 5) == -5
    assert sat_b(12, config) == 7
    assert sat_b(-12, config) == -7
    assert saturate_value(6, config) == 6
    assert scale_beta(0.0, 8) == 0
    assert scale_beta(1.0, 8) == 8
    assert scale_beta(0.5, 8) == 4
    assert scale_beta(0.5, 16) == 8


def test_v0_message_and_memory_update_exact_cases() -> None:
    config = FixedConfig(b=4, g=2, M=8, clip=7)
    assert round_div_power_of_two(5, 1) == 3
    assert round_div_power_of_two(-5, 1) == -3
    assert round_div_power_of_two(7, 2) == 2
    assert memory_mix(y_prev=3, y_new=-5, beta_int=0, config=config) == -5
    assert memory_mix(y_prev=3, y_new=-5, beta_int=4, config=config) == -1
    assert memory_mix(y_prev=3, y_new=-5, beta_int=8, config=config) == 3
    assert check_node_update([3, -3, 3], 0, config) == [-3, 3, -3]
    assert check_node_update([0, -4, 5], 0, config) == [-4, 0, 0]


def test_v1_randomized_fixed_point_primitives() -> None:
    rng = random.Random(20260801)
    config = FixedConfig(b=5, g=2, M=8, clip=15)
    for _ in range(64):
        lhs = rng.randint(-20, 20)
        rhs = rng.randint(-20, 20)
        values = [rng.randint(-20, 20) for _ in range(5)]
        assert signed_add(lhs, rhs) == lhs + rhs
        assert signed_sub(lhs, rhs) == lhs - rhs
        assert signed_mul(lhs, rhs) == lhs * rhs
        assert widened_sum(values) == sum(values)
        beta = rng.random()
        beta_scaled = beta_to_int(beta, config.coefficient_M)
        assert scale_beta(beta, config.coefficient_M) == beta_scaled
        assert 0 <= beta_scaled <= config.coefficient_M
        prev = rng.randint(-15, 15)
        new = rng.randint(-15, 15)
        mix = memory_mix(prev, new, beta_scaled, config)
        assert config.min_value <= mix <= config.max_value


def test_float_integer_and_fixed_reference_decode_zero_syndrome() -> None:
    package_path = PROJECT_ROOT / "graphs" / "generated" / "gross_code_capacity" / "package.json"
    graph = load_graph_package(package_path)
    syndrome = np.zeros(graph.h_matrix.shape[0], dtype=np.uint8)
    prior = np.ones(graph.h_matrix.shape[1], dtype=float)

    float_decoder = FloatRelayBPDecoder(graph.h_matrix, max_iterations=3, gamma=0.25)
    float_result = float_decoder.decode(prior, syndrome)
    assert float_result.converged is True
    assert float_result.total_iterations == 1
    assert float_result.relay_legs == 1
    assert np.array_equal(float_result.decoded_error, np.zeros(graph.h_matrix.shape[1], dtype=np.uint8))
    assert np.array_equal(float_result.final_syndrome, syndrome)

    integer_decoder = HighPrecisionRelayBPDecoder(graph.h_matrix, scale=1 << 20, max_iterations=3, gamma=0.25)
    integer_result = integer_decoder.decode(np.ones(graph.h_matrix.shape[1], dtype=int), syndrome)
    assert integer_result.converged is True
    assert integer_result.total_iterations == 1
    assert integer_result.relay_legs == 1
    assert np.array_equal(integer_result.decoded_error, np.zeros(graph.h_matrix.shape[1], dtype=np.uint8))
    assert np.array_equal(integer_result.final_syndrome, syndrome)

    fixed_decoder = FixedRelayBPDecoder(
        graph.h_matrix,
        FixedRelayConfig(
            fixed=FixedConfig(b=4, g=2, M=8, clip=7, separate_scale=True),
            leg_configs=(FixedRelayLegConfig(max_iterations=3, gamma=0.25),),
            S=1,
            R=1,
        ),
    )
    fixed_result = fixed_decoder.decode(np.ones(graph.h_matrix.shape[1], dtype=int), syndrome)
    assert fixed_result.converged is True
    assert fixed_result.total_iterations == 1
    assert fixed_result.relay_legs == 1
    assert np.array_equal(fixed_result.decoded_error, np.zeros(graph.h_matrix.shape[1], dtype=np.uint8))
    assert np.array_equal(fixed_result.final_syndrome, syndrome)


def test_reference_replay_is_deterministic() -> None:
    package_path = PROJECT_ROOT / "graphs" / "generated" / "gross_code_capacity" / "package.json"
    graph = load_graph_package(package_path)
    syndrome = np.zeros(graph.h_matrix.shape[0], dtype=np.uint8)
    prior = np.full(graph.h_matrix.shape[1], 2, dtype=int)
    decoder = FloatRelayBPDecoder(graph.h_matrix, max_iterations=3, gamma=0.25, trace_messages=True)
    first = decoder.decode(prior, syndrome)
    second = decoder.decode(prior, syndrome)
    assert first.to_json_dict() == second.to_json_dict()
    assert first.trace[0].residual_score == 0


def test_decode_trace_can_be_serialized() -> None:
    package_path = PROJECT_ROOT / "graphs" / "generated" / "gross_code_capacity" / "package.json"
    graph = load_graph_package(package_path)
    syndrome = np.zeros(graph.h_matrix.shape[0], dtype=np.uint8)
    prior = np.ones(graph.h_matrix.shape[1], dtype=int)
    trace_path = CURRENT_DIR / "_tmp_reference_trace.json"
    try:
        result = FloatRelayBPDecoder(graph.h_matrix, max_iterations=3, gamma=0.25, trace_messages=True).decode(prior, syndrome, trace_path=trace_path)
        assert trace_path.exists()
        loaded = json.loads(trace_path.read_text(encoding="utf-8"))
        assert loaded["converged"] is True
        assert loaded["total_iterations"] == result.total_iterations
        assert loaded["relay_legs"] == result.relay_legs
    finally:
        if trace_path.exists():
            trace_path.unlink()


def run_all() -> None:
    for name, func in sorted(globals().items()):
        if name.startswith("test_"):
            func()


if __name__ == "__main__":
    run_all()
    print("directed fixed-point tests passed")

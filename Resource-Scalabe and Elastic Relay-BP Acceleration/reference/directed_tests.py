"""Directed tests for the fixed-point arithmetic."""

from __future__ import annotations

from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from fixedpoint import FixedConfig, beta_to_int, check_node_update, memory_mix, round_div_power_of_two, sat_b


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


def run_all() -> None:
    for name, func in sorted(globals().items()):
        if name.startswith("test_"):
            func()


if __name__ == "__main__":
    run_all()
    print("directed fixed-point tests passed")


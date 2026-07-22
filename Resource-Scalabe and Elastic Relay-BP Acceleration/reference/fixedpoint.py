"""Small fixed-point arithmetic helpers."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Sequence


@dataclass(frozen=True)
class FixedConfig:
    b: int = 4
    g: int = 2
    M: int = 8
    clip: int | None = None

    @property
    def min_value(self) -> int:
        base_min = -(1 << (self.b - 1))
        return max(base_min, -self.clip) if self.clip is not None else base_min

    @property
    def max_value(self) -> int:
        base_max = (1 << (self.b - 1)) - 1
        return min(base_max, self.clip) if self.clip is not None else base_max

    @property
    def m_shift(self) -> int:
        if self.M <= 0 or self.M & (self.M - 1):
            raise ValueError("M must be a power of two")
        return self.M.bit_length() - 1


def sat_b(value: int, config: FixedConfig) -> int:
    """Clamp a value into the stored message range."""
    return max(config.min_value, min(config.max_value, int(value)))


def round_div(value: int, denominator: int) -> int:
    """Round `value / denominator` to nearest, ties away from zero."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    sign = -1 if value < 0 else 1
    q, r = divmod(abs(int(value)), int(denominator))
    if 2 * r >= denominator:
        q += 1
    return sign * q


def round_div_power_of_two(value: int, shift: int) -> int:
    return round_div(value, 1 << shift)


def beta_to_int(beta: float, M: int) -> int:
    """Convert a non-negative coefficient to the separate M scale."""
    scaled = float(beta) * M
    if scaled >= 0:
        return int(floor(scaled + 0.5))
    return -int(floor(abs(scaled) + 0.5))


def memory_mix(y_prev: int, y_new: int, beta_int: int, config: FixedConfig) -> int:
    """Blend old memory with the new soft state."""
    numerator = beta_int * int(y_prev) + (config.M - beta_int) * int(y_new)
    return sat_b(round_div_power_of_two(numerator, config.m_shift), config)


def relay_memory_update(y_prev: int, belief: int, decision: int, beta: float, config: FixedConfig) -> int:
    beta_int = beta_to_int(beta, config.M)
    y_new = int(belief) - 2 * int(decision)
    return memory_mix(y_prev=y_prev, y_new=y_new, beta_int=beta_int, config=config)


def check_node_update(incoming: Sequence[int], syndrome_bit: int, config: FixedConfig) -> list[int]:
    """Return one min-sum outgoing message per incoming edge."""
    outgoing: list[int] = []
    syndrome_sign = -1 if syndrome_bit else 1
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
        outgoing.append(sat_b(sign * magnitude, config))
    return outgoing


def variable_belief(prior: int, incoming: Sequence[int], relay_term: int, config: FixedConfig) -> int:
    total = int(prior) + int(relay_term) + sum(int(value) for value in incoming)
    return sat_b(total, config)


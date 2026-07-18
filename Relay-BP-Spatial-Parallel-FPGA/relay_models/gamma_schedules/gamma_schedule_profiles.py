"""Reusable gamma schedule profiles for Relay-BP studies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class GammaScheduleProfile:
    """Named gamma schedule profile."""

    name: str
    gamma_values: tuple[float, ...]
    carry_gamma: float = 0.5


DEFAULT_GAMMA_PROFILES: tuple[GammaScheduleProfile, ...] = (
    GammaScheduleProfile(name="conservative", gamma_values=(0.2, 0.2, 0.3, 0.3), carry_gamma=0.4),
    GammaScheduleProfile(name="balanced", gamma_values=(0.4, 0.5, 0.6, 0.6), carry_gamma=0.5),
    GammaScheduleProfile(name="aggressive", gamma_values=(0.7, 0.8, 0.9, 1.0), carry_gamma=0.6),
    GammaScheduleProfile(name="staggered", gamma_values=(0.3, 0.55, 0.7, 0.85), carry_gamma=0.5),
)


def get_profile_names() -> list[str]:
    """Return the available gamma profile names."""

    return [profile.name for profile in DEFAULT_GAMMA_PROFILES]


def get_profile(name: str) -> GammaScheduleProfile:
    """Return a profile by name.

    Raises:
        KeyError: If the profile name is unknown.
    """

    for profile in DEFAULT_GAMMA_PROFILES:
        if profile.name == name:
            return profile
    raise KeyError(f"Unknown gamma profile: {name}")


def build_repeated_gamma_schedule(profile: GammaScheduleProfile, legs: int, cycles_per_leg: int) -> list[float]:
    """Expand a short profile into a leg/cycle schedule."""

    repeated: list[float] = []
    values = profile.gamma_values
    for _ in range(legs):
        for cycle_index in range(cycles_per_leg):
            repeated.append(values[cycle_index % len(values)])
    return repeated


def build_profile_family(names: Sequence[str] | None = None) -> list[GammaScheduleProfile]:
    """Return a filtered list of profiles or all defaults."""

    if names is None:
        return list(DEFAULT_GAMMA_PROFILES)
    selected: list[GammaScheduleProfile] = []
    for name in names:
        selected.append(get_profile(name))
    return selected

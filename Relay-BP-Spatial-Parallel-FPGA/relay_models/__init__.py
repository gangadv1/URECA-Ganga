"""Relay model package.

This package mirrors the core Relay-BP model families used in the project:
baseline decoder behavior, gamma schedule helpers, and parallel-lane
experiments. The implementations are re-exported from the simulation and FPGA
model modules so there is a single source of truth for the actual logic.
"""

from .baseline import *  # noqa: F401,F403
from .gamma_schedules import *  # noqa: F401,F403
from .parallel_lanes import *  # noqa: F401,F403

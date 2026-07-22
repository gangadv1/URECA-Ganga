"""Latency-tail and queue helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


def latency_quantiles(latencies: Sequence[float]) -> dict[str, float]:
    values = np.array(latencies, dtype=float)
    if values.size == 0:
        return {name: 0.0 for name in ("p50", "p90", "p99", "p99.9", "p99.99")}
    return {
        "p50": float(np.quantile(values, 0.50)),
        "p90": float(np.quantile(values, 0.90)),
        "p99": float(np.quantile(values, 0.99)),
        "p99.9": float(np.quantile(values, 0.999)),
        "p99.99": float(np.quantile(values, 0.9999)),
    }


@dataclass(frozen=True)
class QueueSummary:
    jobs: int
    average_wait: float
    max_wait: float
    deadline_miss_rate: float


def simulate_queue(latencies: Sequence[float], arrival_interval: float, deadline: float | None = None) -> QueueSummary:
    """Run a simple one-server queue with fixed arrivals."""
    if arrival_interval <= 0:
        raise ValueError("arrival_interval must be positive")
    server_free = 0.0
    waits: list[float] = []
    misses = 0
    for index, latency in enumerate(latencies):
        arrival = index * arrival_interval
        start = max(arrival, server_free)
        finish = start + float(latency)
        waits.append(start - arrival)
        server_free = finish
        if deadline is not None and finish - arrival > deadline:
            misses += 1
    if not waits:
        return QueueSummary(0, 0.0, 0.0, 0.0)
    return QueueSummary(
        jobs=len(waits),
        average_wait=float(np.mean(waits)),
        max_wait=float(np.max(waits)),
        deadline_miss_rate=misses / len(waits),
    )


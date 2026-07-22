"""Small paired-statistics helpers."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Sequence

import numpy as np
from scipy.stats import beta, binomtest, norm


@dataclass(frozen=True)
class McNemarResult:
    only_a_failed: int
    only_b_failed: int
    p_value: float


def mcnemar(a_failed: Sequence[bool], b_failed: Sequence[bool]) -> McNemarResult:
    a = np.array(a_failed, dtype=bool)
    b = np.array(b_failed, dtype=bool)
    if a.shape != b.shape:
        raise ValueError("paired arrays must have the same shape")
    only_a = int(np.sum(a & ~b))
    only_b = int(np.sum(~a & b))
    total = only_a + only_b
    p_value = 1.0 if total == 0 else float(binomtest(min(only_a, only_b), total, 0.5).pvalue)
    return McNemarResult(only_a_failed=only_a, only_b_failed=only_b, p_value=p_value)


def paired_risk_difference_ci(a_failed: Sequence[bool], b_failed: Sequence[bool], confidence: float = 0.95) -> tuple[float, float, float]:
    a = np.array(a_failed, dtype=float)
    b = np.array(b_failed, dtype=float)
    diff = a - b
    mean = float(np.mean(diff))
    if diff.size < 2:
        return mean, mean, mean
    z = float(norm.ppf(0.5 + confidence / 2.0))
    se = float(np.std(diff, ddof=1) / sqrt(diff.size))
    return mean, mean - z * se, mean + z * se


def tost_equivalent(a_failed: Sequence[bool], b_failed: Sequence[bool], margin: float, confidence: float = 0.90) -> bool:
    _, low, high = paired_risk_difference_ci(a_failed, b_failed, confidence)
    return low > -margin and high < margin


def binomial_upper_bound(failures: int, trials: int, confidence: float = 0.95) -> float:
    if trials <= 0:
        raise ValueError("trials must be positive")
    if failures < 0 or failures > trials:
        raise ValueError("failures must be between 0 and trials")
    if failures == trials:
        return 1.0
    return float(beta.ppf(confidence, failures + 1, trials - failures))


def enough_failures(failures: int, target: int = 100) -> bool:
    return int(failures) >= int(target)


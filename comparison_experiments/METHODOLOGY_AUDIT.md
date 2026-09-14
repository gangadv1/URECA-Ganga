# Methodology Audit: Relay-BP Baseline

Date: 2026-09-07

## Scope

This audit was completed before any larger shot campaign. The validation used 500 shots, p=0.001, the `[[144,12,12]]` code, and a 60-iteration limit. No 10,000-shot run was performed.

## Metric Definitions

### Converged
A trial is **converged** when the hard-decision decoded vector `decoded_error` satisfies:

```text
(Hx @ decoded_error) mod 2 == syndrome
```

Equivalently, the residual syndrome weight is zero.

This is syndrome-valid convergence only. It is not proof of logical correctness.

### Converged + Correct Logical State
**Unavailable in the current simulator.** The implementation does not evaluate logical observables, a logical-operator basis, or stabilizer-equivalence between the decoded correction and the generated error.

### Converged + Logical Failure
**Unavailable in the current simulator.** A syndrome-valid correction can differ from the true error by a nontrivial logical operator, and the current code does not classify that case.

### Timeout / Non-convergence
A trial is **non-converged/timeout** when no trajectory reaches zero residual syndrome within `max_iterations=60`.

For an ensemble, the trial is converged if at least one tested trajectory converges; the reported iteration count is the smallest converged trajectory iteration count. If none converges, the trial is a timeout/non-convergence at 60 iterations.

## Paired Shot Audit

N=1, N=2, and N=4 use the same underlying generated shot inputs:

- Shot `i` uses RNG seed `seed_base + i`, with `seed_base=12345`.
- The generated `true_error`, syndrome, and noisy prior LLR are cached by shot index.
- N only changes the Relay trajectory count and trajectory seeds `[11, 22, 33, 44]`.
- A focused check confirmed repeated generation of shot 0 returns identical syndrome, prior LLR, and true error.

Therefore the N comparison is paired at the input level. The current saved summary does not retain per-shot outcome vectors, so paired McNemar/bootstrap analysis cannot be reconstructed from the summary CSV alone.

## Percentile Audit

Iteration summaries are computed with NumPy `np.percentile` using its default linear interpolation. For the validation, P95 and P99 are both 60 for all configurations because the upper tails reach the 60-iteration cap. These are valid iteration/timeout statistics, not logical-error statistics.

## Corrected 500-Shot Validation

| Configuration | Converged | Non-converged/timeout | Convergence rate | Non-convergence rate | Logical correctness |
|---|---:|---:|---:|---:|---|
| Relay-BP N=1 | 28 | 472 | 0.056 | 0.944 | unavailable |
| Relay-BP N=2 | 46 | 454 | 0.092 | 0.908 | unavailable |
| Relay-BP N=4 | 88 | 412 | 0.176 | 0.824 | unavailable |

Iteration statistics:

| Configuration | Mean | Median | Std. dev. | P95 | P99 | Min | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| Relay-BP N=1 | 58.166 | 60 | 8.420 | 60 | 60 | 7 | 60 |
| Relay-BP N=2 | 56.778 | 60 | 11.090 | 60 | 60 | 7 | 60 |
| Relay-BP N=4 | 53.594 | 60 | 15.112 | 60 | 60 | 7 | 60 |

## Statistical Meaning

Approximate 95% binomial intervals for convergence rate are:

- N=1: 0.056, approximately [0.036, 0.076]
- N=2: 0.092, approximately [0.067, 0.117]
- N=4: 0.176, approximately [0.143, 0.209]

These support an exploratory monotonic convergence improvement across N under this fixed workload. They are not confidence intervals for logical error rate. A paired significance test should be run in a future campaign after saving per-shot outcomes for every N.

## Conclusion

The previous values `0.944`, `0.908`, and `0.824` were exactly `1 - convergence_rate`. They must not be called LER. The corrected output uses `convergence_rate` and `nonconvergence_rate`; logical-correct and logical-failure counts are explicitly unavailable.

The current result can legitimately be called a **syndrome-convergence/non-convergence comparison**. It cannot legitimately be called a logical-error-rate comparison until a logical-observable or stabilizer-equivalence check is implemented.

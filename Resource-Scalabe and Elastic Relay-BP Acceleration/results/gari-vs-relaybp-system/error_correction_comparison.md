# Error-correction comparison

## Relay-BP archived p=0.003 panel

| Metric | N=1/E0 | N=2 first success |
|---|---:|---:|
| Shots | 128 | 128 |
| Syndrome-converged | 125 | 128 |
| Non-converged | 3 | 0 |
| Logical-correct | 125 | 128 |
| Syndrome-valid logical errors | 0 | 0 |
| E1 wins | — | 33 |
| N=1 failures rescued | — | 3 |

The N=1 convergence/logical-success rate is 97.656%; N=2 is 100% on this panel. The Wilson intervals overlap, and 128 shots do not establish a logical-error-rate curve. Candidate weights and residual traces exist in the archive, but there is no basis for comparing their numerical values with GARI because the transformed variable spaces and decoder objective differ.

BA2 does not change error correction: 256/256 E0/E1 trajectories and 47,736/47,736 mapped iterations were exact, including all 33 E1 wins and three rescues.

## GARI evidence

The audited architecture paper uses normalized min-sum on the GARI-transformed correlated X/Y/Z detector model, the Gross `[[144,12,12]]` code, 12 syndrome rounds, and p=0.001. It states that 6-bit input LLRs, 8-bit check messages, and 10-bit variable messages closely approach floating-point accuracy. It reports 2.28 average iterations for one decoder and 1.13 for an ensemble of 24, based on the earlier GARI work.

It does not provide a logical-error-rate table, shot count, convergence count, correction-validity table, or matched per-case rescue analysis in this architecture paper.

## Classification

Current accuracy comparability is **INVALID** for a quantitative winner. The studies differ in p, graph transformation, algorithm, ensemble size, precision, stopping behavior, and sample cohort. GARI is a relevant correlated-error decoder baseline, but the present evidence cannot show which corrects more errors under the same workload.

## Required matched experiment

Use one exact Gross `[[144,12,12]]` 12-round circuit-noise model and generate one shared, hashed syndrome/logical cohort at common p values, initially p=0.001 and p=0.003. Run:

1. Reproducible GARI normalized min-sum with its documented quantization and ensemble rule.
2. Relay-BP N=1.
3. Relay-BP N=2 first-success.

For every decoder report logical failure rate with confidence intervals, syndrome convergence, invalid-correction rate, residual-syndrome rate, mean iterations, p95/p99 iterations, and correction validity against the same original observables. Fix maximum work and define ensemble winner/stopping rules before sampling. At least enough shots to resolve the target logical-failure regime are required; 128 is insufficient.

# Controlled node-state clipping assessment

## Tested representation

- Signed 12-bit mantissas, unsigned 6-bit exponents, `M=16`, and four guard bits.
- One unchanged maximum-selected exponent for the combined `mu`/`nu` edge block per iteration.
- One exponent for the combined memory-adjusted-bias/marginal state block per iteration.
- State policies: maximum, exact p99.9, exact p99.5, and exact p99 absolute-magnitude cap.
- Percentile values above the cap are symmetrically clipped before state quantization. Physical priors retain exponent zero.

## Main results (128 paired shots)

| Configuration | Policy | Success | Avg iterations | p99 iterations | State clipped | State zeroed | Edge zeroed |
|---|---:|---:|---:|---:|---:|---:|---:|
| Low latency | max | 73/128 | 192.29 | 260.00 | 0% | 16.294% | 0.360% |
| Low latency | p99.9 | 82/128 | 177.75 | 260.00 | 0.096% | 15.670% | 0.352% |
| Low latency | p99.5 | 91/128 | 170.18 | 260.00 | 0.483% | 13.107% | 0.402% |
| Low latency | p99 | 93/128 | 162.70 | 260.00 | 0.925% | 12.887% | 0.387% |
| Balanced | max | 128/128 | 167.33 | 468.50 | 0% | 12.308% | 0.257% |
| Balanced | p99.9 | 128/128 | 166.27 | 485.60 | 0.096% | 11.246% | 0.258% |
| Balanced | p99.5 | 127/128 | 170.77 | 517.91 | 0.487% | 9.959% | 0.249% |
| Balanced | p99 | 126/128 | 157.50 | 828.80 | 0.979% | 9.908% | 0.260% |
| High success | max | 127/128 | 149.37 | 503.92 | 0% | 2.633% | 0.196% |
| High success | p99.9 | 128/128 | 134.96 | 395.91 | 0.098% | 2.810% | 0.220% |
| High success | p99.5 | 127/128 | 143.95 | 538.74 | 0.493% | 2.364% | 0.214% |
| High success | p99 | 127/128 | 142.90 | 688.42 | 0.987% | 1.841% | 0.183% |

Float success/average iterations were respectively 125/46.91, 127/67.75, and 128/100.45. Unscaled b=14/M=16 achieved 126/49.47, 127/65.64, and 127/110.49. No tested clipping policy approaches the low-latency references.

## Hardware approximation assessment

Exact percentile selection is not RTL-friendly: each iteration's threshold was selected from 135,504 state magnitudes. A streaming magnitude histogram followed by a reverse cumulative count and a second state pass is a plausible approximation, but plain leading-one buckets are too coarse. For low-latency p99, 149,680,426 accumulated values occupied the threshold's leading-one bucket, while only 3,863,125 were in strictly higher buckets. Therefore a power-of-two bucket boundary cannot closely reproduce the exact within-bucket p99 threshold. Finer sub-bins or fixed top-count rejection would be required and would need a separate validation study.

## Decision

Controlled clipping helps, and p99 is the strongest low-latency policy tested, but it does not satisfy the lock criterion. The remaining blocker is precision collapse within the node-state block: even after clipping about 0.925% of low-latency state values, 12.887% of nonzero state values still quantize to zero and success remains only 93/128 versus 125/128 float and 126/128 unscaled b=14.

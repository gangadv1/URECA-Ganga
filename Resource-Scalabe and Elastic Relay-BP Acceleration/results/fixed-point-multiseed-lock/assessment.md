# Unscaled saturating fixed-point lock assessment

## Experiment

- Five deterministic circuit-sample seeds: 20260809 through 20260813.
- 128 shots per seed; 640 paired shots per algorithm configuration.
- Identical saved Tier-2 syndromes/logical observations for float and every fixed format.
- Signed unscaled stored messages with b=14, b=16, or b=18; M=16; four guard bits.
- No block floating, exponent, normalization, percentile, or dynamic-scaling mechanism.

## Aggregate results

| Config | Format | Logical success | Conv. | SV logical errors | Non-conv. | Avg iters | p50 | p90 | p99 | Max | Avg/max legs | Stored sat. | Marginal sat. |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Low latency | float | 622/640 | 622 | 0 | 18 | 48.11 | 31 | 95.1 | 260.0 | 260 | 1.25/4 | - | - |
| Low latency | b14 | 619/640 | 620 | 1 | 20 | 51.57 | 32 | 104.0 | 260.0 | 260 | 1.28/4 | 16.36% | 32.27% |
| Low latency | b16 | 617/640 | 618 | 1 | 22 | 51.70 | 32 | 103.0 | 260.0 | 260 | 1.28/4 | 10.65% | 21.22% |
| Low latency | b18 | 618/640 | 619 | 1 | 21 | 51.63 | 32 | 102.1 | 260.0 | 260 | 1.28/4 | 7.15% | 13.93% |
| Balanced | float | 638/640 | 638 | 0 | 2 | 65.51 | 31 | 129.1 | 600.84 | 980 | 1.51/16 | - | - |
| Balanced | b14 | 636/640 | 637 | 1 | 3 | 62.37 | 32 | 123.2 | 582.11 | 980 | 1.45/16 | 9.40% | 18.40% |
| Balanced | b16 | 637/640 | 638 | 1 | 2 | 65.06 | 32 | 128.4 | 664.37 | 980 | 1.49/16 | 6.94% | 13.54% |
| Balanced | b18 | 637/640 | 638 | 1 | 2 | 63.85 | 32 | 132.1 | 645.88 | 980 | 1.47/16 | 5.73% | 11.14% |
| High success | float | 639/640 | 640 | 1 | 0 | 102.20 | 70 | 170.0 | 588.83 | 1066 | 1.86/18 | - | - |
| High success | b14 | 639/640 | 639 | 0 | 1 | 116.18 | 72.5 | 188.1 | 816.50 | 1940 | 2.09/32 | 3.84% | 7.64% |
| High success | b16 | 638/640 | 638 | 0 | 2 | 113.63 | 72.5 | 195.2 | 732.29 | 1940 | 2.04/32 | 2.56% | 5.11% |
| High success | b18 | 640/640 | 640 | 0 | 0 | 110.84 | 72.5 | 194.1 | 705.92 | 1485 | 1.99/25 | 1.60% | 3.22% |

All fixed formats had zero physical-prior clipping and zero b+4 accumulator saturation. Selected-solution weights remain close but are not expected to equal float because quantization changes which syndrome-valid correction is reached.

## Paired logical assessment

The aggregate logical-success differences versus float for b14/b16/b18 were respectively:

- Low latency: -3, -5, -4 shots out of 640.
- Balanced: -2, -1, -1 shots out of 640.
- High success: 0, -1, +1 shots out of 640.

Two-sided exact paired discordance tests found no significant difference (all p >= 0.44). Saturation therefore does not show systematic logical harm on this 1,920-shot-per-format panel.

## Width and hardware trade-off

- b14 minimizes message memory and arithmetic width, but its high-success tail reaches 1,940 iterations/32 legs and its p99 is 38.7% above float.
- b16 costs 14.3% more stored bits than b14, but still reaches 1,940 iterations and provides no logical advantage.
- b18 costs 28.6% more stored bits than b14 (12.5% more than b16), but is the only width with 640/640 high-success logical successes and reduces that tail to p99 705.92 and max 1,485/25 legs.
- Relative BRAM/URAM packing and LUT/DSP cost require synthesis; no device resource counts are inferred here.
- All three unscaled formats require only signed saturating arithmetic and a b+4 accumulator. This is materially simpler than block-floating designs: no exponent storage, block scans, rescaling shifts, threshold selection, or cross-scale alignment.

## Decision

**LOCK FOR HARDWARE: YES.**

Lock the numerical model as:

- signed 18-bit unscaled stored priors, lambda biases, check-to-variable messages, variable-to-check messages, and marginals;
- signed 22-bit variable-node accumulator (four guard bits), saturated only when stored back to 18 bits;
- M=16 power-of-two gamma coefficient scale with nearest/ties-away-from-zero division;
- saturation bounds [-131072, 131071];
- canonical per-node gamma, update order, relay handoff, convergence, and candidate-selection semantics unchanged.

b18 is chosen over b14 solely because b14's high-success tail penalty is too pronounced for a confident hardware lock. The remaining b18 tail difference is an explainable quantization effect without logical degradation in this panel and should be treated as the fixed-point reference behavior during datapath verification.

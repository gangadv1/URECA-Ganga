# Independent gamma RNG sign-off

## Distribution contract

Later-leg software semantics are `gamma ~ Uniform[-0.24,0.66]`, followed by signed ties-away rounding of `16*gamma`. The exact discrete probabilities are:

- coefficient -4: `17/720`;
- each coefficient -3 through 10: `50/720`;
- coefficient 11: `3/720`.

Hardware accepts a PRNG word when its low ten bits are below 720 and uses fixed comparison thresholds `17, 67, 117, ..., 717, 720`. Values 720 through 1023 are rejected. This avoids replacing the endpoint-weighted distribution with an incorrect uniform integer distribution.

## RTL sample

The 200,000-coefficient RTL sample produced:

| q | Expected | Observed | Absolute deviation |
|---:|---:|---:|---:|
| -4 | 0.02361111 | 0.02356000 | 0.00005111 |
| -3 | 0.06944444 | 0.07013000 | 0.00068556 |
| -2 | 0.06944444 | 0.06925500 | 0.00018944 |
| -1 | 0.06944444 | 0.07004000 | 0.00059556 |
| 0 | 0.06944444 | 0.06843000 | 0.00101444 |
| 1 | 0.06944444 | 0.06972000 | 0.00027556 |
| 2 | 0.06944444 | 0.06941000 | 0.00003444 |
| 3 | 0.06944444 | 0.07033000 | 0.00088556 |
| 4 | 0.06944444 | 0.06833000 | 0.00111444 |
| 5 | 0.06944444 | 0.06903000 | 0.00041444 |
| 6 | 0.06944444 | 0.06933000 | 0.00011444 |
| 7 | 0.06944444 | 0.06944500 | 0.00000056 |
| 8 | 0.06944444 | 0.06974500 | 0.00030056 |
| 9 | 0.06944444 | 0.06924500 | 0.00019944 |
| 10 | 0.06944444 | 0.06997500 | 0.00053056 |
| 11 | 0.00416667 | 0.00402500 | 0.00014167 |

The sample consumed 284,096 PRNG words, including 84,096 rejected words.

## Verification summary

- RTL/Python exact: five seeds, 233 directed coefficients, raw words and final states exact.
- Abort: before first coefficient, stalled valid coefficient, and final boundary pass.
- Independence: identical seeds remain sequence-identical despite asymmetric handshakes; aborting engine 0 does not affect engine 1.
- Tier-2 dual generation: 67,752 coefficients per engine in 96,316 elapsed cycles. Engine 0 used 96,309 words with 28,557 rejects; engine 1 used 96,247 words with 28,495 rejects.
- Decoder integration: three intermediate shots, two engines, complete final mu/nu/marginal/decision arrays exact against seed-derived Python oracles. Real-RNG first-success and cancellation smoke tests pass.

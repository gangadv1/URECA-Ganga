# Tail-latency comparison

| Metric | Relay-BP evidence | GARI evidence | Status |
|---|---|---|---|
| Mean | 128-shot N=1/N=2 paired model plus combined BA2 derivation | Implemented average latency | Not directly comparable |
| p90 | N=1 1.449B; N=2 1.086B detailed modeled cycles | Not reported | Relay-BP has explicit evidence |
| p95 | N=1 2.258B; N=2 1.456B detailed modeled cycles | Not reported | Relay-BP has explicit evidence |
| p99 | N=1 7.384B; N=2 2.209B detailed modeled cycles | Not reported | Relay-BP has screening-level evidence |
| Maximum | N=1 7.384B; N=2 4.724B detailed modeled cycles | Not reported | Relay-BP has observed-panel evidence |
| Hard-case rescue | Three N=1 failures rescued; E1 wins 11/13 top-10% cases | Not reported per case | Relay-BP has paired evidence |
| Ensemble behavior | Two independent gamma/RNG paths; first success wins | 3 physical cores/device and 24-decoder context; diversity/arbitration unspecified | Mechanisms cannot be equated |

GARI reports average latency but does not provide directly comparable p95/p99 tail-latency statistics in the audited paper.

Relay-BP's N=2 effect is tail-concentrated: median is unchanged, mean drops 35.15%, p95 drops 35.53%, and p99 drops 70.09%. In the 13-shot top-10% N=1 tail, E1 wins 11 and the mean paired reduction is 48.26%; in the seven-shot top-5% tail, E1 wins all seven and the mean reduction is 63.48%. The p99 estimate is preliminary because 128 shots provide very few extreme-tail observations.

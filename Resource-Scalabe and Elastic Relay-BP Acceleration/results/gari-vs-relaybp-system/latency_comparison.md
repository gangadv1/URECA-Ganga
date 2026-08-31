# Average-latency comparison

## Relay-BP N=1 versus N=2 evidence

The canonical study contains 128 paired p=0.003 shots, 32 from each circuit seed 20260809–20260812. The locked design uses b=18, a 22-bit guard accumulator, M=16, S=1, R=32, first-leg limit 80, later-leg limit 60, and P=4.

The detailed RTL-calibrated model reports:

| Metric | N=1 | N=2 first success | Reduction |
|---|---:|---:|---:|
| Mean cycles | 726,676,463 | 471,284,892 | 35.15% |
| p50 | 287,091,238 | 287,091,238 | 0% |
| p90 | 1,448,701,890 | 1,086,244,420 | 25.02% |
| p95 | 2,257,959,401 | 1,455,705,983 | 35.53% |
| p99 | 7,384,342,293 | 2,208,714,916 | 70.09% |
| Maximum | 7,384,343,541 | 4,724,250,260 | 36.02% |

These are architectural/model cycles, not nanoseconds. N=2 does 1.299× the active work of N=1 under the conservative cancellation model; first-success latency improves by using additional trajectory hardware, not by making one iteration cheaper.

## BA2 folding effect

Using fixed archived E0 trajectories and the P=4 folding model:

| Metric | Original layout | BA2 | Reduction |
|---|---:|---:|---:|
| Mean | 726,388,133 | 617,117,727 | 15.043% |
| p95 | 2,257,054,018 | 1,917,397,629 | 15.049% |
| p99 | 7,381,272,452 | 6,270,598,460 | 15.047% |

BA2 reduces the modeled cost of the same trajectory through fewer bank retries. It does not alter iterations, convergence, or corrections.

## New combined factorial derivation

The combined result applies the existing formula `iterations × layout_iteration_cycles + legs × layout_relay_init_cycles` independently to archived E0 and E1, then selects the first successful trajectory. Original costs are 3,788,781 cycles/iteration and 969,916 cycles/leg; BA2 costs are 3,214,635 and 1,068,955.

| Condition | Mean | p50 | p90 | p95 | p99 | Maximum |
|---|---:|---:|---:|---:|---:|---:|
| N=1 original | 726,388,133 | 287,022,882 | 1,448,120,519 | 2,257,054,018 | 7,381,272,452 | 7,381,272,452 |
| N=2 original | 471,101,739 | 287,022,882 | 1,085,788,799 | 1,455,090,357 | 2,207,801,682 | 4,722,245,457 |
| N=1 BA2 | 617,117,727 | 243,773,898 | 1,230,224,497 | 1,917,397,629 | 6,270,598,460 | 6,270,598,460 |
| N=2 BA2 | 400,249,878 | 243,773,898 | 922,480,141 | 1,236,224,243 | 1,875,628,598 | 4,011,810,090 |

Relative to N=1 original, N=2+BA2 reduces modeled mean by 44.899%, p95 by 45.228%, and p99 by 74.589%. This is a derived software-model result, not a measured hardware combination.

## GARI

GARI reports approximately 274 MHz and `10+1728i` cycles. At p=0.001 over 12 rounds it reports 14.4 µs for one decoder at 2.28 average iterations, and 7.16 µs for a 24-decoder ensemble at 1.13 average iterations—approximately 596 ns per round.

The absolute values cannot be compared with Relay-BP modeled cycles because the algorithms, p, graph, ensemble size, implementation level, and cycle accounting differ.

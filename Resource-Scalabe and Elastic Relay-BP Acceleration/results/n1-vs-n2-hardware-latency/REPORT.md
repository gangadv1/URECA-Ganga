# Paired N=1 versus N=2 hardware-latency screening study

## Scope and configuration

- Official Tier-2 gross `[[144,12,12]]` memory-Z package, 12 noisy rounds, `p=0.003`.
- 128 paired shots: 32 shots from each circuit seed `20260809`–`20260812`.
- N=1 engine 0 and N=2 engine 0 use the same per-shot seed `S0`; N=2 engine 1 uses independent `S1`.
- Frozen candidate: P=4, b18 stored messages, 22-bit accumulator, M=16, S=1, R=32, first-leg gamma +2/16, first-leg limit 80, later-leg limit 60.
- Later gamma coefficients use the frozen xorshift64 hardware generator and exact discrete mapping for `[-0.24,0.66]`.
- Latency is architectural cycles from the RTL-calibrated cycle model, not Python runtime or iteration count. Phase constants are CHECK 508,753, VARIABLE 2,489,173, CONVERGENCE 790,855, and RELAY_INIT 969,916 cycles. The model is calibrated to the exhaustive Tier-2 one-iteration RTL and complete multi-leg intermediate RTL traces.
- Cancellation cleanup and avoided-work figures are a conservative phase-boundary model calibrated to cancellation RTL tests. They are not exhaustive full-Tier-2 cancellation traces and must not be interpreted as power or energy measurements.

## Logical results

| Metric | N=1 | N=2 first success |
|---|---:|---:|
| Syndrome convergence | 125/128 (97.656%) | 128/128 (100%) |
| Logical success | 125/128 (97.656%) | 128/128 (100%) |
| Logical-success Wilson 95% CI | 93.336%–99.200% | 97.086%–100% |
| Syndrome-valid logical errors | 0 | 0 |
| Non-convergence | 3 | 0 |

N=2 rescued all three N=1 non-convergences. No shot exhibited the risk case in which engine 1 returned a logically wrong syndrome-valid correction before a correct engine-0 result.

## Architectural latency

| Statistic | N=1 cycles | N=2 cycles | Absolute reduction | Reduction |
|---|---:|---:|---:|---:|
| Mean | 726,676,463 | 471,284,892 | 255,391,571 | 35.15% |
| p50 | 287,091,238 | 287,091,238 | 0 | 0% |
| p90 | 1,448,701,890 | 1,086,244,420 | 362,457,470 | 25.02% |
| p95 | 2,257,959,401 | 1,455,705,983 | 802,253,418 | 35.53% |
| p99 | 7,384,342,293 | 2,208,714,916 | 5,175,627,377 | 70.09% |
| Maximum | 7,384,343,541 | 4,724,250,260 | 2,660,093,281 | 36.02% |

Standard deviations were 1,261,211,420 cycles for N=1 and 557,641,214 cycles for N=2. The mean paired reduction bootstrap 95% interval was 123,520,201–432,574,177 cycles. Bootstrap intervals for the marginal percentile differences were 130,265,185–1,142,726,912 cycles at p90 and 671,236,497–5,551,711,444 cycles at p99. The p99 estimate is screening-level only at 128 shots.

Algorithmically, N=1 averaged 190.88 iterations and 3.27 legs; the N=2 winner averaged 123.78 iterations and 2.19 legs. Thus the gain is trajectory racing finding shorter successful trajectories, not a change in per-iteration RTL cost.

## Winner and tail analysis

- Engine 0 won 95 shots; engine 1 won 33. Of the engine-0 wins, 69 were same-cycle successes and therefore resolved by deterministic engine-0 priority.
- There were no dual failures.
- In the 13-shot top 10% N=1 tail, engine 1 won 11, used fewer legs in 11, and produced a mean 48.26% latency reduction.
- In the 7-shot top 5% tail, engine 1 won all 7, used fewer legs in all 7, and produced a mean 63.48% reduction.
- The two empirical top-1% entries were both engine-1 wins/rescues, but this subset is too small for a stable tail claim.

The improvement is therefore concentrated in hard shots rather than being a uniform shift: median latency was unchanged, while high-percentile latency fell materially.

## Cancellation and resource availability

- Mean cancellation cleanup: 1,147,354 cycles; p90/max: 2,489,174 cycles.
- Mean avoided loser work: 476,062,926 cycles; total: 60,936,054,534 cycles.
- N=1 active-cycle work total: 93,014,587,356 cycles.
- N=2 active-cycle work total: 120,795,793,605 cycles, or 1.299 times N=1. This is a computational-work proxy, not energy.
- Mean pair-reuse cycle: 472,432,246; p90: 1,088,733,594; p99: 2,211,204,090; maximum: 4,726,739,434.

User-visible result latency is the first-success cycle. Under the conservative no-overlapping-frame policy, throughput availability is the pair-reuse cycle after loser quiescence.

## Integrity and limitations

- All 128 `(sample_seed, shot)` keys and all 128 detector/logical hash pairs are unique; no duplicated circuit shot was detected.
- Four independent circuit seeds were used.
- p=0.004 was not added because the required p=0.003 128-shot stage already took about 22.4 minutes and satisfied the requested first screening target.
- Full decoder trajectories were executed in the locked Python fixed-point model with the exact hardware PRNG sequence. Architectural cycles were calculated from exhaustively RTL-calibrated phase behavior; 128 full Tier-2 RTL shots were not simulated gate-by-gate.
- Cancellation-disabled equality of first-success timing is covered by directed RTL cancellation regressions, not a second 128-shot run.
- The logical-rate intervals overlap substantially, so this study shows no observed degradation but is not powered to establish LER equivalence.
- Icarus emitted known assertion-synthesis and constant-select sensitivity notices in assertion-enabled verification. All smoke tests passed; these notices do not alter this experiment's results.

## Decision

**RESEARCH HYPOTHESIS: PARTIALLY SUPPORTED.** N=2 materially reduced mean, p90, p99, and observed maximum latency, with the strongest effect in hard shots, three rescues, and no observed logical-risk event. The classification remains partial because 128 shots give weak p99/LER precision and the bulk latency study used the RTL-calibrated hardware model rather than exhaustive full-shot RTL simulation.

**READY FOR VIVADO N=1/N=2 RESOURCE AND TIMING EVALUATION: YES.** The screening result is strong enough to justify measuring the area, timing, and power cost of the already-frozen N=1 and N=2 implementations without changing their architecture.

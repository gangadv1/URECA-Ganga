# N=2 phase-safe cancellation sign-off

## Safe-stop policy

| Active phase | Cancellation boundary | Outstanding-work treatment |
|---|---|---|
| Gamma load | Current coefficient handshake | Accepted write commits; source receives `gamma_abort`; no read response exists |
| Relay initialization | End of relay-init phase | All edge/fault and prior responses, conflict subsets, and nu writes drain |
| Check update | End of check phase | Both passes finish; accepted reads and mu writes drain |
| Variable update | End of variable phase | Pointer/node reads, mu gather retries, node writes, and nu write retries drain |
| Convergence | End of convergence phase | Decision gathers and residual accumulation finish; candidate/next phase is suppressed |

Cancellation never asynchronously resets a controller. `cancel_ack` is issued only at the safe boundary. `cancelled` is distinct from `failed`, and `quiescent` requires no owner request, response, phase busy signal, or engine busy state. With cancellation deasserted, the original state and cycle sequence is unchanged.

## Directed results

All directed cases passed with assertions enabled:

- first- and later-leg gamma load: immediate boundary acknowledgement, `gamma_abort` observed;
- relay initialization: 215-cycle drain from injection;
- check update: 244-cycle drain;
- variable update: 606-cycle drain;
- convergence: 301-cycle drain;
- cancellation during a pending same-bank mu gather subset: 591-cycle phase drain;
- cancellation during a pending same-bank nu write subset: 572-cycle phase drain.

The drain counts are phase-position dependent and are not fixed interface latencies.

## Paired intermediate results

The three-shot suite passed for equal timing and both asymmetric stall assignments. Same-cycle success selected engine 0 and marked engine 1 cancelled. Engine-0-first and engine-1-first cases preserved the winning correction and metadata. Dual failure caused no cancellation and retained the existing global-failure rule.

For the asymmetric stalled-loser run:

| Shot | Winner commit | Loser quiescent | Cleanup | Natural loser completion | Avoided loser cycles |
|---|---:|---:|---:|---:|---:|
| relay rescue | 5862 | 5978 | 116 | 6282 | 304 |
| first-leg success | 2380 | 2549 | 169 | 2548 | -1 |

The second case demonstrates that cancellation is not useful when the loser is already at the end of its current atomic phase. First-success latency is unchanged in both cases.

## Tier-2 structural result

The cancellation-enabled N=2 top elaborated at `C=1728`, `V=67752`, `E=391320`, `P=4`. A controlled arbiter-boundary winner was committed while the losing full-width engine was in gamma load. The loser acknowledged and quiesced with no later request or response. This is a cancellation-structure test, not a naturally converged Tier-2 decode.

Assertion-enabled and assertion-free elaboration pass. Existing Icarus constant-select sensitivity notices remain tool limitations in the memory fabric; no new width, signedness, latch, or unbounded-loop issue was introduced.

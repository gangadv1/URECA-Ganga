# Relay-BP M4 software/address-level validation

This study validates the analytical M4 memory architecture without changing RTL, Relay-BP equations, fixed-point precision, BA2 mappings, gamma streams, or N=2 first-success semantics. `run_m4_validation.py` implements a separate M4 oracle with one phase-aliased edge-message store per trajectory, compact degree-table traversal, and logically shared immutable graph/prior/syndrome data.

## Result

- Four-case pilot: 4/4 exact.
- Full archive: 256/256 exact (128 E0 and 128 E1), covering 47,736/47,736 mapped iterations.
- Message alias hazards: 0 across 391,320 incidences.
- Degree traversal: exact for all 1,728 checks and 67,752 faults.
- BA2 retry subsets and modeled phase cycles: unchanged exactly.
- N=2 first success under dual-read sharing: 95 E0 wins, 33 E1 wins, all three rescues preserved; no changed winner, completion cycle, success, or logical result.

The shared-port trace is an address-level service model. Fractions in `shared_memory_port_demand.csv` are over `(static issue group, bank)` observations and exclude unrelated arithmetic/idle controller cycles. While both engines are active they request the same immutable address stream, so an accessed logical bank sees two simultaneous reads and never more than two. A two-read bank therefore adds zero modeled stalls.

`single_port_control.csv` is deliberately conservative: E0 receives priority and every coincident static read is serialized under a phase-lock assumption. It is a negative control, not a cycle-accurate RTL arbiter. It changes six first-success winners and produces mean/p95/p99 added modeled cycles of 21,281,649 / 107,240,318 / 215,527,548, demonstrating that one-read sharing is not acceptable for the frozen N=2 timing model.

## Validated memory model

M4 stores 32,933,564 bits (3.926 MiB): 15,593,616 shared-static bits and 17,339,948 duplicated dynamic bits. This includes two 7,043,760-bit aliased message stores. The ideal capacity is 894 BRAM36 equivalents; four-bank rounding gives 925. With true-dual-read shared banks, the bandwidth-aware analytical estimate remains 925. A conservative fallback that replicates every shared-static array is 1,346. These are analytical capacity estimates, not synthesized BRAM results.

Against the cited GARI measurements, both 925 and the 1,346 fallback are numerically below the measured 2,121 BRAM for three GARI cores, but neither is below the measured 704 BRAM for one GARI core. Cross-design numbers are not hardware-equivalent measurements.

## Reproduction

Run from the repository root:

```sh
python3 results/relaybp-memory-m4-validation/run_m4_validation.py
```

Completed trajectory checkpoints are reused. Delete or alter no checkpoint unless intentionally rerunning decoder trajectories. The script fails the final study status if canonical/M4 traces, archived iteration/leg metadata, or the frozen 47,736-iteration total do not match.

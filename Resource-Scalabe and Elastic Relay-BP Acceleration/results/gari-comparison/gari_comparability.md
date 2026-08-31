# GARI–BA2 comparability

## Overall classification: partially comparable

The studies share the Gross `[[144,12,12]]` code family, a 12-round memory setting, detector-error-model message passing, and a goal of resource-conscious correlated-error decoding. They do not share a verified graph, physical-error rate, algorithm, numerical format, schedule, sample panel, hardware target, or latency definition.

## Workload alignment

GARI reports transformed blocks `D_X` 792×7920, `D_Z` 936×8784, `U` 7920×51048, and `V` 8784×51048 at `p=0.001`. It does not specify an exact Stim circuit, DEM file, full circuit-noise channel, shot cohort, or graph incidence count in this architecture paper.

BA2 uses the repository's memory-Z Stim/DEM at `p=0.003`: 1,728 detector nodes, 67,752 mathematical fault variables, and 391,320 detector–fault incidences. Its fixed-point Relay-BP trajectories come from a fixed 128-shot archive (E0 and E1).

The matching 792+936=1,728 check count is informative but not sufficient for direct equivalence: GARI's Equation (2) adds zero-syndrome block rows and auxiliary variable blocks, and its reported columns/submatrices do not match BA2's canonical fault space.

## Latency limits

GARI reports clocked FPGA timing: approximately 274 MHz, `10+1728i` cycles, 14.4 µs average for a single decoder, and 7.16 µs over 12 rounds (about 596 ns/round) for a 24-decoder ensemble at `p=0.001`.

BA2 reports relative software-model results only: 4,758,697→4,283,590 structural modeled cycles (−9.984%) and 726,388,132.63→617,117,727.34 trajectory-weighted mean modeled cycles (−15.043%). These are not clock cycles from implemented RTL and cannot be converted to nanoseconds from GARI's frequency.

A valid latency comparison requires a BA2 clocked implementation, an identical decoder-work definition, identical stopping/ensemble rules, the same graph/noise/samples, and consistent inclusion of input, routing, convergence, and winner-selection time.

## Resource limits

GARI has post-implementation resource values. BA2 has only four modeled lanes/banks and no LUT, register, BRAM/URAM, DSP, routing, frequency, power, or energy result. Direct resource comparison is unavailable.

## Metric-specific classification

- Algorithmic mechanism: **partially comparable**—both are message passing; graph/equations differ.
- Correlated-error representation: **partially comparable**—both start from DEM concepts; GARI explicitly refactors X/Y/Z components.
- Graph transformation: **directly contrastable, not quantitatively comparable**—GARI changes factorization; BA2 only permutes storage.
- Folding/resource reuse: **partially comparable**—both reuse resources, with different granularities/schedules.
- Explicit modulo-bank conflict mitigation: **not the same mechanism**.
- Accuracy: **not directly comparable**.
- Latency: **not directly comparable**.
- Resources: **not directly comparable**.

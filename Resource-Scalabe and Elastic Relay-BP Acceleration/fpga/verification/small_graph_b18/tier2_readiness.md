# Tier-2 readiness after the small-graph complete engine

The small-graph engine implements the canonical phases and is functionally complete for its configured graph. Its internal arrays are synthesizable register memories used behind phase-separated controller states. They deliberately are not presented as inferred BRAM/URAM. Before Tier-2 simulation, each array must be replaced by a registered memory adapter with an explicit request/response latency; traversal counters must advance only when the response is valid.

| Object | Small graph | Tier-2 requirement |
|---|---:|---:|
| checks | 3 | 1,728; check address 11 bits |
| variables | 4 | 67,752; variable address 17 bits |
| incidences | 9 | 391,320; edge/pointer address 19 bits |
| check pointer | 4 x 32 bits | 1,729 entries, 19 significant bits |
| edge fault ID | 9 x 2 bits | 391,320 entries x 17 bits |
| variable pointer | 5 x 32 bits | 67,753 entries, 19 significant bits |
| variable-to-edge | 9 x 4 bits | 391,320 entries x 19 bits |
| nu and mu | each 9 x 18 bits | each 391,320 x 18 bits |
| prior/marginal | each 4 x 18 bits | each 67,752 x 18 bits |
| gamma | 2 x 4 x 5 bits | per-node 5-bit fill for every relay leg |

Required scale-up work:

- Generate check CSR, variable CSR/permutation, priors, and syndrome initialization files from the verified Tier-2 package with hashes and bounds checks.
- Replace register arrays with P=4 banked or packed synchronous memories and explicit valid/ready read responses.
- Widen and formally check every address, row-pointer subtraction, chunk counter, iteration counter, and weight accumulator.
- Preserve partial-word masks at row ends and prevent cross-row reads.
- Add a deterministic hardware RNG/gamma-fill unit for later legs; preloaded gamma is verification-only.
- Add scalable candidate correction output/copy storage instead of hierarchical testbench inspection.
- Stream or sample traces selectively: dumping 391,320 mu and nu values per iteration will dominate RTL simulation runtime.
- Run an intermediate graph before the complete 1,728 x 67,752 model, then perform a small number of Tier-2 shots in a faster compiled simulator.

No N=2 replication or synthesis is part of this readiness step.

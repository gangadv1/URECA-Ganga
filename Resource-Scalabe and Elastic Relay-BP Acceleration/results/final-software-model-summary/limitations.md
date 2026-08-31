# Limitations

- Every access, retry, utilization, and cycle result is produced by a software folding model. No FPGA speedup or measured hardware latency is claimed.
- P=4 is the studied folding point. It has not been shown to be globally optimal relative to P=2, P=8, or other factors.
- BA2 decoder equivalence is established for the canonical Gross [[144,12,12]] memory-Z p=0.003 archive. Generalization to other codes, graph sizes, bases, rounds, or physical error rates remains pending.
- The model assumes its documented address-modulo-4 banking and retry scheduler. Hardware arbitration, routing, pipeline, clock-frequency, and context-storage overheads are outside this result.
- METIS used a limited interface: single scalar degree weighting followed by deterministic exact typed-count rebalancing, not simultaneous four-channel vertex constraints.
- The optional stagnation-priority result is validated only at p=0.003. The p=0.002 and p=0.004 archives lack paired E1 seeds and trajectories.
- Late recoveries show that stagnation is not safe as a hard termination rule.
- F1/F3 refinements were decision studies, not adopted layouts. BA2 remains selected.

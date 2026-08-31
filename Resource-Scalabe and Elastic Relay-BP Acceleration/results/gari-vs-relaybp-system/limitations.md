# Limitations

- GARI uses p=0.001; the Relay-BP archive uses p=0.003.
- The studies do not use a verified identical Stim circuit, DEM, fault space, or shot cohort.
- GARI uses normalized min-sum on an augmented/rewired graph; this repository uses fixed-point Relay-BP on the canonical detector-fault graph.
- The GARI 24-decoder diversity and winner-selection mechanism are not documented in the audited architecture paper.
- GARI latency is FPGA implementation timing. Relay-BP latency is an RTL-calibrated/software folding model, not nanoseconds.
- The combined N=2+BA2 result is derived from fixed archived iterations/legs and phase costs; it is not a new decoder run or hardware execution.
- The 128-shot p99 statistic is screening-level and has very few extreme-tail observations.
- Relay-BP logical counts do not constitute a logical-error-rate curve.
- Relay-BP BRAM equivalents are capacity calculations, not synthesis. They omit legal aspect ratios, packing losses beyond array/bank rounding, port replication, FIFOs, routing, arbitration, and full control storage.
- BA2 permutation maps are counted as optional metadata but are unnecessary at runtime when initialization images are preordered.
- Observable metadata is not part of the current decoder memory fabric; it is counted separately for potential on-device logical scoring.
- No LUT, register, DSP, frequency, power, energy, or measured throughput result exists for the complete Relay-BP system.
- Optional stagnation priority is excluded from the main system and headline numbers.

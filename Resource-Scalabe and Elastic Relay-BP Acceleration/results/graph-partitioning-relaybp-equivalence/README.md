# Partitioned Relay-BP equivalence

Software-only paired invariance study using `reference/relay_bp_fixed.py::FixedRelayBPDecoder` with locked b18/g4/M16 settings. The selected METIS seed-2 ordering is compared with the original graph on four archived p=0.003 trajectories. Gamma vectors are generated once in original mathematical fault order and permuted with the faults, rather than merely reseeding in the new order.

Results: {'EXACT MATCH': 4, 'OUTCOME MATCH BUT TRAJECTORY DIFFERENCE': 0, 'OUTCOME MISMATCH': 0, 'INVALID': 0}. All mapping invariants passed. Relay-BP equations and parameters were unchanged; RTL was not touched. This study establishes ordering equivalence only, not latency or accuracy improvement.

Reproduce with:

```bash
../.venv/bin/python results/graph-partitioning-relaybp-equivalence/run_partitioned_relaybp_equivalence.py
```

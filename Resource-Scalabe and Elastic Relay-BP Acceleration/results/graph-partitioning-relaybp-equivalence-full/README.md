# Full graph-reordering Relay-BP equivalence

Canonical archived N=1 panel: 128 trajectories, four circuit seeds, shots 0--31. Decoder: fixed b18/g4/M16 `FixedRelayBPDecoder`, S=1, R=32. Original gamma vectors are permuted with mathematical faults.

Classification: {'EXACT MATCH': 128, 'OUTCOME MATCH BUT TRAJECTORY DIFFERENCE': 0, 'OUTCOME MISMATCH': 0, 'INVALID': 0}. Trace iterations compared: 24433. Candidate-weight maximum/median absolute deltas: 1.14e-13/0; these are reporting-only with S=1.

No Relay-BP equations, configuration, graph incidences, or RTL were changed. This is equivalence evidence, not a performance claim.

## N=2/E1 extension

E1 classification: {'EXACT MATCH': 128, 'OUTCOME MATCH BUT TRAJECTORY DIFFERENCE': 0, 'OUTCOME MISMATCH': 0, 'INVALID': 0}. Iterations compared: 23303. E1 wins: 33; parallel rescues: 3; all exact. Candidate-weight max/median absolute deltas: 1.14e-13/0.

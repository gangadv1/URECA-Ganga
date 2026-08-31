# BA2 Relay-BP equivalence

Software-only paired validation of the BA2 bank-aware fault permutation against the original canonical graph using locked b18/g4/M16/S1/R32 `FixedRelayBPDecoder`. Gamma vectors are generated in original mathematical fault order and permuted with `fault_new_to_old`.

Pilot: {'EXACT MATCH': 4, 'OUTCOME MATCH BUT TRAJECTORY DIFFERENCE': 0, 'OUTCOME MISMATCH': 0, 'INVALID': 0}. E0: {'EXACT MATCH': 128, 'OUTCOME MATCH BUT TRAJECTORY DIFFERENCE': 0, 'OUTCOME MISMATCH': 0, 'INVALID': 0} across 24,433 iterations. E1: {'EXACT MATCH': 128, 'OUTCOME MATCH BUT TRAJECTORY DIFFERENCE': 0, 'OUTCOME MISMATCH': 0, 'INVALID': 0} across 23,303 iterations. All 33 E1 wins and 3 rescue cases are included.

BA2 edge IDs are storage-only for this decoder; CSR neighborhood order is reconstructed from the fault-permuted H. This is equivalence evidence only, not a decoding, FPGA-latency, or speedup claim.

# BA2 metadata analysis

## Explicit offline representations

| Item | Minimal width | Bits |
|---|---:|---:|
| Fault bank assignments | 2 × 67,752 | 135,504 |
| Edge bank assignments | 2 × 391,320 | 782,640 |
| Fault old→new map | 17 × 67,752 | 1,151,784 |
| Fault new→old map | 17 × 67,752 | 1,151,784 |
| Edge old→new map | 19 × 391,320 | 7,435,080 |
| Edge new→old map | 19 × 391,320 | 7,435,080 |

All four forward/inverse maps total 17,173,728 bits. Separate residue vectors total 918,144 bits.

## Online requirement

None of these full tables is required by the selected decoder fabric. The graph, priors, and message initialization files can be emitted directly in BA2 order. At runtime:

- the bank is `new_address % 4`;
- the residue is implicit in the address;
- adjacency entries already contain reordered IDs;
- inverse maps are needed only to validate or translate outputs in software/debug flows.

BA2 adds no scheduler-group table. Its online metadata cost is therefore zero full permutation arrays in M0–M4. M2's “remove runtime BA2 metadata” is a design rule and prevents a future accidental 17.17-Mbit overhead; it does not claim a reduction from M0, which already used compiled images.

If original fault identities must accompany correction output on chip, translation should be performed after winner selection using a streamed/offline interface or a winner-only map, not duplicated inside both trajectories.

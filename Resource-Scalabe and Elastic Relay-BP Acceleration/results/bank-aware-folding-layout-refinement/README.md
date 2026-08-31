# BA2 fault-residue refinement

This software-only study freezes the validated BA2 edge/message permutation and refines only fault residues using the exact co-access groups induced by that frozen edge order. F1 uses convergence:relay weights 1:1, F2 uses 1:2, F3 uses 2:1, and F4 applies deterministic capacity-preserving swaps to F2. The exact unchanged P=4 scheduler selects `F1` using the declared rule. No syndrome outcome or tail label enters layout construction.

BA2's relay-init regression arose because its original fault co-occurrence surrogate was built before the final edge permutation, whereas relay initialization groups consecutive final edge addresses. All mathematical invariants pass. Fault ordering changes, so decoder equivalence must be revalidated before decoder studies. These are modeled folding costs, not FPGA latency or speedup.

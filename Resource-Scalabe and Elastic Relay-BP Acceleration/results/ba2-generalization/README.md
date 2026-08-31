# Frozen BA2 generalization

The selected out-of-sample target is the non-toy Tier-1 Gross code-capacity graph (144 checks, 288 faults, 864 incidences). It is structurally different from the canonical circuit-level graph; the p=.001-.005 circuit packages are incidence-identical and therefore are not independent topology tests. Frozen BA2 uses weights 5 for variable-message co-access, 3 for convergence, 3 for relay init, balance lambda 0.25, locality lambda 0, deterministic weighted-degree ordering, and P=4. No coefficient was retuned.

Retries decrease from 812 to 213 (73.77%), mean active lanes increase from 1.864 to 2.049, and structural modeled cycles decrease from 15,892 to 14,322 (9.88%). One MU and one NU retry remain, so the canonical zero-variable-retry result is not universal.

This is structural-only validation. The package has no logical-action matrix and its archived panel is canonical float rather than the locked fixed-point decoder, so trajectory weighting and decoder equivalence are not claimed. All available H, probability, incidence, residue, and permutation invariants pass. Results are software-model estimates, not FPGA speedup.

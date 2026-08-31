# Selected analytical memory architecture: M4

## Selection

M4 is the recommended candidate for implementation study:

1. Share immutable graph topology, quantized priors, and syndrome once between E0/E1 using two-read-port storage per logical bank.
2. Compile BA2 directly into initialization images; retain no full permutation/residue tables online.
3. Replace full CSR offset arrays with compact degree tables plus sequential running edge positions.
4. Retain independent per-trajectory marginals, decisions, gamma, RNG, residual, relay, and convergence state.
5. Use one independent 18-bit edge-message store per trajectory, phase-aliased between NU and MU.

## Capacity

- Total: 32,933,564 bits = 3.926 MiB.
- Shared: 15,593,616 bits.
- Duplicated trajectory state: 17,339,948 bits.
- Ideal BRAM36 equivalent: 894.
- Per-array/four-bank capacity equivalent: 925.
- Reduction from M0: 49.087% in bits and 48.611% in the banked-capacity count.

These are analytical capacity values, not synthesis.

## Why M4 is practical rather than merely smallest

M4 preserves two independent dynamic trajectory states. Static sharing needs no more than one read per engine per bank after each engine's P=4 conflict filtering, so a true dual-read memory bank can serve both without serializing them. Phase aliasing follows the existing global check→variable schedule and edge-message lifetimes; it does not recompute messages or reduce precision.

M4 does not claim unproven QC/template compression. That keeps its address generation deterministic and BA2-compatible.

## Required gates before adoption

1. Software lifetime-equivalence oracle for aliased NU/MU across easy, hard, failure, and E1-rescue traces.
2. Address-trace equivalence for degree-table versus CSR-pointer traversal.
3. Cycle model with two independent engines sharing dual-port static banks, proving zero new stalls.
4. Full 256-trajectory mapped equivalence.
5. Only then implement RTL and synthesize to measure actual BRAM packing and Fmax.

If dual-read shared banks cannot be mapped efficiently, fall back to M3 with selectively replicated high-bandwidth static arrays or to M2 without degree-table changes. E0/E1 dynamic state must never be shared.

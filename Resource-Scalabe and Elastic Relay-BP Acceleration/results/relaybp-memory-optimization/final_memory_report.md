# Relay-BP analytical memory-architecture optimization

## Baseline

The current N=2 wrapper instantiates two complete P=4 memory fabrics. Each contains 15,407,678 topology bits and 16,934,998 input/dynamic/control bits, totaling 32,342,676 bits. N=2 therefore stores 64,685,352 bits (7.711 MiB), with 1,800 per-array/four-bank BRAM36 capacity equivalents.

The dominant per-engine arrays are fault-to-edge IDs (7,435,080 bits), MU (7,043,760), NU (7,043,760), and edge-to-fault IDs (6,652,440).

## N=2 sharing boundary

E0/E1 use the same graph, priors, syndrome, and BA2 layout. Those values may be shared read-only if two independent reads per bank are available. MU, NU, marginals, decisions, gamma, RNG, residuals, and convergence/relay state must remain independent because they encode the trajectory diversity responsible for the N=2 tail benefit.

The current wrapper duplicates even static data because it instantiates two engines. M1 shares graph topology; M2 additionally shares prior and syndrome. M2 reaches 48,056,410 bits and 1,336 banked-capacity equivalents, a 25.707% bit reduction.

## Graph metadata

The check and fault index arrays are complementary traversals rather than duplicates. Both large mappings remain necessary for low-latency check- and fault-major access. Full CSR offsets are avoidable because every controller walks nodes sequentially: 8-bit check degrees and 4-bit fault degrees plus running edge positions replace 19-bit offset arrays. M3 reaches 47,021,084 bits and 1,309 banked-capacity equivalents, a 27.308% reduction.

## Message lifetime optimization

NU is consumed by the check phase and replaced conceptually by MU. MU is consumed by the following variable phase and replaced by next-iteration NU. Because phases are globally separated and every edge has exactly one check and one fault owner, a single 18-bit edge store per trajectory can alternate NU→MU→NU in place. No precision or equation changes are required.

M4 removes one E×18 array per trajectory and reaches 32,933,564 bits (3.926 MiB), 894 ideal or 925 banked-capacity BRAM36 equivalents: 49.087% fewer bits than M0.

## BA2 cost

Full minimal-width BA2 forward/inverse maps would occupy 17,173,728 bits and explicit residue arrays another 918,144 bits. They are not runtime requirements. Initialization tooling emits memories directly in BA2 order, and address modulo four supplies the bank. M0 already assumes this compiled representation, so no artificial M2 saving is attributed to deleting absent tables.

## QC/template opportunity

The circuit-level graph retains round regularity: 61,704 faults belong to repeated translation templates and only 12,096 normalized templates exist. However, all 67,752 exact fault signatures are unique, and BA2's global addresses require a template-to-layout translation. No QC saving is credited until a generator reproduces every BA2 incidence and access group exactly.

## Bandwidth and tail behavior

Shared topology/prior banks must supply at most one read per engine per bank after each engine's local P=4 conflict filtering. True dual-read banks can theoretically preserve simultaneous progress. A single-port shared implementation would serialize trajectories and is rejected because it could erase the tail benefit.

M4 retains separate message, marginal, gamma/RNG, decision, and convergence state per trajectory. Its intended first-success semantics therefore remain intact, subject to proving that shared banks add no stalls.

## GARI context

GARI measures 704 BRAM for one core and 2,121 for three cores. M4's 925 value is an analytical two-trajectory banked-capacity equivalent. It is numerically below GARI's three-core count but above its one-core count and omits physical packing, ports, FIFOs, and routing. It does not establish a BRAM advantage.

## Recommendation

Select M4 for the next validation stage because it combines the largest credible reduction with unchanged precision, graph, equations, BA2 mapping, and independent dynamic trajectories. First build a software/address-trace oracle for phase-aliased messages and degree-based traversal, then model dual-port shared-memory contention. Only after full trajectory equivalence should RTL implementation and synthesis be considered.

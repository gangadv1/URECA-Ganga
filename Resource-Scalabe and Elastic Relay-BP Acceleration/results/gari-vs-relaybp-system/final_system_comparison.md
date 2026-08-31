# GARI versus resource-scalable and tail-aware Relay-BP acceleration

## Complete Relay-BP system

The main proposed system combines three independent architectural ideas:

1. **N=2 trajectory parallelism:** E0 and E1 receive the same syndrome and graph but use independent fault-indexed gamma/RNG streams. The first syndrome-valid successful correction wins, reducing exposure to an unlucky hard trajectory.
2. **P=4 folding:** each trajectory time-multiplexes graph work over four reusable processing lanes and four logical memory banks. P is not a trajectory/core count.
3. **BA2 layout:** the graph remains mathematically unchanged, but fault and message addresses are assigned from actual P=4 co-access statistics so simultaneous requests collide less often under `address % 4`.

The decoder is the canonical b=18 fixed-point Relay-BP with a 22-bit variable-sum guard accumulator and M=16 coefficient scale. Optional stagnation-priority scheduling is not part of the main architecture.

## GARI system

GARI changes the correlated X/Y/Z detector-error graph into `D_X,D_Z,U,V` blocks using the repeated-column relationships and change of variables in Section II/Equations (1)–(2). It runs normalized min-sum using a 45-tile serial `D_X,D_Z` unit, an 18-tile parallel `U,V` unit, ROM-controlled memories, and tagged buffered crossbars (Sections III-A–D; Figures 1–5). `D_X,D_Z` share one processing structure, `U,V` share another, and compatible stages overlap.

One core was implemented on VU29P; three complete cores were placed on one VCU19P (Table III/IV, Figures 8–9). A complete 24-decoder ensemble is discussed across eight VCU19Ps. The architecture paper does not document ensemble randomization or winner-selection hardware.

## Latency and tail

The detailed Relay-BP N=1/N=2 screening uses 128 paired p=0.003 shots. N=2 reduces mean modeled cycles by 35.15%, p95 by 35.53%, and p99 by 70.09%, while median is unchanged. E1 wins 33 shots and rescues all three E0 non-convergences. The effect is concentrated in difficult trajectories.

BA2 separately reduces N=1 P=4 modeled mean, p95, and p99 by approximately 15.04–15.05%. Applying the existing layout-specific phase costs to both archived trajectories yields a new combined modeled N=2+BA2 mean of 400,249,878 cycles, p95 of 1,236,224,243, and p99 of 1,875,628,598. Relative to modeled N=1-original, these are reductions of 44.899%, 45.228%, and 74.589%. This is a deterministic model derivation, not FPGA timing.

GARI reports approximately 274 MHz, 14.4 µs average for one decoder, and 7.16 µs over 12 rounds—about 596 ns/round—for a 24-decoder ensemble at p=0.001 (Section IV-H and Section V). GARI reports average latency but does not provide directly comparable p95/p99 tail-latency statistics in the audited paper.

GARI therefore has stronger absolute FPGA latency evidence. Relay-BP has stronger explicit tail-distribution and per-case rescue evidence. No absolute latency winner is established.

## Error correction

Relay-BP N=1 converges and is logically correct on 125/128 shots; N=2 reaches 128/128, with no syndrome-valid logical errors. BA2 preserves all E0/E1 trajectories exactly.

GARI explicitly addresses correlated inference and says its 6/8/10-bit implementation closely approaches float accuracy, but the architecture paper contains no logical-error-rate table or matched shot-level counts. Its p=0.001 setting, transformed graph, normalized-min-sum decoder, and 24-member context differ from Relay-BP's p=0.003 panel.

Accuracy comparison is therefore invalid until both decoders run the same circuit, p, samples, work budget, and logical scoring.

## Memory model

The current P=4 memory fabric stores CSR graph pointers/indices, two 18-bit edge-message directions, 18-bit priors/marginals, a 5-bit active gamma vector, one-bit decisions, and one-bit syndrome. The four banks partition arrays; they do not make four full copies. Previous-leg marginals are reused directly, so canonical Relay-BP has no separate relay-memory array.

One engine requires 32,342,676 modeled bits (3.856 MiB). The current N=2 wrapper instantiates two complete engines, requiring 64,685,352 bits (7.711 MiB). Static data are mathematically shareable but physically duplicated by this wrapper for independent bandwidth.

Using 36,864 bits per BRAM36 gives 878 ideal capacity equivalents per engine and 1,755 for N=2. Separately rounding the actual arrays and four banks gives 900 and 1,800. These values exclude critical implementation effects and are not synthesized BRAM counts.

GARI measures 704 BRAM for one core and 2,121 for three cores. The current analytical model cannot establish that Relay-BP uses less memory. MU, NU, the fault-to-edge permutation, and edge-to-fault metadata dominate Relay-BP capacity.

## P=4 resource-scaling rationale

The P sweep shows why the proposal does not simply maximize lanes:

- P=2 BA2 has 85.58% utilization but is slowest; moving P=2→P=4 reduces trajectory mean by 34.94% with two added lanes.
- P=4 BA2 has 66.78% utilization and is the selected balance point.
- P=8 BA2 is faster, but utilization falls to 49.31%; P=4→P=8 saves only 46.8M trajectory cycles per added lane versus 165.7M for P=2→P=4.

Thus P=4 is supported as a diminishing-returns design point, not proven hardware-optimality.

## Whole-system assessment

- **Average latency:** GARI has stronger measured evidence; direct comparison invalid.
- **Tail latency:** Relay-BP has stronger distribution/rescue evidence; absolute comparison unavailable.
- **Error correction:** no fair winner without a matched workload.
- **BRAM/resources:** GARI has stronger implementation evidence; Relay-BP has only an order-of-magnitude capacity model.
- **Resource scalability:** both reuse computation, but GARI folds transformed matrix blocks while Relay-BP combines trajectory diversity with per-trajectory P folding.
- **Graph flexibility:** Relay-BP/BA2 preserves the original graph; GARI deliberately changes it to improve inference.
- **Bank conflicts:** BA2 uniquely targets the repository's modulo-bank retry bottleneck.

## Research contribution

The complete direction is **resource-scalable and tail-aware Relay-BP acceleration**:

- **MAIN:** fixed-point Relay-BP; N=2 independent first-success trajectories; P=4 folding; BA2 bank-aware layout.
- **SUPPORTING:** METIS negative/control result, P-factor sweep, exact reordering equivalence, memory-capacity audit, and cross-graph BA2 checks.
- **OPTIONAL:** non-destructive stagnation-priority scheduling; it is excluded from the selected architecture.

The defensible story is that trajectory diversity and memory-efficient folding attack different aspects of latency: N=2 reduces difficult-path/tail exposure, while BA2 reduces the cost of executing each fixed trajectory. The repository shows both effects can coexist in a software model without changing tested decoding behavior.

## Recommended experiment

First synthesize the frozen original and BA2 P=4 memory fabrics for N=1 and N=2 on one declared FPGA, without architecture tuning. Record BRAM/URAM, LUT, registers, DSP, Fmax, per-phase cycles, routing failures, and bank-conflict counters. In parallel, obtain or implement a reproducible GARI decoder and run a matched large-shot Gross-code accuracy/tail experiment at common p values. These two steps respectively settle the BRAM/latency and error-correction questions.

# GARI versus BA2/P=4

## Executive conclusion

GARI and BA2 are technically distinct and potentially complementary. GARI changes the correlated detector-error factor graph to improve message-passing inference, then builds specialized FPGA units for the transformed blocks. BA2 leaves the Relay-BP mathematical problem unchanged and optimizes only fault/message storage addresses for a fixed four-bank folding model. The GARI paper contains implemented FPGA results; BA2 contains validated software-model reductions. No latency or resource winner can therefore be declared.

## What GARI does

Section II writes the original correlated X/Y/Z detector matrix in terms of `D_X`, `D_Z`, `D'_X`, and `D'_Z`. Because the Y-error projections repeat X- and Z-syndrome columns, `D'_X=D_XU` and `D'_Z=D_ZV`. Equation (2) changes variables and adds identity/`U`/`V` constraint blocks with zero syndromes. This augmentation and rewiring removes Y-related four-cycles that impair ordinary BP and allows reliability to pass between error domains.

The hardware runs normalized min-sum. A 45-tile memory-based engine serially processes `D_X` and `D_Z`; an 18-tile engine processes independent `U` or `V` checks in parallel. ROM schedules, value/calibration RAMs, FIFO messages, hard decisions, and three tagged buffered crossbars implement the alternating dependency graph. This is specialized temporal reuse of two matrix families—not a uniform P=4 banked graph traversal.

## What BA2 does

BA2 starts from the repository's fixed-point Relay-BP graph: 1,728 detectors, 67,752 faults, and 391,320 incidences at circuit-level memory-Z `p=0.003`. Its mathematical checks, fault priors, logical actions, gamma attachment, and neighborhoods remain unchanged. It derives fault/edge co-access weights from the fixed P=4 scheduler and assigns objects to address residues so co-requested items are less likely to share `address % 4`, with workload balance.

The result is reversible and decoder-equivalent over the tested archive: 256/256 trajectories and 47,736/47,736 mapped iterations match. In the software model, retries fall 336,291→142,566 (−57.606%), structural modeled cycles fall 4,758,697→4,283,590 (−9.984%), and trajectory-weighted mean modeled cycles fall 15.043%. None is an FPGA timing measurement.

## Central graph distinction

- **GARI changes inference connectivity/representation.** It introduces auxiliary variable/check blocks and rewired relationships under a change of variables.
- **BA2 changes storage identity only.** Mapping back recovers exactly the original `H`, `A`, priors, detector incidences, and observable incidences.
- **METIS is not a GARI analogue.** METIS partitioned the existing bipartite graph for locality; GARI algebraically refactors the graph to improve inference; BA2 optimizes access conflicts.

The simplest accurate characterization is: GARI targets BP quality and scalable block structure; BA2 targets modulo-bank scheduling cost under a fixed decoder.

## Folding and memory comparison

GARI reuses one serial unit across `D_X,D_Z` and one parallel unit across `U,V`, overlaps compatible work, and maps variables/checks to tile memories. Variables sharing a serial-unit check must occupy different memories, and the paper uses guided/greedy code-specific mappings. Tagged crossbars handle message redistribution and buffer contention.

BA2 models four reusable lanes and four logical banks, where each address's residue selects its bank and unresolved same-bank accesses retry. BA2 explicitly scores access-group co-occurrence and balances residue work. GARI does not report an equivalent modulo-four co-occurrence statistic, residue assignment, or retry objective. The broad memory-placement problem overlaps, but the bottleneck and heuristic do not.

## Ensemble comparison

GARI fits three complete cores on one VCU19P and projects a 24-core ensemble across eight devices. The architecture paper does not specify core randomizations, winner selection, or ensemble stopping logic, and Section V says full ensemble integration is future work. The cited 1.13 average iterations derives from the earlier GARI study.

The repository's historical N=2 experiment runs two independent Relay-BP trajectories on the same syndrome with distinct mapped gamma/RNG streams; first successful correction wins. That is conceptually ensemble diversity, but it is not demonstrably equivalent to GARI's diversity or arbitration. BA2 itself requires only one static layout and is independent of N=2.

## Benchmark comparability

Both studies use the Gross `[[144,12,12]]` bivariate-bicycle code and 12 syndrome rounds. GARI reports `p=0.001` and transformed blocks `D_X` 792×7920, `D_Z` 936×8784, `U` 7920×51048, and `V` 8784×51048. It does not document an exact Stim circuit, DEM package, complete circuit-noise model, or matched shot cohort in this architecture paper.

BA2 uses a known Stim/DEM circuit-level memory-Z graph at `p=0.003` with 67,752 faults and a fixed archive. Thus the Gross benchmark is **partially comparable**, not directly comparable. A shared code/check count does not equate the variable graph, decoder, noise, or samples.

## Hardware results and comparison limits

For one VU29P core, GARI reports approximately 274 MHz and `10+1728i` cycles. At 2.28 average iterations this is 14.4 µs. For a 24-decoder ensemble, 1.13 average iterations give 7.16 µs over 12 rounds, approximately 596 ns/round; the complete ensemble requires eight VCU19Ps.

Table III gives one core as 122,393 LUTs, 111,697 registers, and 704 BRAMs. Table IV gives three VCU19P cores as 381,698 LUTs, 365,765 registers, and 2,121 BRAMs. DSP count, throughput, and tail latency are not reported. The sixfold claim is eight versus 48 FPGA devices for 24 cores relative to the earlier parallel GARI proposal.

BA2 has no clock, implementation, or resource result. A fair latency/resource comparison requires a clocked BA2 implementation under the same graph, decoder work, precision, stopping/ensemble rule, physical noise, samples, target device, and accounting boundaries. BA2's modeled percentages must not be converted using GARI's frequency.

## Novelty and baseline role

Against this primary paper, the strongest defensible contribution remains **bank-aware folded memory/layout optimization for Relay-BP**. The disclosed GARI architecture does not use simultaneous modulo-bank co-access statistics or optimize address residues for a fixed P=4 retry scheduler. This establishes a mechanism-level distinction, not priority over all prior literature.

GARI is a strong baseline for correlated-error decoding, architecture/resource reuse, multi-core capacity, and concrete memory/crossbar organization. It is a partial baseline for folding and latency because the mechanisms/workloads differ. It is not a matched baseline for BA2's conflict objective, decoder accuracy, or direct resource/performance ranking.

## Recommended experiment

The smallest useful next experiment is a matched software mechanism study before RTL: construct the exact GARI-transformed Gross graph/work schedule (or obtain the authors' machine-readable graph), run the existing GARI mapping and a BA2-style co-access layout on that same schedule without changing normalized-min-sum inference, and compare only conflict/routing/cycle-model metrics. That tests whether BA2's storage principle complements GARI. Hardware latency/resource comparison should wait for a clocked BA2 implementation and matched benchmark protocol.

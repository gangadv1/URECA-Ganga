# GARI primary-source audit

## Bibliographic record

Daniel Báscones, Arshpreet Singh Maan, Valentin Savin, and Francisco Garcia-Herrero, “A Scalable FPGA Architecture for Real-Time Decoding of Quantum LDPC Codes Using GARI,” arXiv:2605.01035v1 [quant-ph], 1 May 2026. The authoritative local PDF is `reference/gari/arxiv_2605.01035.pdf` (SHA-256 `159d3ecffff7c4792c497dd301c8d0b1ebacbb596175c0c2d06a7d4c5726e8ef`).

## Decoder and graph transformation

GARI means **Graph Augmentation and Rewiring for Inference**. Section II starts with a correlated detector-error matrix whose columns are `e_Z`, `e_X`, and `e_Y` error variables and whose rows are `s_X` and `s_Z` detectors. Repeated syndrome components of the Y faults give `D'_X = D_X U` and `D'_Z = D_Z V`. Equation (2) performs a change of variables and introduces additional variable blocks and zero-syndrome check blocks involving identity matrices, `U`, and `V`. The purpose is to remove harmful four-cycles involving Y errors while retaining joint reliability exchange between X- and Z-error domains.

The implemented message-passing rule is normalized min-sum (Section III-B.2). `D_X,D_Z` use a serial/layered schedule, while independent checks within `U` or `V` are parallel. Table I alternates `D_X/U` and `D_Z/V` half-steps, with compatible units overlapped. For the memory experiment, parity is checked only over `D_Z`, so convergence can occur only on even steps (Section III-A). The convergence unit terminates when all checked parities match the syndrome (Section III-B.4).

The paper does not report the normalization factor, maximum-iteration rule, or failure/tie policy.

## Architecture extraction

- `D_X,D_Z` unit: one memory-based serial normalized-min-sum datapath reused for the two blocks, with 45 repeated tiles, value memories, separate calibration memories, FIFO check-message storage, syndrome register/queue storage, ROM-driven scheduling, and hard-decision registers (Sections III-A/B; Figures 1–2; Section IV/Table II).
- `U,V` unit: 18 tiles; checks are independent within each block and processed in parallel, with only one of `U` or `V` active at a time. Parallelism is deliberately sized to fit beneath the serial-unit critical time (Sections III-A/C; Figures 1 and 3; Section IV).
- Interconnect: tagged, buffered, staged crossbars; 45→18 (`D_X,D_Z` to `U,V`), 18→45 (return), and 122→122 (`U↔V`). Tags identify destination memories; FIFOs and ping-pong buffers absorb collisions/back-pressure (Sections III-C/D; Figures 4–5; Section IV).
- Reuse/folding: `D_X` and `D_Z` share the serial unit and alternate; `U` and `V` share their parallel unit and alternate. Processing/routing is overlapped where dependencies permit. This is time/resource reuse, but it is not the repository's P=4 address-modulo-bank retry model.
- Mapping: variables sharing a check must occupy different memories in the serial unit. The paper calls the assignment NP-hard and uses a sufficiently good guided heuristic. `U,V` checks/variables are greedily placed by degree. This is explicit memory/tile placement, but no modulo-four co-occurrence objective or retry scheduler is reported (Sections III-B, III-D, IV-B/H).

## Ensemble extraction

Three complete decoder-core instances fit on one VCU19P, with BRAM as the limiting resource (Section IV-I, Table IV, Figure 9). A complete 24-decoder ensemble therefore projects to eight VCU19P devices rather than the 48 devices of the earlier parallel GARI proposal (Section IV-I and Section V).

The paper motivates ensembles as a way to improve logical error rate and reports average iterations for a single decoder and a 24-decoder ensemble from [20]. It does **not** specify in this paper how core diversity is generated, how a winner is selected, whether winner selection is implemented on FPGA, whether cores stop independently, or whether the three on-device cores alone constitute the reported 24-member decoding experiment. Section V lists integration of full ensemble decoding as future work. Therefore those mechanisms remain unverified here.

## Benchmark extraction

The case study is the Gross `[[144,12,12]]` bivariate-bicycle code and a memory experiment over a window of `d=12` consecutive syndrome measurements (Sections IV and IV-H). Table II gives transformed block sizes:

- `D_X`: 792 × 7920
- `D_Z`: 936 × 8784
- `U`: 7920 × 51048
- `V`: 8784 × 51048

Section IV-H assumes physical error rate `p=0.001`. The paper treats a correlated detector-error model with X, Y, and Z faults, but does not give a complete circuit-noise-channel specification or identify the exact Stim circuit/DEM construction. It reports average iterations (2.28 single; 1.13 ensemble of 24) from [20] and says 6/8/10-bit quantization closely approaches floating-point accuracy; it does not provide a logical-error-rate table in this architecture paper.

Consequently, this benchmark is only partially comparable with this repository's circuit-level memory-Z Stim/DEM at `p=0.003` (1,728 detectors, 67,752 faults, 391,320 incidences). The code and 12-round memory setting align broadly, but graph construction, variable space, physical error rate, decoder, and evaluation cohort do not.

## Hardware extraction

Section IV-H reports `10 + 1728 i` cycles for `i` iterations. A single core is implemented on an AMD VU29P at 3.647 ns (`≈274 MHz`), giving `i·6302 ns + 37 ns`; 2.28 average iterations correspond to 14.4 µs. A 24-decoder ensemble has 1.13 average iterations and 7.16 µs over 12 rounds, or about 596 ns/round. Section V associates this complete ensemble with eight FPGAs, not one three-core FPGA.

Table III reports one VU29P core: 122,393 LUTs, 111,697 registers, and 704 BRAMs, or 7.5%, 3.5%, and 26%. An alternative mapping is 21% RAM plus 5% URAM. Table IV reports three cores on one VCU19P: 381,698 LUTs, 365,765 registers, and 2,121 BRAMs. Section V summarizes this as approximately 9% LUT, 4% registers, and 90% BRAM per three-core device. DSPs, throughput, power, energy, worst-case latency, and latency percentiles are not reported.

The paper claims a sixfold device reduction for the full 24-decoder ensemble: eight VCU19Ps versus 48 devices for the prior fully parallel GARI architecture. This is not a sixfold reduction in each resource counter and should not be restated that way.

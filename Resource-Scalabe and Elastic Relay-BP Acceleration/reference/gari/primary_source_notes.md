# GARI primary-source notes

Authoritative source: Daniel Báscones, Arshpreet Singh Maan, Valentin Savin, and Francisco Garcia-Herrero, “A Scalable FPGA Architecture for Real-Time Decoding of Quantum LDPC Codes Using GARI,” arXiv:2605.01035v1 [quant-ph], 1 May 2026.

Local PDF: `arxiv_2605.01035.pdf`

SHA-256: `159d3ecffff7c4792c497dd301c8d0b1ebacbb596175c0c2d06a7d4c5726e8ef`

## Source map

- Section II, Equations (1)–(2): original correlated detector-error matrix and the GARI change of variables.
- Section III-A, Figure 1, Table I, Equations (3)–(4): two-unit architecture and alternating schedule.
- Section III-B, Figures 2 and 4: serial normalized-min-sum `D_X,D_Z` unit, memories, control, and convergence check.
- Section III-C, Figures 3–4: parallel `U,V` unit and tagged multi-stage routing.
- Section III-D, Figure 5: three decoder interconnects.
- Section IV, Table II: transformed Gross-code submatrix dimensions.
- Section IV-H, Figure 7, Equations (6)–(7): cycle model, clock, average iterations, and latency.
- Section IV-I, Tables III–IV, Figures 8–9: implementation resources and placement.
- Section V: three-core-per-VCU19P result, eight-device projection for a 24-decoder ensemble, and limitations/future work.

## Important interpretation limits

The architecture paper specifies normalized min-sum, the block schedule, and parity-based termination. It does not specify the normalization constant, maximum iteration setting, ensemble diversity mechanism, ensemble winner-selection logic, tail latency, throughput, DSP usage, or a full gate/circuit noise-channel definition. Its `p=0.001`, 12-round average-iteration figures are attributed to the earlier GARI work [20]. Those missing details are not inferred here.

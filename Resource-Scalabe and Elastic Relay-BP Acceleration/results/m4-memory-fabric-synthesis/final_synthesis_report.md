# Final synthesis report

## Outcome

**BLOCKED BEFORE SYNTHESIS — TARGET FPGA AND VIVADO REQUIRED.**

The requested isolated inference study cannot be run reproducibly because the repository supplies no exact part, speed grade/package, board, XDC, or approved clock, and Vivado is not installed. The earlier N=1 Vivado audit reached the same conclusion. The VU29P device mentioned in GARI literature is not a Relay-BP project target and was not adopted.

No RAMB36, RAMB18, LUTRAM, LUT, FF, DSP, warning, collision-mode, packing, replication, WNS, TNS, or Fmax result is claimed. The 980-BRAM36 M4 number remains analytical. Consequently the requested A/B/C/D architecture decision cannot honestly be made from synthesis evidence.

## Prepared work

The standalone RTL remains functionally validated. `synth_m4_matrix.tcl` contains out-of-context full-depth jobs for shared metadata, degree, prior, syndrome, message, marginal, gamma, and decision bank classes. It deliberately fails unless `TARGET_PART` and `CLOCK_PERIOD_NS` are supplied.

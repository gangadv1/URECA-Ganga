# N=1 Vivado baseline — blocked before synthesis

## Decision

**TARGET FPGA REQUIRED**

No Vivado synthesis was launched. The repository does not specify a target board, FPGA/SoC, or exact Xilinx part, and the task explicitly prohibits choosing an arbitrary device.

## Environment inspection

- `vivado` is not present on `PATH`; consequently no Vivado version or installed-device-family inventory can be reported from this host.
- No `.xdc`, `.xpr`, or synthesis `.tcl` file exists in the repository.
- `fpga/synthesis/README.md` is a placeholder stating that synthesis scripts, constraints, outputs, and summaries will be added later.
- `fpga/implementation/README.md` is likewise a placeholder.
- `docs/research_proposal/relay_bp_fpga_research_proposal.md` explicitly lists insertion of the FPGA target device as future work.
- `docs/BLUEPRINT_STATUS.md` states that FPGA/tail results require an FPGA part and toolchain.

## Missing decisions required before synthesis

The supervisor/project owner must provide:

1. Exact Xilinx part number, including speed grade and package (for example, a complete `xc...` part string).
2. Target board or SoC platform, if board-level constraints are intended.
3. Vivado release to use and the machine/environment where it is installed.
4. Intended clock name and target frequency/period. If no frequency objective exists, explicit approval for an exploratory constraint is needed.
5. Whether the first prototype should use synthesis-time initialized Tier-2 graph/prior memories or runtime-loading ports.
6. Any board/project XDC covering the clock pin and clock electrical constraints. For out-of-context core synthesis, confirmation that a virtual/core clock constraint is acceptable is sufficient.

## Consequences

Without an exact part, utilization percentages, BRAM/URAM inference capabilities, timing paths, WNS/TNS, and Fmax would not be meaningful or reproducible. No resource, timing, memory-inference, power, or real-time latency figures have therefore been fabricated.

## Status

- N=1 Vivado synthesis: **FAIL — not run; blocked by missing target and unavailable toolchain**
- Ready to synthesize N=2: **NO**

The next action is to obtain the six items above, install/select the matching Vivado environment, and then create the N=1 out-of-context synthesis Tcl/XDC for the frozen production hierarchy.

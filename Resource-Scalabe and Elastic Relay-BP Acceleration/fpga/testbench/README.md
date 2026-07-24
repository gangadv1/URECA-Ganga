# Testbench

The preserved `tb_parallel_relay.v` covers the older parallel-lane prototype.

The new Blueprint path adds:

- `tb_fixedpoint_arithmetic.sv` — directed separate-`M` memory-mix vectors;
- `tb_fixedpoint_random.sv` — 64 Python-generated memory-mix vectors;
- `tb_node_tiles.sv` — directed fixed-point check/variable node vectors;
- `tb_relay_bp_graph_engine.sv` — a small full-graph folded-engine smoke test.
- `tb_relay_bp_gross_tier1.sv` — end-to-end gross-code tier-1 smoke test using
  generated graph maps.

Run these with a SystemVerilog simulator together with
`fixedpoint_relay_pkg.sv`, `relay_memory_mix.sv`, and (for the graph smoke
test) `relay_bp_graph_engine.sv`. A tier-1 full-graph run additionally compiles
the generated `gross_code_tier1_graph_pkg.sv` and binds its edge arrays.
This folder will contain verification testbenches, stimulus files, and simulation harnesses used to validate the FPGA designs.

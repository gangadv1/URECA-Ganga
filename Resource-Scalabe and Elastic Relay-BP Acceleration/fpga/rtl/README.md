# RTL

The older `.v` files implement the preserved parallel-lane prototype. They are
not the Blueprint's fixed-point gross-code implementation.

The additive SystemVerilog path is:

- `fixedpoint_relay_pkg.sv` — explicit signed rounding and saturation rules;
- `relay_memory_mix.sv` — separate-`M` Relay-memory arithmetic;
- `check_node_tile.sv` / `variable_node_tile.sv` — bit-exact node operations;
- `relay_bp_graph_engine.sv` — functional full-graph sequential folded engine
  that consumes generated edge maps;
- `relay_bp_gross_tier1_top.sv` — tier-1 wrapper that binds generated gross-code maps;
- `relay_bp_folded.sv` — lightweight folded controller with reusable check/variable phases,
  graph-size parameters, relay legs, cycle counts, and trace checkpoints.

Generate `graphs/generated/.../schedule_pc*_pv*/schedule.csv` and
`gross_code_tier1_graph_pkg.sv` with `graphs/schedule.py`. The generated
package supplies the edge maps for `relay_bp_graph_engine.sv`; any tier-2 graph
requires regenerated schedule/config data.

# Existing RTL audit and locked-b18 milestone

## Existing modules

- `relay_engine.v`, `syndrome_dispatcher.v`, `first_success_selector.v`, `convergence_monitor.v`, `output_buffer.v`, and `top_parallel_relay.v` form a behavioral/control-oriented multi-lane prototype. They use small flattened candidates and legacy gamma/carry interfaces, not the Tier-2 sparse b18 datapath.
- `first_success_selector.v` is potentially reusable later as an arbitration concept, but its candidate width/interface must be redesigned for a 67,752-bit memory-backed correction.
- `convergence_monitor.v` only registers externally supplied status; it does not compute H*e_hat.
- `check_node_tile.sv` uses an O(d^2) excluded-edge scan and gives zero for degree one. It is obsolete for the locked check datapath.
- `variable_node_tile.sv` uses a legacy prior+relay-term interface and hard decision `<0`; it is obsolete.
- `relay_memory_mix.sv`, coefficient/beta modules, and golden/Tier-1 engines contain legacy relay-memory/beta or small Tier-1 assumptions and must not be reused as the canonical datapath.
- Existing edge/node memory wrappers are simple single-port scaffolds. Their concepts are reusable, but their widths, depths, P=4 banking, and read latency contracts require replacement/refactoring.
- Existing folded/controller modules are control scaffolds, but their phase ordering and convergence inputs are not the locked Tier-2 schedule.

No legacy RTL was deleted or overwritten.

## New locked modules

- `relay_bp_sat18.sv`: signed saturation to [-131072, 131071].
- `relay_bp_round_div16.sv`: nearest division by 16, ties away from zero.
- `relay_bp_bias18.sv`: exact 16*prior + gamma*(previous-prior) bias numerator with no premature saturation.
- `relay_bp_check_min2_18.sv`: two-minimum check primitive with first-minimum tie behavior and defined degree-one output.
- `relay_bp_variable_node_18.sv`: bias, 22-bit accumulation, marginal, <=0 decision, outgoing nu, and original-prior weight contribution.
- `relay_bp_p4_datapath_shell.sv`: structural four-slot primitive composition. It contains no graph traversal, memories, convergence reduction, relay FSM, or complete decode claim.

The legacy multi-engine files remain side-by-side with these new modules so old test flows are not broken. The locked-b18 filenames deliberately use the `relay_bp_*18` prefix to prevent accidental substitution into legacy tops.

## Missing complete-engine blocks

- Check summarize/emit folded traversal controller for degree up to 242.
- Variable traversal/address controller for degree up to 9.
- P=4 banked memories and graph tables.
- H*e_hat convergence traversal.
- Gamma RNG/fill unit.
- Relay transition and candidate-selection FSM.
- Candidate-weight reduction and correction copy controller.
- Request/result interfaces.

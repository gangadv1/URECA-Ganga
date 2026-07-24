# Blueprint Implementation Status

This file tracks the source-of-truth plan in
`master-proposal/qLDPC_Project_Blueprint.md`. Generated tier-1 outputs are
scaffolding only and must not be presented as circuit-level or post-route
results.

| Work package | Current implementation | Status |
| --- | --- | --- |
| WP0 — provenance and graph | Gross-code package, manifests, tier-1 DEM, shared graph loader | implemented for tier-1 |
| WP1 — Python reference | Exact integer helpers, fixed-point Relay-BP, directed vectors/tests, deterministic float baseline | implemented; canonical-trace audit remains a release gate |
| WP2 — format search | Paired deterministic screening over `b={4,6,8}`, `M={4,8,16}`, shared/separate scale, and float/high-precision controls | implemented for tier-1 screening |
| WP3 — schedule/banking | Deterministic conflict-free edge schedule, machine-readable CSV and summary/manifest | implemented for tier-1 |
| WP4/WP5 — RTL | New SystemVerilog arithmetic, check/variable tiles, full-graph folded engine, tier-1 wrapper, and passing Icarus directed/smoke testbenches added beside legacy `.v` prototype | needs trace-level Python/RTL co-simulation and performance-oriented PC/PV tile replication |
| WP6/WP7 — FPGA/tail results | result/manifest structure exists | requires FPGA part, toolchain, locked formats, circuit-level package, and measured implementation results |

## Reproduce the foundation

From the repository root:

```sh
python3 'Resource-Scalabe and Elastic Relay-BP Acceleration/reference/directed_tests.py'
python3 'Resource-Scalabe and Elastic Relay-BP Acceleration/graphs/schedule.py'
python3 'Resource-Scalabe and Elastic Relay-BP Acceleration/experiments/format_sweep.py'
```

Outputs are written next to their manifests:

- `graphs/generated/gross_code_capacity/schedule_pc8_pv8/`
- `results/format-sweep-tier1/`

## Remaining external gates

The Blueprint deliberately requires evidence that cannot be fabricated in the
repository: a chosen canonical Relay-BP trace for the faithfulness lock, a
circuit-level (tier-2) DEM, and an FPGA target/toolchain for synthesis and
post-route timing/resource results. Icarus Verilog is installed and runs the
current directed and tier-1 smoke tests; a trace-level Python/RTL harness is
the next verification increment.

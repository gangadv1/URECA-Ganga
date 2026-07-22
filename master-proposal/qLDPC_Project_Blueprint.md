# qLDPC Relay-BP Project Blueprint

This is the source-of-truth project plan.

The project is about building a simple, reproducible base for a fixed-point
Relay-BP decoder study. The first goal is not a paper-ready FPGA result. The
first goal is a clean foundation that an undergraduate can run, understand,
and extend.

## One-Line Goal

Build and test a fixed-point Relay-BP decoder for the gross code
`[[144, 12, 12]]`, then compare accuracy, latency, and FPGA cost across a
small set of message widths.

## What We Are Building

The main path is:

1. Build a pinned gross-code graph package.
2. Build a Python fixed-point Relay-BP reference.
3. Verify exact integer arithmetic with directed tests.
4. Export vectors for RTL checks.
5. Build a folded/tiled SystemVerilog engine for the full graph.
6. Compare selected fixed-point formats fairly.

The current repo already contains an older parallel-lane Relay-BP direction.
That work is kept intact, but it is no longer the critical path. It can be
used later as an optional extension.

## Why This Matters

FPGA decoders need to be fast, small enough to fit, and predictable in their
slow cases. Reduced precision can make hardware cheaper and faster, but it can
also change the decoder's behavior.

This project asks a practical question:

> Which fixed-point format gives good Relay-BP behavior while keeping FPGA cost
> and latency under control?

The project does not claim that low precision is new by itself. Prior work has
already shown that reduced-precision Relay-BP can work for the gross code. Our
task is to build a clear, reproducible base and measure the trade-offs in this
implementation.

## Scope

In scope:

- gross-code `[[144, 12, 12]]` experiments;
- fixed-point Relay-BP with exact integer rules;
- a separate integer scale `M` for the Relay memory coefficient;
- Python golden reference for RTL vectors;
- paired comparisons against a floating-point baseline;
- SystemVerilog RTL for a folded/tiled full-graph engine;
- manifests, hashes, and simple result tables.

Out of scope for the first foundation phase:

- publication-grade post-route FPGA claims;
- a fully unrolled IBM-scale decoder;
- a universal decoder for arbitrary qLDPC codes;
- on-chip random generation of relay settings;
- rare-event low-LER studies;
- extending the old parallel-lane ensemble.

## Important Decisions

| Decision | What It Means |
|---|---|
| Use Python as the bit-exact reference | Python generates the integer values that RTL must match. |
| Use a separate memory scale `M` | The Relay memory coefficient does not share the message scale. |
| Start with a tier-1 graph package | Code-capacity scaffolding unblocks software and RTL work. |
| Regenerate for tier-2 | Circuit-level DEM counts, edges, schedules, masks, and vectors will change. |
| Keep old work untouched | Existing simulations, HLS, model files, docs, and `.v` files remain intact. |
| Build additively | New work lives in new folders under `Resource-Scalabe and Elastic Relay-BP Acceleration/`. |

The Python-reference decision replaces the older Rust-reference wording. The
decision log records this explicitly.

## System Shape

```text
syndrome + graph + fixed format
        |
        v
iteration and relay controller
        |
        v
banked graph/message/state storage
        |
        +--> check-node tiles
        |
        +--> variable-node and memory-mix tiles
        |
        v
decision, convergence, and trace output
```

The engine is folded/tiled. This means a small number of processing tiles are
reused across the whole graph. One full graph iteration takes multiple cycles.
Relay legs reuse the same engine instead of duplicating the whole decoder.

## Fixed-Point Rule That Must Not Be Lost

The Relay memory coefficient uses its own scale:

```text
beta_int = round(M * beta)
M = 2^m
```

The memory update is:

```text
y = SAT_b(ROUND((beta_int * y_prev + (M - beta_int) * y_new) / M))
```

This rule is a correctness gate. If the coefficient shares the message scale,
it can round to zero at low precision and remove the intended memory effect.

The implementation must also fix:

- signed integer representation;
- message width `b`;
- guard bits `g`;
- clipping range;
- rounding rule;
- saturation locations;
- iteration and relay-leg settings.

Changing any of these creates a new named configuration.

## Work Plan

### WP0 - Foundation And Provenance

- Record package versions, tool versions, git commit, and source-doc hashes.
- Build the gross-code graph package.
- Keep tier-1 artifacts clearly marked as non-headline scaffolding.
- Save manifests beside generated outputs.

Exit gate: graph package loads, hashes are recorded, and the baseline source is pinned.

### WP1 - Python Fixed-Point Reference

- Audit the current float scaffold before treating it as an oracle.
- Implement integer arithmetic rules.
- Add directed tests for rounding, saturation, endpoints, and check-node cases.
- Export small RTL vectors.

Exit gate: directed tests pass and exported vectors have manifests.

### WP2 - Format Search

- Compare float, high-precision integer, shared-scale fixed point, and
  separate-scale fixed point on the same shots.
- Sweep a small grid: `b in {4, 6, 8}` and `M in {4, 8, 16}`.
- Keep only useful candidates.

Exit gate: a small shortlist of formats is chosen.

### WP3 - Schedule And Banking

- Generate a conflict-free schedule for the selected graph.
- Keep graph sizes parameterized.
- Do not bake tier-1 dimensions into final RTL sizing.

Exit gate: schedule summary and machine-readable schedule exist.

### WP4/WP5 - RTL Units And Full-Graph Engine

- Add new SystemVerilog files beside the old `.v` files.
- Verify arithmetic units first.
- Then verify one full graph iteration.
- Then verify multi-iteration and multi-leg traces.

Exit gate: RTL matches Python vectors and reports cycles per iteration.

### WP6/WP7 - Hardware And Tail Results

- Run synthesis/post-route only for locked formats.
- Report resource use, frequency, cycles, and tail latency.
- Use the measured latency distribution for backlog/deadline checks.

Exit gate: fair tables and plots exist for the chosen comparison.

## Required Comparisons

Core comparisons:

- A0: float vs high-precision integer;
- A1: shared coefficient scale vs separate `M`;
- A2: `b = 4, 6, 8`;
- A3: `M = 4, 8, 16`;
- A4: guard bits;
- A5: tile counts and pipeline depth.

Optional later comparisons:

- mixed precision;
- hard-syndrome sets;
- correlated XYZ or a second circuit;
- old parallel-lane diversity.

## Metrics

Decoder metrics:

- logical error rate convention used;
- convergence rate;
- iterations and relay legs;
- saturation counts;
- failure class;
- latency quantiles: p50, p90, p99, p99.9, p99.99;
- deadline-miss and backlog behavior.

Hardware metrics:

- LUT, LUTRAM, FF, BRAM/URAM, DSP;
- achieved clock frequency;
- timing slack;
- cycles per full graph iteration;
- end-to-end decode latency.

Statistics:

- use identical shots for paired comparisons;
- use McNemar and paired risk-difference intervals for "different" claims;
- use an equivalence margin for "matches float" claims;
- report an upper confidence bound when zero failures are observed.

## Claim Guardrails

Allowed claims:

- the base is reproducible and manifest-tagged;
- the Python reference and RTL match on exported vectors;
- the separate coefficient scale changes represented values as expected;
- selected fixed-point formats have measured accuracy/latency/resource trade-offs.

Do not claim:

- tier-1 code-capacity results are circuit-level headline results;
- final FPGA cost from tier-1 dimensions;
- "four bits is enough" as a new result;
- hardware convergence proves logical correctness;
- publication-grade results before the post-route and circuit-level gates pass.

## Current Repository Direction

New critical-path folders:

```text
configs/        manifests, naming, decision log
graphs/         gross-code graph and DEM packages
reference/      Python fixed-point reference and vectors
verification/   generated vectors and later co-sim checks
experiments/    statistics and latency helpers
results/        manifest-tagged outputs
fpga/rtl/       later new SystemVerilog files
```

Existing parallel-lane work remains as background and optional future work.


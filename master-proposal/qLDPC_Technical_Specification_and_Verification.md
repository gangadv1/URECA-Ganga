# qLDPC Relay-BP Technical Spec And Verification Plan

This document explains what the implementation must do and how we check it.
It is written as a practical build guide.

## Main Contract

The baseline deliverable is a fixed-point Relay-BP engine for the pinned
gross-code graph. It must:

1. process the full graph, not only one arithmetic block;
2. use fixed-point integers for stored decoder state;
3. use a separate integer scale `M` for the Relay memory coefficient;
4. reuse processing tiles across the graph;
5. match the Python reference at named checkpoints;
6. report cycles per full graph iteration;
7. support at least `b = 4` and `b = 8`;
8. expose enough trace data to find the first mismatch.

The first implementation may use the small tier-1 code-capacity graph for fast
testing. Final sizing must wait for the circuit-level graph.

## Configuration Manifest

Every generated result must have a nearby `manifest.json`.

The manifest records:

| Group | Examples |
|---|---|
| Graph | code name, graph hash, detector count, fault count, edge count |
| Circuit | circuit source, rounds, physical error model, physical error rate |
| Decoder | iteration limits, relay legs, gamma policy, seeds |
| Arithmetic | `b`, `g`, `M`, clip, rounding, saturation |
| Architecture | `P_C`, `P_V`, bank counts, schedule version |
| Hardware | FPGA part, tool version, clock constraint |
| Experiment | shot source, stopping rule, metric definitions |
| Provenance | git commit, generated file hashes, source-doc hashes |

Example config name:

```text
gross-xz_b4_g3_M8_clipC_pc8_pv8_sched02
```

The name should be short, but the manifest must contain the full meaning.

## Graph Package

The software reference and RTL schedule must read the same graph package.

A graph package contains:

- detector/check nodes;
- fault/variable nodes;
- edge incidence lists;
- priors or prior-table references;
- logical masks;
- graph and file hashes;
- later, the hardware schedule.

### Tier-1 Package

The tier-1 package is code-capacity scaffolding. It is useful for early
software tests, arithmetic tests, and small RTL traces.

Tier-1 artifacts are not headline experiment results.

### Tier-2 Package

The tier-2 package is the circuit-level DEM for the gross-code memory
experiment with `num_rounds = 12`.

When tier-2 arrives, regenerate:

- detector and fault counts;
- edge lists;
- degree statistics;
- schedules;
- logical masks;
- exported vectors;
- RTL sizing parameters.

Only the loader field names and access functions should stay stable.

## Python Reference

Python is the bit-exact reference for this repo.

It must provide:

- a floating-point baseline path;
- a high-precision integer path;
- shared-scale fixed point;
- separate-`M` fixed point;
- trace export;
- RTL vector export;
- deterministic replay from saved shots and seeds.

Before using it as the final oracle, run the faithfulness check:

- audit the current float decoder behavior;
- confirm the relay-memory update order;
- confirm no random noise enters the reference path;
- compare against the chosen canonical Relay-BP behavior.

A wrong reference that matches RTL exactly is still wrong.

## Fixed-Point Arithmetic

Messages use signed two's-complement integers.

Each format records:

- message width `b`;
- guard bits `g`;
- coefficient scale `M`;
- clipping range;
- rounding rule;
- saturation locations.

Products and sums must be widened before rounding or saturation.

The RTL must not rely on implicit SystemVerilog width or signedness behavior.

### Memory Coefficient

Use:

```text
beta = 1 - gamma
beta_int = round(M * beta)
M = 2^m
```

Then:

```text
mix_num = beta_int * y_prev + (M - beta_int) * y_new
y_mix   = ROUND(mix_num / M)
y_out   = SAT_b(y_mix)
```

Because `M` is a power of two, division can be a signed right shift plus the
chosen rounding adjustment.

Test both:

- shared coefficient/message scale;
- separate coefficient scale `beta_int / M`.

## Decoder Operations

### Check Node

For each check:

1. read incoming variable-to-check messages;
2. compute the min-sum outgoing messages;
3. apply the syndrome sign;
4. apply clipping and saturation;
5. write check-to-variable messages.

Zero magnitudes and signs must match the Python reference.

### Variable Node

For each variable:

1. read prior/state and incoming check messages;
2. add them with guard bits;
3. apply the Relay memory term at the reference-defined point;
4. form outgoing variable-to-check messages;
5. store saturated messages;
6. produce the hard decision used for convergence.

### Relay Memory

For each relay update:

1. compute the new soft state;
2. mix it with the previous memory state using `beta_int`;
3. round and saturate;
4. store the result.

## Hardware Shape

The engine contains:

- check-node tiles;
- variable-node and memory-mix tiles;
- edge-message memory;
- node-state memory;
- coefficient table;
- schedule ROM;
- controller;
- convergence/decision block;
- optional trace counters.

The same engine is reused across relay legs.

The design is folded/tiled. `P_C` and `P_V` choose how many check and variable
tiles are active. More tiles may reduce cycles but cost more area.

## Schedule And Memory Banking

The schedule may be generated offline because the graph is known.

The schedule generator should:

- assign work to tiles;
- avoid unsupported memory conflicts;
- include idle slots when needed;
- preserve reference update order when order matters;
- write a readable summary;
- write a machine-readable schedule file.

Pipeline stages are allowed, but they must not change numerical results.

## External Interface

Exact signal names may change, but the behavior should be clear:

| Interface | Required Behavior |
|---|---|
| Clock/reset | reset behavior is tested |
| Config/graph | identifies graph and arithmetic format |
| Syndrome input | loads one decode problem |
| Control | start, busy, done, optional abort |
| Result | converged flag, decision/correction, iteration and leg counts |
| Trace | enough data to find the first mismatch |
| Counters | active cycles, stalls, tile use, saturation counts |

Converged means the syndrome check passed. It does not by itself prove the
logical correction is correct.

## Verification Levels

| Level | Test | Pass Condition |
|---|---|---|
| V0 | Directed arithmetic tests | exact integer result |
| V1 | Random unit tests | every unit output matches Python |
| V2 | One scheduled graph iteration | every named write matches Python |
| V3 | Multi-iteration and multi-leg decode | same decision, convergence, iteration, and leg counts |
| V4 | Circuit-level paired replay | same per-shot result for chosen RTL/reference config |
| V5 | Post-route check | timing met and function still matches |

When a mismatch occurs:

1. stop at the first different write;
2. record config, cycle, phase, node/edge, operands, and result;
3. reduce it to a small test;
4. fix the reference or RTL;
5. add a regression test.

Do not average over mismatches.

## Directed Arithmetic Tests

Test at least:

- zero, one, minus one, min value, max value;
- coefficient endpoints `0` and `M`;
- one interior coefficient;
- positive and negative half-way rounding;
- sums with and without saturation;
- products near widened limits;
- all-equal check-node magnitudes;
- smallest and second-smallest magnitudes on different edges;
- zero-magnitude sign behavior;
- maximum variable and check degree;
- memory mix endpoints and interior values.

## Experiment Matrix

Core software sweep:

- float;
- high-precision integer;
- shared-scale fixed point;
- separate-`M` fixed point;
- `b = 4, 6, 8`;
- `M = 4, 8, 16`;
- useful clip and guard-bit settings.

Core hardware sweep:

- at least `b = 4` and `b = 8`;
- shared vs separate coefficient scale;
- at least one feasible `P_C/P_V` setting;
- post-route results for the headline points.

## Metrics

Accuracy:

- block/logical error convention used;
- convergence rate;
- wrong-coset rate when logical masks are available;
- non-convergence rate;
- paired confidence intervals.

Latency:

- full-graph cycles per iteration;
- end-to-end decode cycles;
- p50, p90, p99, p99.9, p99.99;
- backlog/deadline-miss behavior.

Hardware:

- LUT, LUTRAM, FF, BRAM/URAM, DSP;
- achieved frequency;
- timing slack;
- tile utilization;
- saturation counters.

Statistics:

- use identical shots for paired comparisons;
- use McNemar and paired risk-difference intervals for difference claims;
- use an equivalence margin for "matches float" claims;
- report an upper confidence bound for zero observed failures;
- avoid low-LER claims without enough failures or a validated rare-event method.

## Acceptance Gates

G0: graph package exists, loads, and has hashes.  
G1: fixed-point directed tests pass.  
G2: Python reference is faithfulness-checked before headline vectors.  
G3: exported vectors have manifests and source-doc hashes.  
G4: RTL unit tests match Python vectors.  
G5: full-graph RTL traces match Python.  
G6: selected hardware builds meet timing.  
G7: final comparisons use pinned settings and paired shots.

## Repo Layout

Expected folders:

```text
configs/        manifests, naming, decision log
graphs/         graph builders, generated graph packages
reference/      Python fixed-point reference and vector export
verification/   vectors and later co-sim checks
experiments/    paired stats and latency helpers
results/        manifest-tagged outputs
fpga/rtl/       later new SystemVerilog files
```

Existing parallel-lane files are kept as background and optional future work.

## Open Items

These are not blockers for the first foundation pass:

- final circuit-level DEM builder;
- logical masks for headline logical-error results;
- final rounding tie rule if changed from the current Python helper;
- final clip choices;
- schedule generator and bank assignment;
- full SystemVerilog engine.


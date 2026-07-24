# Decision Log

This file records small changes from the proposal documents.

## 2026-07-22 - Python Reference Instead Of Rust

The proposal names Rust as the bit-exact reference language. For this repo,
the first reference implementation will be Python.

Reason:
- the existing decoder scaffold is already Python;
- Python is easier for this project stage;
- the important requirement is exact integer behavior, not the language.

Boundary:
- Python is the internal golden model for RTL vector matching.
- External correctness still depends on reproducing the floating-point baseline
  and the pinned gross-code experiment.

Superseded proposal lines:
- `qLDPC_Technical_Specification_and_Verification.md`, line 5;
- `qLDPC_Technical_Specification_and_Verification.md`, line 87.

## 2026-07-22 - Current Float Decoder Is A Scaffold

The current Python float decoder is useful, but it is not treated as final
canonical Relay-BP behavior yet.

Before exporting headline vectors, check:
- the belief restore around outgoing messages;
- the memory update cadence between relay legs;
- no random noise term leaks into the reference path.

The HLS file is only used as a shape guide for the four main operations. Its
small graph size and `/255` carry update are not the target arithmetic.

## 2026-07-22 - Tier-1 DEM Is Scaffolding

The first DEM package is code-capacity scaffolding. It keeps the same loader
contract that later code should use, but the real circuit-level graph will
regenerate counts, edges, schedules, masks, and vectors.

## 2026-07-24 - Faithfulness Verdict Is Computed, Not Hardcoded

The faithfulness check status is now derived from the checks. If any check
fails, the report marks `all_passed: false` and the script exits non-zero. The
audit is still a scaffold gate; a manual canonical trace-lock is still required
before headline vectors.

## 2026-07-24 - Shared-Scale Control For The Memory Coefficient

`FixedConfig` gains `separate_scale`. The separate-scale design uses the
independent power-of-two `M`. The shared-scale control ties the coefficient to
the message scale `2**(b-1)`, so its resolution shrinks with `b`. This gives the
shared-vs-separate coefficient ablation (A1) the proposal requires. Default is
`separate_scale=True`, so existing tests and exported vectors are unchanged.


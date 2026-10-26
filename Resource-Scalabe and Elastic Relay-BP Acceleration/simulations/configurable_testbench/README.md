# Configurable circuit-level Relay-BP software testbench

From the project directory:

```sh
../.venv/bin/python -B simulations/configurable_testbench/testbench.py \
  --config simulations/configurable_testbench/smoke_config.json \
  --output simulations/configurable_testbench/runs/first_smoke
../.venv/bin/python -B -m unittest discover \
  -s simulations/configurable_testbench -p test_testbench.py -v
```

Outputs must be fresh directories, either external or under this new testbench.
Historical runners/packages are read only. JSON fields match `Config` exactly;
paths are relative to the invocation directory. The example is a one-shot wiring
smoke test with deliberately tiny iteration budgets, not a performance result.

Select `code` from 18_4_3, 72_12_6, 144_12_12, 288_12_18. Optionally set
`package` to an existing validated Tier-2 package directory, `physical_p` and
`source_circuit` (must match the packaged circuit hash). Defaults use existing
_bb*_test packages for the non-Gross codes: these packages are currently
untracked dependencies and should be preserved with their manifests. For other
physical probabilities select an existing corresponding package; no probability
rescaling or package generation occurs. All dimensions come from package data.
The Gross-only algebraic generator and dense Tier-1 loader are not used.

Configure N, P, shots, shot_offset, first_limit, later_limit, R/S, sample_seed,
trajectory_base_seed or explicit `engine_seeds` of length N. Explicit seeds are
reused across shots. Otherwise the canonical splitmix recurrence derives engine
streams from sample seed and absolute shot index. Gamma uses the canonical
xorshift64 encoded distribution, first gamma .125, fixed b18/g4/M16 arithmetic.

Sample modes:
- `circuit`: fresh circuit detector/observable sampling with a fixed seed.
- `package`: saved circuit samples; requires exact archived seed and enough shots.
- `canonical_paired`: exact hash-locked Gross multiseed sample archive, for regression.

The decoder receives only H, prior probabilities/LLRs and detector syndrome.
Logical action A and observed logical labels enter scoring after decoding. True
fault labels are never loaded as decoder inputs. Total failure is nonconvergence
plus syndrome-valid logical error; each component and total have Wilson 95% CIs.
Winner/per-engine iteration and leg distributions accompany per-shot and
per-engine CSVs. Full independent trajectories are simulated to score the race;
their full iteration statistics are not cancellation-truncated execution counts.

Timing models:
- `canonical_p4`: locked Gross incidence/P4/S1 phase calibration and original
  controller/RNG overhead formula. Other graphs or S values are rejected.
- `folding_original`: archived service formulas on the selected sparse graph,
  original CSR edge ordering and modulo-P banks, P=2/4/8. Phase cycles, requested
  accesses, retries, issued-group occupancy and full-P fraction are available.
  This is extrapolated software modeling, not multi-BB RTL calibration. RNG and
  top-level controller overhead are excluded; S>1 uses complete decoder runtime.
  BA2 permutations are graph-specific and are not transplanted between codes.

The first syndrome-valid eligible decoder completion wins; smallest index wins
ties. All-fail waits for the last engine. Logical correctness does not choose
the winner. R/S are reference semantics (up to R legs, target S solutions); a
valid result on exhausting R can still be returned with fewer than S solutions.
No loser acknowledgement/drain latency is guessed or folded into result latency.
Exact cancellation-aware work, elapsed-cycle PE utilization and measured FPGA
latency are null. Natural work and provisioned N*P*completion lane cycles are
separate; no shared processing pool or N-trajectory memory arbitration is modeled.

Provenance records configuration, package/source hashes, implementation hashes,
versions, base Git commit, input/output labels and RNG seeds. Very small samples
are smoke evidence only; their failure rates are not meaningful LER estimates.

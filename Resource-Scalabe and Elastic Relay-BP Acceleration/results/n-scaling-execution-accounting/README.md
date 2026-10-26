# Archived N-scaling execution accounting

Run `python3 -B results/n-scaling-execution-accounting/analyze_execution.py`
from the project directory. It reads existing CSVs only, performs no decoding,
and refuses to overwrite its output directory. Use `--output` for a fresh path.

All quantities are software-modeled cycles, never measured FPGA work.

- `ensemble_completion_cycles`: unchanged canonical first syndrome-valid
  completion; lowest engine index wins ties. All-fail waits for the last result.
- `uncancelled_natural_work`: sum of complete independent engine runtimes;
  includes initialization, RNG, controller and memory wait time. It is the
  canonical N-scaling `active_work`, not historical N2 cancellation-aware work.
- `provisioned_lane_cycles`: N * P * ensemble completion cycles, assuming
  dedicated lanes. This is capacity through selection, not useful operations
  or capacity through safe reuse.
- `cancellation_aware_executed_work`: null. Archive totals cannot establish
  phase positions, cancellation acknowledgement, issue occupancy or drain.
- `executed_engine_elapsed_cycles_*_bound`: summed engine execution envelopes,
  including waits, through stop. The lower bound clips unresolved losers at
  selection; this clipping is NOT exact busy work or useful work.
- `executed_phase_controller_cycles_*_bound`: occupancy of check, variable,
  convergence and relay controllers, including their waits/retries. Natural
  occupancy B is iterations * (check + variable + convergence) + legs * relay.
  With natural runtime T and earliest possible stop s, unknown placement gives
  max(0, B - (T-s)) <= executed occupancy <= B. Completed engines/winner retain B.
  Arithmetic-active cycles and useful issued lane operations remain unknown.
- Quiescence/overhead bounds include winner completion after candidate-valid.
  They are NOT cancellation/drain timing measurements. Exact acknowledgement
  and drain fields remain null.

Bounds require simultaneous launch, independent engines, no added stalls and
stop/quiescence no later than natural completion. No maximum-phase drain time
or invented request delay is used. These assumptions are not an N>2 RTL proof.

RTL latches cancellation, drains check/variable/convergence/initialization to a
safe phase boundary, can abort gamma loading, and exposes acknowledgement and
quiescence separately. Natural archive totals do not record these event times.
Exact reconstruction needs per-engine phase entry/exit timestamps, request and
acknowledgement cycles, outstanding-response/RNG drain and quiescence, plus
issued lane masks, useful operation and wait counters. Decoder iteration hooks
observe mathematical states, not these hardware events.

Compare N8/N16 on paired shots using unchanged latency, natural runtime sum,
provisioned capacity and execution bounds. Overlapping bounds cannot establish
which ensemble executes less useful work. Memory contention/shared pools and
energy are outside this accounting model.

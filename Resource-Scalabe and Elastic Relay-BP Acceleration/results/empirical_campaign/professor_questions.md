# Professor's Questions — Answered with Numbers

## Q1. What proves METIS improves locality?
METIS reduced the archived balanced edge-cut ratio from 74.9532% for random to 10.4472% for the selected limited run, with 40,882 cut edges on 391,320 incidences. This is partition quality evidence, not proof of bank locality. In the P=4 access model, METIS node-only instead increased retries by 2.222% and modeled structural cycles by 0.471% versus original, so graph edge cut did not translate into this memory-locality objective.

## Q2–Q3. Why P=4, and what about P=8?
The archived original-layout model has 7,205,045, 4,758,697, and 3,198,386 structural cycles at P=2, 4, and 8. Lane utilization is 80.037%, 60.272%, and 44.077%. Thus P=8 lowers modeled cycles but uses twice the lanes/banks of P=4 and has lower utilization. This supports P=4 only as a documented resource/utilization trade-off; it does not prove global optimality.

## Q4. Proposed architecture versus base Relay-BP
The strongest archived software-model result is BA2: P=4 structural cycles 4,758,697 to 4,283,590 (-9.984%) and trajectory-weighted modeled mean 726,388,133 to 617,117,727 (-15.043%), with exact archived equivalence. These are software-simulated/model results, not FPGA timing.

## Q5. GARI comparison
GARI values in this package are literature-reported and not matched. The local audit found no verified public GARI software reproduction run. Direct latency/resource ranking is therefore unavailable.

## Q6. How much memory is saved?
The M4 validation stores 32,933,564 bits (3.926 MiB) and reports 894 ideal or 925 four-bank BRAM36-equivalent capacity; these are analytical estimates. They are not measured FPGA BRAM.

## Q7. Cycles/operations
P-cycle distributions are available in `p_scaling/trajectory_results.csv`. The operation table is explicitly analytical and structural: 391,320 incidences per check/variable message direction and 4*391,320+1,728 = 1,567,008 operations in the stated proxy; it is not an instruction-level profiler.

## Q8–Q9. RTL and FPGA
The standalone M4 RTL run reports 16,506 trace matches, zero mismatches, zero assertion failures, zero dropped/duplicated requests, and 706 same-address dual reads. Full Relay-BP RTL integration is false. FPGA synthesis is blocked because Vivado and target part/constraints are unavailable.

## Q10. Evidence classes
See `evidence_matrix.csv` and `experiment_manifest.csv`.

## Explicit limitations
The available LER run is bounded: 512 shots at p=0.001–0.003, 272 at p=0.004, and 256 at p=0.005; p=0.005 includes 19 logical failures and 19 non-convergences. N=4, a complete 3x3 factorial, a 10,000-shot campaign, instruction-level operation distributions, COACCESS-GREEDY, matched GARI software, and FPGA synthesis remain blocked or not yet measured.

## Todo 3/4 additions

- The smallest baseline study ran 64 paired Tier-1 shots. Standard BP converged on 59/64 (92.1875%), uniform-memory BP on 64/64, and Relay-BP on 64/64 with mean 22.109375 iterations and 3.03125 relay legs. Tier-1 logical scoring was unavailable, so these are convergence results only.
- The recovered N=4 archive contains 640 paired cases per N. Relative to N=1, N=2 reduced mean modeled iterations by 20.3654% and N=4 by 30.1935%; N=4 reduced p99 by 70.1850% but had one syndrome-valid logical error versus zero for N=1/N=2 in that archive. This is a P=4 timing model, not a new joint N×P factorial.
- Selected METIS seed 2 has 40,882 cut incidences, 1,356 boundary checks, 23,432 boundary faults, and 24,905 distinct cross-partition endpoint references. These communication/interface numbers are separate from edge cut and do not establish bank-locality improvement.
- P transitions are quantified in `p_scaling/p_transition_summary.csv`: P=2→4 reduces modeled cycles by 33.9564% while utilization falls 19.7654 percentage points; P=4→8 reduces cycles by 32.7825% while utilization falls another 16.1945 points. Each transition doubles lanes/banks. Therefore P=4 is a resource/utilization choice supported by these numbers, not a latency optimum.

# Empirical Campaign Summary

## Status
**PARTIALLY COMPLETE.** The package contains verified archived software/analytical/RTL evidence and newly normalized CSVs/plots. It does not claim completion of every requested experiment.

## Environment
Isolated `.venv`: Python 3.13.6, NumPy 2.2.6, SciPy 1.15.3, STIM 1.15.0, PyMatching 2.3.1, Matplotlib 3.10.7, PyMetis 2025.2.2; arm64 macOS; commit `ecf279a9f443a0b900a6411191bcb650e3dff3d2`. Icarus is available; Vivado is unavailable.

## Completed/recovered
- P=2/4/8 folding structural and trajectory distributions.
- Original, METIS variants, BA1/BA2/BA3 heuristic comparison.
- Bounded p=0.001–0.005 LER table with Wilson bounds and long-tail metadata.
- N=1/N=2 archived first-success comparison.
- M4 analytical memory/equivalence evidence.
- M4 standalone RTL simulation.
- GARI literature comparison with non-comparability labels.

## Main numerical findings
- Original P=2/4/8 modeled cycles: 7,205,045 / 4,758,697 / 3,198,386.
- Original P=2/4/8 utilization: 80.037% / 60.272% / 44.077%.
- BA2 at P=4: 336,291 to 142,566 retries (-57.606%); 4,758,697 to 4,283,590 structural cycles (-9.984%).
- METIS cut: 10.4472% selected versus 74.9532% random balanced, but METIS node-only increased P=4 modeled retries/cycles.
- Bounded LER: p=0.005 observed 19/256 = 0.07421875; p=0.001–0.004 had zero observed logical failures in the archived bounded samples, so upper bounds are reported in CSV.
- M4 RTL: 16,506 matches, zero mismatches/assertions/dropped/duplicated requests.

## Blocked/not yet measured
N=4 and complete N×P factorial, complete 10,000-shot LER points, instruction-level operations, COACCESS-GREEDY, matched GARI software, full integrated Relay-BP RTL, and FPGA synthesis/timing/resource measurements.

## Todo 3/4 completed additions
- Small baseline run: standard BP converged on 59/64 shots, uniform-memory BP on 64/64, and Relay-BP on 64/64; Relay-BP mean was 22.109375 iterations and 3.03125 relay legs. Logical scoring was unavailable for this Tier-1 package.
- N=4 was recovered from the archived 640-case-per-N parallel trajectory model: mean iteration reduction versus N=1 was 30.1935%, p99 reduction was 70.1850%, and one syndrome-valid logical error occurred among 640 N=4 policy cases. This is not a new N×P factorial measurement.
- Selected METIS seed 2 communication metrics: 40,882 cut incidences, 1,356 boundary checks, 23,432 boundary faults, and 24,905 distinct cross-partition endpoint references. Communication volume remains distinct from edge cut and bank locality.
- P transition arithmetic: P=2→4 reduces modeled cycles by 33.9564% while utilization falls 19.7654 percentage points; P=4→8 reduces modeled cycles by 32.7825% while utilization falls another 16.1945 points. Each transition doubles lanes/banks. See `p_scaling/p_transition_summary.csv`.

## Todo 3/4 status
The smallest runnable software/RTL studies are complete or recovered: baseline, N=4, METIS communication metrics, P-scaling, BA2, bounded LER, M4 software validation, and M4 RTL simulation. Todo 3/4 is **complete with explicit limits**, not a claim that the full campaign is complete. A matched N×P factorial, instruction-level profiler, public GARI software run, full LER target, integrated Relay-BP RTL, and FPGA synthesis remain before the final PDF.

## Provenance
Every normalized table points to its source artifact in `experiment_manifest.csv`; claim-level traceability is in `evidence_matrix.csv`. Analytical BRAM and operation values are not hardware measurements.

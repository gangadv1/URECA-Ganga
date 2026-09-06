# M4 standalone RTL memory-fabric report

Representative parameterized shared-TDP, private 1R1W, aliased-message, and phase-controller RTL was simulated at one- and two-cycle read latency. Each mode returned 8,207/8,207 tagged shared-memory responses exactly; the combined trace contains 16,506 exact comparisons. The directed NU_old -> MU -> NU_new sequence returned 12/12 reads per mode with zero semantic or phase hazards. Deterministic stress ran 5,000 cycles per mode, including 2,356 same-bank and 704 same-address dual-read cycles.

The frozen cycle-model file contains 16 run-length templates spanning all four phases and 41,206,386,498 archived group occurrences. RTL replay tests representative instances of every protocol class rather than expanding that 41.2-billion-occurrence workload.

Simulation timing agrees exactly for all tested requests. Synthesis was not executed because no Yosys or Vivado executable is installed. Consequently the 980-BRAM36 port-aware packing estimate remains unconfirmed, and memory inference is the principal remaining risk before full decoder integration.

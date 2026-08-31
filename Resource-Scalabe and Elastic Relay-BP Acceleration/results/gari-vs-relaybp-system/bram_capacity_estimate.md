# Relay-BP analytical storage and BRAM-capacity estimate

## Counting basis

The model follows the instantiated arrays in `fpga/rtl/relay_bp_memory_fabric_p4.sv` at C=1,728, V=67,752, E=391,320, P=4. Address widths are the RTL `clog2` values: 17-bit fault IDs, 19-bit edge IDs/pointers. Stored messages, priors, and marginals are 18 bits; gamma is 5 bits; decisions and syndromes are one bit. The 22-bit guard accumulator is an arithmetic/controller register, not a V- or E-length stored array.

One engine contains 15,407,678 static-graph bits and 16,934,998 trajectory/input/control bits, totaling 32,342,676 bits = 3.856 MiB. The current N=2 wrapper instantiates two complete memory-backed engines, totaling 64,685,352 bits = 7.711 MiB.

Although graph structure, priors, and syndrome are mathematically shareable, the current wrapper physically duplicates them to give both engines independent ports. A hypothetical perfectly shared static graph would reduce N=2 to 49,277,674 bits = 5.874 MiB, but that is not the current architecture and could require replication to meet bandwidth.

## BRAM36-equivalent calculation

Using 36,864 usable bits per AMD/Xilinx BRAM36:

| Scope | Stored bits | Ideal `ceil(total/36864)` | Per-array/four-bank capacity sum |
|---|---:|---:|---:|
| One P=4 engine | 32,342,676 | 878 | 900 |
| Current N=2 wrapper | 64,685,352 | 1,755 | 1,800 |
| Hypothetical N=2 with perfectly shared static graph | 49,277,674 | 1,337 | Not claimed |

“Per-array/four-bank” separately rounds each bulk RAM and each of its four banks to a BRAM36 capacity. It still ignores legal width/depth modes, dual-port constraints, replication, FIFO storage, and place-and-route effects. It is therefore conservative relative to pure total-bit division but not a synthesis estimate.

## BA2 and observable metadata

BA2 forward/inverse maps contain 17,173,728 minimally encoded bits, but they need not reside in decoder hardware: build-time tooling can emit graph and state initialization images directly in BA2 order, and runtime bank selection is simply the address residue. Storing all maps on-chip would add 466 ideal BRAM36 equivalents.

Sparse observable-scoring metadata would add 1,595,685 bits or 44 ideal BRAM36 equivalents. It is currently used by host/offline logical scoring rather than the P=4 decode fabric.

Including current N=2 storage, all forward/inverse BA2 maps, and observable metadata gives 83,454,765 bits = 9.949 MiB = 2,264 ideal BRAM36 equivalents. This is an optional system-debug/configuration scenario, not the selected datapath storage requirement.

## Dominant storage

For each engine, the largest objects are:

- MU messages: 7,043,760 bits
- NU messages: 7,043,760 bits
- fault-to-edge permutation: 7,435,080 bits
- edge-to-fault IDs: 6,652,440 bits

These four arrays account for most capacity. P=4 partitions them into banks; it does not replicate each complete array four times.

## Interpretation against GARI

GARI measures 704 BRAM for one core and 2,121 BRAM for three cores. Relay-BP estimates 900 per-array/banked equivalents for one engine and 1,800 for N=2. The N=2 estimate is numerically 15.1% below GARI's measured three-core count, but that margin is not large enough to survive unknown packing, port, FIFO, routing, and implementation overhead confidently. Conversely, one Relay-BP engine's estimate already exceeds GARI's measured 704 BRAM/core.

Therefore the analytical result does **not** establish lower BRAM use. It does show that a complete N=2 folded design is in the same order of magnitude and motivates synthesis, with graph/message storage optimization as a priority.

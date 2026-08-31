# GARI architecture notes

## Plain-English explanation

Ordinary BP on a correlated X/Y/Z detector graph can repeatedly circulate nearly the same information around short four-cycles created by Y faults. GARI refactors that detector model: duplicated X- and Z-syndrome patterns are represented through `U` and `V`, and auxiliary variables/check equations let the two domains exchange reliability without retaining those harmful short cycles. The resulting problem is mathematically related by a change of variables, but its factor graph is structurally different from the original detector-fault graph.

The FPGA follows that block structure. One memory-based serial engine is reused for `D_X` and `D_Z`; another moderately parallel bank of tiles is reused for `U` and `V`. Tagged, buffered crossbars move extrinsic information between the units. Three whole decoder cores fit on one VCU19P, while the 24-member ensemble timing cited from the GARI study would use eight such devices.

## Schedule and dependencies

The schedule in Section III-A/Table I is:

1. Serial `D_X`, then parallel `U` while compatible work overlaps.
2. Serial `D_Z`, then parallel `V` while compatible work overlaps.
3. Repeat, exchanging `D_X→U`, `D_Z→V`, `U→(V,D_X)`, and `V→(U,D_Z)` information.

Only one of `D_X,D_Z` occupies the serial engine at a time, and only one of `U,V` occupies the parallel engine at a time. For memory-Z-style convergence, all `D_Z` parity checks are evaluated in parallel and convergence is possible on even schedule steps.

## Datapath and storage

The serial unit has 45 tiles. Each tile owns value RAM, calibration RAM, buffered check-to-node messages, arithmetic around a normalized-min-sum CNU, and hard-decision state. Syndrome information is held in a register file for convergence and a circular queue for processing. ROM tables select the current block, check membership, memory indices, masking, and hard-decision write enables.

The `U,V` unit has 18 tiles, each receiving up to 500 variables from each serial block. Its reported tile degrees are `(23,17,13,11,11,11,7,7,7,7,7,7,7,7,5,5,3,3)`. Incoming messages and destination tags feed passive parallel processing and staged routing.

## Crossbars and collisions

Three tagged networks are reported: 45→18, 18→45, and 122→122. The `U↔V` network performs a binary-radix-like, `ceil(log2 J)` staged sort. FIFOs at the ends and ping-pong buffers internally absorb back-pressure; dual ports reduce collisions. The paper observes small routing conflicts and approximately 10–20% routing overhead on serial-to-parallel transfers, about 20% for `U↔V`, and about 10% for parallel-to-serial return.

This is not equivalent to BA2's bank rule. GARI routes tagged messages to mapped tile memories and tolerates network contention. BA2 chooses each fault/message address residue specifically to reduce same-group conflicts under `address % 4`, then measures retry subsets in a fixed four-lane issuer.

## Folding/resource reuse classification

GARI uses **block-specialized temporal reuse**:

- one serial datapath for both `D_X` and `D_Z`;
- one parallel tile array for both `U` and `V`;
- overlap across dependency-compatible block pairs;
- memories and crossbars sized from a code-specific placement heuristic.

BA2/P=4 uses **uniform lane/bank folding plus static address placement** over an unchanged Relay-BP graph. Both seek efficient message passing and both map graph objects into memories, but their mathematical inputs, schedules, conflict models, and optimization targets differ.

## Ensemble limitation

“Three cores” is a physical capacity result, not a complete description of ensemble inference. This paper does not say what differs between the cores or how their outputs are arbitrated. Its 1.13-iteration/596-ns-per-round number is associated with a 24-decoder ensemble from [20], while Section V says integration of full ensemble decoding remains future work.

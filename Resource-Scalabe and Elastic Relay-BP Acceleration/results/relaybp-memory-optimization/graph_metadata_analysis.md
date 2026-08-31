# Graph-metadata redundancy analysis

## Current representation

The runtime fabric stores both traversals of the same 391,320 incidences:

- Check CSR: `check_row_pointer` plus check-ordered `edge_to_fault`.
- Fault CSR/reverse traversal: `fault_row_pointer` plus fault-ordered `fault_to_edge`, whose values are IDs in check-edge order.

The two large index arrays are not simple duplicates. `edge_to_fault[e]` identifies the mathematical fault at check-ordered edge `e`; `fault_to_edge[position]` maps a fault-ordered adjacency position back to that edge's message slot. Removing either without another address-generation mechanism would prevent one traversal or require an E-scale scan.

## Safe offset compaction

The existing check, variable, convergence, and relay-init controllers visit checks/faults monotonically. They do not require arbitrary CSR row lookup during a phase. A running 19-bit edge position plus the current node degree can therefore regenerate each start/end range.

Actual degree bounds are:

- Check degree: 51–242, requiring 8 bits.
- Fault degree: 1–9, requiring 4 bits.

Replacing `(C+1)×19` check offsets and `(V+1)×19` fault offsets with `C×8` and `V×4` degree tables reduces shared storage from 1,320,158 to 284,832 bits, saving 1,035,326 bits. This is M3. It requires controller/address-generator equivalence testing but does not change adjacency, edge order, or equations.

## Unsafe or uncredited removals

- Deriving fault adjacency by scanning the check CSR is functionally possible but has unacceptable O(EV) access cost and would destroy independent progress.
- Reordering into fault-major order only swaps which traversal needs a reverse map.
- Delta/entropy compression of edge IDs would add variable-rate decode logic and unpredictable access latency; it is not credited.
- Eliminating `edge_to_fault` would require a different convergence and relay-init schedule. It is not claimed safe here.

## Scheduler metadata

No separate P=4 group table is stored. Controllers form groups from sequential CSR positions and P, so there is no scheduler table to remove.

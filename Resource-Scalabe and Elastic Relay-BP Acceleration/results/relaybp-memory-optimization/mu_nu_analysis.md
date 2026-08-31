# MU/NU storage analysis

## Semantics

- `NU[e]` is the fault-to-check message consumed by the check update for edge `e`.
- `MU[e]` is the resulting check-to-fault message consumed by the variable update.
- The variable update computes the fault aggregate from all incident MU values and emits the next NU value for each incident edge.

Both are signed 18-bit values in the locked decoder. Reducing their width would change the validated arithmetic and is excluded.

## Lifetime proof for phase aliasing

The engine executes globally separated phases: check update completes before variable update starts, and variable update completes before convergence/next check phase.

During check update, each edge belongs to exactly one check. Once all old NU values for that check have been read, those NU values are never used again in the iteration. Their slots may be overwritten with the corresponding MU outputs.

During variable update, each edge belongs to exactly one fault. Once all MU values for that fault have been read and its aggregate computed, those MU values are dead and may be overwritten with the next NU outputs.

Therefore one edge-message store can alternate:

`NU(previous iteration) → MU(current check phase) → NU(current variable phase)`.

No mathematical ping-pong array is required because an edge has one owner in each phase and phase boundaries prevent a later consumer from needing the overwritten value. Within a node, the controller must complete all reads before overwriting any slot whose value contributes to that node's aggregate; the existing staged controller already separates gather and emit behavior.

## Consequence

A phase-aliased store saves one `E×18` array per trajectory: 7,043,760 bits, or 14,087,520 bits for N=2. It reduces the M3 banked-capacity estimate by 384 BRAM36 equivalents, producing M4.

## Alternatives rejected

- Sharing MU/NU between E0 and E1 is invalid because their messages diverge.
- Recomputing MU instead of storing it would repeat check updates and increase latency substantially.
- Recomputing NU instead of retaining it would require prior variable-state reconstruction and change the schedule.
- Lowering precision is excluded.

M4 is analytically semantics-preserving, but it must pass address-level, iteration-level, and full 256-trajectory equivalence tests after implementation before being frozen.

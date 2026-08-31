# Example: graph layout over the P=4 folded datapath

> Scope: professor-facing software-model illustration. This is not a new RTL
> architecture and does not change Relay-BP equations or graph connectivity.

## 1. Mathematical decoding graph

The small fixture is

```text
C0 -> V0, V1, V2
C1 -> V1, V2, V3
C2 -> V0, V2, V3
```

Its nine mathematical incidences are retained exactly:

```text
e0=C0--V0  e1=C0--V1  e2=C0--V2
e3=C1--V1  e4=C1--V2  e5=C1--V3
e6=C2--V0  e7=C2--V2  e8=C2--V3
```

Partitioning/layout changes only storage addresses. It never deletes, duplicates,
or redirects one of these incidences.

## 2. Conceptual graph partitions

One illustrative locality assignment is

```text
Partition 0: C0, V0, V1
Partition 1: C1, C2, V2, V3
```

Cross-partition incidences remain present. A partition ID is therefore layout
metadata, not permission to remove an edge.

```mermaid
flowchart LR
  subgraph P0[Partition 0]
    C0((C0))
    V0[V0]
    V1[V1]
  end
  subgraph P1[Partition 1]
    C1((C1))
    C2((C2))
    V2[V2]
    V3[V3]
  end
  C0 --- V0
  C0 --- V1
  C0 --- V2
  C1 --- V1
  C1 --- V2
  C1 --- V3
  C2 --- V0
  C2 --- V2
  C2 --- V3
```

## 3. Bank-aware address assignment

The implemented P=4 model selects a physical bank by

```text
bank = logical_address mod 4
```

A BA2-style layout first assigns a desired residue, then places an item only in
addresses `residue + 4*k`. For illustration:

| Mathematical item | New address | Bank |
|---|---:|---:|
| V0 | 0 | 0 |
| V1 | 1 | 1 |
| V2 | 2 | 2 |
| V3 | 3 | 3 |
| e2 | 4 | 0 |
| e4 | 5 | 1 |
| e7 | 6 | 2 |

The forward and inverse tables preserve mathematical identity:

```text
old ID -> new address -> old ID
```

## 4. From one access group to four datapath lanes

Suppose the variable update for `V2` needs messages on `e2`, `e4`, and `e7`.
With the illustrative bank-aware addresses above:

```text
request group: e2@4, e4@5, e7@6
banks:            0,    1,    2
```

All three requests can issue together:

```mermaid
flowchart LR
  S[Variable V2 scheduler] -->|e2 address 4| B0[(Bank 0)]
  S -->|e4 address 5| B1[(Bank 1)]
  S -->|e7 address 6| B2[(Bank 2)]
  B0 --> L0[Datapath lane 0]
  B1 --> L1[Datapath lane 1]
  B2 --> L2[Datapath lane 2]
  B3[(Bank 3)] -. idle .-> L3[Datapath lane 3]
  L0 --> U[Variable-node update]
  L1 --> U
  L2 --> U
  L3 --> U
```

This issued subset has three active lanes and requires no retry.

## 5. What a conflict looks like

If the same three messages instead had addresses `4`, `8`, and `6`, their banks
would be `0`, `0`, and `2`:

```text
original request: [e2@4, e4@8, e7@6]
first subset:     [e2@4,       e7@6]  -> banks 0 and 2
retry subset:            [e4@8]       -> bank 0
```

The stable scheduler lets the first pending lane for each bank win. The other
bank-0 request is retried. BA2 attempts to avoid assigning the same residue to
items that frequently occur in one request group.

## 6. Full dataflow context

```mermaid
flowchart LR
  G[Same detector-fault graph] --> P[Static partition/layout metadata]
  P --> F[Reversible fault address permutation]
  P --> E[Reversible edge/message address permutation]
  F --> FT[Prior / marginal / gamma / decision tables]
  E --> ET[MU / NU message tables]
  FT --> SCH[P=4 stable subset scheduler]
  ET --> SCH
  SCH --> B0[(Bank 0)]
  SCH --> B1[(Bank 1)]
  SCH --> B2[(Bank 2)]
  SCH --> B3[(Bank 3)]
  B0 --> L0[Lane 0 datapath]
  B1 --> L1[Lane 1 datapath]
  B2 --> L2[Lane 2 datapath]
  B3 --> L3[Lane 3 datapath]
  L0 --> R[Same Relay-BP update]
  L1 --> R
  L2 --> R
  L3 --> R
```

The four lanes are folded arithmetic lanes processing one trajectory. They are
not four independent mathematical graph partitions and do not run different
Relay-BP equations. Partitioning and bank-aware ordering only try to present
more mutually compatible memory addresses to these lanes each issued cycle.

## 7. Interpretation of the current BA2 result

In the full Tier-2 software access model, BA2 makes every modeled variable-phase
MU and NU group conflict-free. Convergence improves, while relay initialization
regresses. The aggregate software-model result is higher lane utilization and
fewer retry subsets. This document illustrates the mechanism only; it is not an
FPGA speedup claim.

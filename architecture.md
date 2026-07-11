# Parallel-Lane Relay-BP Ensembling + Quasi-Cyclic Compressed H
### A combined proposal (Areas A + E)

**Thesis in one line:** free up BRAM/URAM by storing `H` in a quasi-cyclic
(circulant-block) form instead of dense, and reinvest that freed memory in
several Relay-BP lanes that run unconditionally, in lockstep, racing each
other to convergence — with only a final mux/vote deciding the winner.

This keeps everything inside the message-passing decoder class the paper
already shows wins, uses conditionals *only* at the very end (mux, not
skip-work), and directly answers the two "future directions" the paper
leaves open: FPGA-specific space/time optimization of BP scheduling, and
exploiting the repeated-submatrix structure noted in Sec. 5.7.

---

## 1. Top-level system block diagram

```mermaid
flowchart TB
    S["Syndrome input s"] --> DIST["Broadcast network\n(fan-out, no logic)"]

    DIST --> L1["Lane 1: Relay-BP\nγ-schedule A, seed A"]
    DIST --> L2["Lane 2: Relay-BP\nγ-schedule B, seed B"]
    DIST --> L3["Lane 3: Relay-BP\nγ-schedule C, seed C"]
    DIST --> LN["Lane N: Relay-BP\nγ-schedule N, seed N"]

    subgraph MEM["Shared quasi-cyclic H storage (Area E)"]
        QC["Circulant generator bank\n+ shift/address generator"]
    end

    QC --> L1
    QC --> L2
    QC --> L3
    QC --> LN

    L1 --> CM1["Convergence monitor 1\n(syndrome-weight = 0?)"]
    L2 --> CM2["Convergence monitor 2"]
    L3 --> CM3["Convergence monitor 3"]
    LN --> CMN["Convergence monitor N"]

    CM1 --> ARB["Arbiter / vote-mux\nfirst-valid, majority, or lowest-weight"]
    CM2 --> ARB
    CM3 --> ARB
    CMN --> ARB

    ARB --> OUT["Correction output ê"]
```

Key point: every lane is wired identically and runs every cycle — there is
no per-instance branching. The only conditional in the whole design is the
arbiter's final select, which is a combinational mux driven by "done" flags,
not a control-flow decision that skips work.

---

## 2. Single-lane pipeline (what's inside each Relay-BP lane)

```mermaid
flowchart LR
    IN["Syndrome s"] --> VN["Variable-node update\nLLR + memory term γ·L_prev"]
    VN --> CN["Check-node update\n(min-sum)"]
    CN --> SC{"H·ê = s ?"}
    SC -- "not converged, iter < max" --> VN
    SC -- "converged" --> DONE["Emit ê, iteration count,\nresidual syndrome weight"]

    QCADDR["QC address generator\n(shared, Area E)"] -. "H(i,j) on demand" .-> VN
    QCADDR -. "H(i,j) on demand" .-> CN
```

The variable/check-node update loop is untouched Relay-BP — the only new
element per lane is a distinct `(γ-schedule, seed)` pair, and a shared
address generator replacing a dense per-lane memory copy.

---

## 3. Arbiter decision logic

```mermaid
flowchart TD
    START["All N lanes running, lockstep, cycle counter shared"] --> CHK{"Any lane's\ndone flag high\nthis cycle?"}
    CHK -- "no" --> TICK["cycle++, all lanes continue unconditionally"] --> CHK
    CHK -- "yes" --> FIRST["Latch (lane_id, ê, weight, iter)\nfor each lane going high"]
    FIRST --> POLICY{"Arbiter policy\n(compile-time choice)"}
    POLICY -- "first-to-converge" --> EMIT1["Emit that lane's ê\nimmediately, kill others"]
    POLICY -- "bounded wait, k cycles" --> COLLECT["Collect all finishers\nwithin the k-cycle window"]
    COLLECT --> VOTE{"Do a majority\nof finishers agree\non ê?"}
    VOTE -- "yes" --> EMITM["Emit majority ê"]
    VOTE -- "no" --> LOWW["Emit ê from the finisher\nwith lowest residual weight"]
```

`k` is a small fixed constant (e.g. 2–8 cycles) — bounded, so this is still
O(1) extra latency, not a re-introduction of the tail problem.

---

## 4. Quasi-cyclic compressed storage vs. dense (Area E)

```mermaid
flowchart LR
    subgraph Dense["Baseline (paper, Table 1): dense H"]
        D1["Full H in BRAM/URAM\nrows × cols bits, hundreds of BRAM/URAM"]
    end

    subgraph QCBlock["Proposed: QC-compressed H"]
        G1["Circulant generator rows\n(one row per block-column,\nrest are cyclic shifts)"]
        SHT["Shift-index table\n(small, per block)"]
        AG["Address generator:\n(row, col) → (generator row, shift)"]
        G1 --> AG
        SHT --> AG
    end

    AG --> ACC["On-the-fly H(i,j) lookup,\nfeeds VN/CN update in every lane"]
```

Because the same generator bank is shared across *all* lanes (Section 1),
the freed BRAM/URAM is not just "saved" — it is the resource that literally
pays for lane N+1, N+2, … This is what turns A and E into one coherent
narrative rather than two separate tweaks.

---

## 5. Timing view: why this attacks the tail specifically

```mermaid
sequenceDiagram
    participant L1 as Lane 1 (γ=A)
    participant L2 as Lane 2 (γ=B)
    participant L3 as Lane 3 (γ=C)
    participant ARB as Arbiter

    par all lanes start together, cycle 0
        L1->>L1: iterate BP
        L2->>L2: iterate BP
        L3->>L3: iterate BP
    end
    L2-->>ARB: converged @ cycle 40
    Note over ARB: first valid result arrives from Lane 2
    ARB-->>ARB: emit ê (does not wait on L1, L3)
    L1-->>ARB: converged @ cycle 130 (discarded)
    L3-->>ARB: hits Tmax without converging (discarded)
```

In the sequential/escalation picture, a single unlucky leg dominates
`T_max`. Here, `T_max` for the ensemble is (in the first-to-converge policy)
the **minimum** across lanes rather than a single draw — which is exactly
why tail latency (not mean latency) is expected to shrink, since it's the
tail draws that ensembling suppresses most.

---

## 6. What the accompanying simulation shows

`relay_ensemble_sim.py` is a proxy simulation (not RTL) that demonstrates
the two claims numerically on a synthetic quasi-cyclic parity-check matrix:

1. **Memory**: dense-bit-count vs. QC-generator-bit-count for the same `H`,
   to quantify the BRAM/URAM budget freed by Area E.
2. **Latency**: Monte Carlo comparison of a single Relay-BP-style lane vs.
   an N-lane ensemble (different γ-schedules/seeds per lane, first-to-converge
   policy), reporting mean *and* tail (95th/99th percentile) decode latency —
   since the tail is the quantity Area A is meant to shrink, not the mean.

This is a behavioral proxy for arguing the shape of the effect and sizing
the tradeoff (freed BRAM vs. added lanes vs. tail-latency reduction); it is
not a substitute for HLS/RTL implementation and post-synthesis timing, which
would be the natural next step after the professor buys the direction.

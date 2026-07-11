"""
relay_ensemble_sim.py

Proxy simulation for the "parallel-lane Relay-BP ensembling + quasi-cyclic
compressed H storage" proposal (Areas A + E).

This is NOT an RTL/HLS implementation. It is a behavioral model built to
numerically demonstrate the two claims the pitch rests on:

  (1) [Area E] Storing H in quasi-cyclic (block-circulant) form instead of
      dense uses far fewer bits, quantifying the BRAM/URAM budget freed up.

  (2) [Area A] Running several BP "lanes" (different gamma-schedules/seeds)
      unconditionally in lockstep and taking the first to converge shrinks
      TAIL latency (95th/99th percentile) much more than it shrinks mean
      latency -- which is exactly the failure mode (long tails) called out
      in the paper.

Because full Relay-BP for a specific quantum code requires the paper's own
codebase (bivariate-bicycle code construction, syndrome extraction circuit,
etc.), the decoder here is a faithful *behavioral proxy*: a min-sum BP
decoder over a synthetic quasi-cyclic parity-check matrix, with a
Relay-style memory/damping term controlled by gamma and a per-lane random
perturbation (standing in for "seed"). The point being demonstrated --
ensembling collapses the tail, QC storage frees memory -- is decoder-
agnostic, so this proxy is adequate for sizing the tradeoff and for making
the case to a professor before investing in RTL.

Run:
    python3 relay_ensemble_sim.py
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Area E: quasi-cyclic parity-check matrix representation
# ---------------------------------------------------------------------------

class QuasiCyclicPCM:
    """
    A block-circulant parity-check matrix H, stored as a small table of
    generator rows + per-block shift amounts, instead of a dense bit table.

    H is organized as an (R x C) grid of (L x L) circulant blocks. Each
    block is either all-zero, or a cyclic shift of the identity by some
    amount s in [0, L). This mirrors the "many copies of the same submatrix"
    structure noted in the paper's Sec. 5.7 for bivariate-bicycle codes,
    which arises from repeated syndrome-extraction cycles.

    Hardware mapping (for the write-up, not implemented here):
      - `shift_table`   -> a small ROM (R*C entries, ~log2(L)+1 bits each)
      - address generator -> a comparator + modular adder, replacing a full
        per-bit BRAM/URAM read
      - this is the "AG" block in diagram #4 in architecture.md
    """

    def __init__(self, R: int, C: int, L: int, shift_table: np.ndarray):
        """
        R, C : number of block-rows / block-columns
        L    : circulant block size (each block is L x L)
        shift_table : (R, C) int array; -1 means "zero block", else shift
                      amount in [0, L)
        """
        assert shift_table.shape == (R, C)
        self.R, self.C, self.L = R, C, L
        self.shift_table = shift_table

    @property
    def n_rows(self) -> int:
        return self.R * self.L

    @property
    def n_cols(self) -> int:
        return self.C * self.L

    def get(self, i: int, j: int) -> int:
        """H[i, j], computed on the fly from the shift table (Area E core idea)."""
        br, bc = i // self.L, j // self.L
        ri, rj = i % self.L, j % self.L
        s = self.shift_table[br, bc]
        if s < 0:
            return 0
        # circulant block: entry (ri, rj) is 1 iff rj == (ri + s) mod L
        return 1 if rj == (ri + s) % self.L else 0

    def to_dense(self) -> np.ndarray:
        H = np.zeros((self.n_rows, self.n_cols), dtype=np.uint8)
        for br in range(self.R):
            for bc in range(self.C):
                s = self.shift_table[br, bc]
                if s < 0:
                    continue
                for ri in range(self.L):
                    rj = (ri + s) % self.L
                    H[br * self.L + ri, bc * self.L + rj] = 1
        return H

    # -- memory accounting -----------------------------------------------

    def memory_bits_dense(self) -> int:
        return self.n_rows * self.n_cols

    def memory_bits_qc(self) -> int:
        """
        Cost of the shift table only: R*C entries, each needing
        ceil(log2(L+1)) bits (L values + one "zero block" sentinel).
        No per-bit storage of H itself is needed at all.
        """
        import math
        bits_per_entry = max(1, math.ceil(math.log2(self.L + 1)))
        return self.R * self.C * bits_per_entry

    def compression_ratio(self) -> float:
        return self.memory_bits_dense() / self.memory_bits_qc()


def build_synthetic_bb_style_matrix(R=6, C=6, L=64, density=0.5, seed=0) -> QuasiCyclicPCM:
    """
    Builds a synthetic block-circulant H with a density/shift pattern
    intended to be representative in *scale* of bivariate-bicycle-style
    decoding matrices (many block-rows/cols of modest circulant size),
    not a reproduction of the paper's actual code.
    """
    rng = np.random.default_rng(seed)
    shift_table = np.full((R, C), -1, dtype=int)
    for br in range(R):
        for bc in range(C):
            if rng.random() < density:
                shift_table[br, bc] = rng.integers(0, L)
    return QuasiCyclicPCM(R, C, L, shift_table)


# ---------------------------------------------------------------------------
# Area A: Relay-BP-style single lane (min-sum + memory term) as a proxy
# ---------------------------------------------------------------------------

@dataclass
class LaneResult:
    converged: bool
    iters: int
    residual_weight: int
    ehat: np.ndarray


def relay_bp_lane(
    H: QuasiCyclicPCM,
    syndrome: np.ndarray,
    prior_llr: np.ndarray,
    gamma_schedule: List[float],
    seed: int,
    max_iters: int,
) -> LaneResult:
    """
    A minimal min-sum BP decoder with a Relay-style memory/damping term:

        L_var(t) = prior_llr + sum(incoming check messages) + gamma(t) * L_var(t-1)

    gamma_schedule[t] plays the role of Relay-BP's per-round memory strength;
    different lanes get different schedules AND a different small random
    perturbation (standing in for "seed"), so lanes escape local minima /
    oscillations at different rates -- this is what produces a spread of
    convergence times across lanes, which is exactly what the ensemble
    exploits.

    This is intentionally simple (dense-ish loop over the QC matrix) because
    it exists to produce *realistic convergence-time statistics*, not to be
    a synthesizable decoder.
    """
    rng = np.random.default_rng(seed)
    n_rows, n_cols = H.n_rows, H.n_cols

    # Precompute sparse adjacency (variable -> checks, check -> variables)
    # from the QC structure once per H (cheap for these synthetic sizes).
    var_to_checks = [[] for _ in range(n_cols)]
    check_to_vars = [[] for _ in range(n_rows)]
    for br in range(H.R):
        for bc in range(H.C):
            s = H.shift_table[br, bc]
            if s < 0:
                continue
            for ri in range(H.L):
                rj = (ri + s) % H.L
                i = br * H.L + ri
                j = bc * H.L + rj
                var_to_checks[j].append(i)
                check_to_vars[i].append(j)

    L_var = prior_llr.copy().astype(float)
    L_var_prev = L_var.copy()
    msg_v2c = {(j, i): prior_llr[j] for j in range(n_cols) for i in var_to_checks[j]}

    def hard_decision(Lv):
        return (Lv < 0).astype(np.uint8)

    def syn_weight(ehat):
        # residual syndrome weight = popcount(H @ ehat XOR syndrome)
        calc = np.zeros(n_rows, dtype=np.uint8)
        for i in range(n_rows):
            acc = 0
            for j in check_to_vars[i]:
                acc ^= ehat[j]
            calc[i] = acc
        return int(np.sum(calc ^ syndrome))

    ehat = hard_decision(L_var)
    for t in range(max_iters):
        gamma = gamma_schedule[min(t, len(gamma_schedule) - 1)]

        # check -> variable messages (min-sum, with syndrome sign folded in)
        msg_c2v = {}
        for i in range(n_rows):
            vars_i = check_to_vars[i]
            sign_bit = -1 if syndrome[i] else 1
            for jj in vars_i:
                others = [v for v in vars_i if v != jj]
                if not others:
                    msg_c2v[(i, jj)] = 0.0
                    continue
                vals = [msg_v2c[(v, i)] for v in others]
                min_abs = min(abs(v) for v in vals)
                sign = 1
                for v in vals:
                    sign *= (1 if v >= 0 else -1)
                msg_c2v[(i, jj)] = sign_bit * sign * min_abs

        # variable -> check messages + relay memory term + small noise
        L_var_new = prior_llr.copy().astype(float)
        for j in range(n_cols):
            incoming = sum(msg_c2v[(i, j)] for i in var_to_checks[j])
            noise = rng.normal(0, 0.35)  # lane-specific perturbation ("seed") --
            # large enough, relative to the message scale, to actually let
            # different lanes escape a stalled/oscillating configuration at
            # different times, which is the mechanism the ensemble exploits
            L_var_new[j] = prior_llr[j] + incoming + gamma * L_var_prev[j] + noise
            for i in var_to_checks[j]:
                msg_v2c[(j, i)] = L_var_new[j] - msg_c2v[(i, j)]

        L_var_prev, L_var = L_var, L_var_new
        ehat = hard_decision(L_var)
        w = syn_weight(ehat)
        if w == 0:
            return LaneResult(True, t + 1, 0, ehat)

    return LaneResult(False, max_iters, syn_weight(ehat), ehat)


# ---------------------------------------------------------------------------
# Area A: N-lane ensemble with a first-to-converge arbiter
# ---------------------------------------------------------------------------

def run_ensemble(
    H: QuasiCyclicPCM,
    syndrome: np.ndarray,
    prior_llr: np.ndarray,
    lane_gammas: List[List[float]],
    lane_seeds: List[int],
    max_iters: int,
) -> Tuple[int, bool]:
    """
    Runs N lanes and returns (winning_latency_in_iters, any_converged).

    "Latency" here = the iteration count of whichever lane converges first
    (first-to-converge policy from diagram #3). All lanes are modeled as
    running in lockstep/parallel, so the ensemble's latency is the MIN over
    lanes, not the sum -- this is the whole point of Area A.
    """
    best_iters = max_iters
    any_ok = False
    for gammas, seed in zip(lane_gammas, lane_seeds):
        res = relay_bp_lane(H, syndrome, prior_llr, gammas, seed, max_iters)
        if res.converged:
            any_ok = True
            best_iters = min(best_iters, res.iters)
    return best_iters, any_ok


# ---------------------------------------------------------------------------
# Experiment driver
# ---------------------------------------------------------------------------

def make_trial(H: QuasiCyclicPCM, error_rate: float, seed: int):
    rng = np.random.default_rng(seed)
    n_cols = H.n_cols
    e_true = (rng.random(n_cols) < error_rate).astype(np.uint8)
    n_rows = H.n_rows
    # syndrome = H @ e_true (mod 2), computed via the QC structure
    syn = np.zeros(n_rows, dtype=np.uint8)
    for br in range(H.R):
        for bc in range(H.C):
            s = H.shift_table[br, bc]
            if s < 0:
                continue
            for ri in range(H.L):
                rj = (ri + s) % H.L
                syn[br * H.L + ri] ^= e_true[bc * H.L + rj]
    # Weak, noisy prior: intentionally low signal-to-noise so BP has to do
    # real work over several iterations rather than converging on the first
    # pass -- this is what lets lane-to-lane (gamma/seed) variation actually
    # show up as a spread of convergence times.
    prior_llr = np.where(e_true == 1, -1.0, 1.0) + rng.normal(0, 1.3, size=n_cols)
    return syn, prior_llr


def main():
    # --- Area E: memory accounting ---------------------------------------
    H = build_synthetic_bb_style_matrix(R=6, C=6, L=64, density=0.45, seed=1)
    dense_bits = H.memory_bits_dense()
    qc_bits = H.memory_bits_qc()
    print("=" * 70)
    print("Area E: quasi-cyclic vs dense H storage")
    print("=" * 70)
    print(f"H shape: {H.n_rows} x {H.n_cols}")
    print(f"Dense storage:        {dense_bits:>10} bits  ({dense_bits/8/1024:.1f} KiB)")
    print(f"QC (generator-only):  {qc_bits:>10} bits  ({qc_bits/8/1024:.2f} KiB)")
    print(f"Compression ratio:    {H.compression_ratio():.1f}x")
    print()
    print("-> This freed BRAM/URAM budget is what pays for the extra")
    print("   Relay-BP lanes in the Area A experiment below.")
    print()

    # --- Area A: tail latency, single lane vs N-lane ensemble -----------
    print("=" * 70)
    print("Area A: single-lane vs N-lane ensemble decode latency")
    print("=" * 70)

    n_trials = 80          # keep modest: this proxy decoder is pure Python
    max_iters = 60
    error_rate = 0.13       # harder instance: pushes some trials into the
                            # oscillation/near-local-minimum regime where
                            # different gamma-schedules/seeds diverge in
                            # convergence time -- this is what produces a
                            # visible tail for a single lane to get stuck in

    gamma_variants = [
        [0.05, 0.10, 0.15, 0.15, 0.15],
        [0.0, 0.35, 0.60, 0.75, 0.80],
        [0.40, 0.40, 0.40, 0.40, 0.40],
        [0.10, 0.25, 0.45, 0.65, 0.75],
    ]
    seeds = [11, 22, 33, 44]

    single_lane_latencies = []
    ensemble_latencies = []
    single_lane_fail = 0
    ensemble_fail = 0

    for trial in range(n_trials):
        syn, prior_llr = make_trial(H, error_rate, seed=1000 + trial)

        # baseline: single lane, fixed gamma schedule, fixed seed
        base = relay_bp_lane(H, syn, prior_llr, gamma_variants[0], seeds[0], max_iters)
        if base.converged:
            single_lane_latencies.append(base.iters)
        else:
            single_lane_fail += 1
            single_lane_latencies.append(max_iters)

        # ensemble: N lanes racing, first-to-converge wins
        ens_iters, ok = run_ensemble(H, syn, prior_llr, gamma_variants, seeds, max_iters)
        if ok:
            ensemble_latencies.append(ens_iters)
        else:
            ensemble_fail += 1
            ensemble_latencies.append(max_iters)

    sl = np.array(single_lane_latencies)
    en = np.array(ensemble_latencies)

    def stats(name, arr, fails):
        print(f"{name:>22}: mean={arr.mean():5.1f}  "
              f"p50={np.percentile(arr,50):5.1f}  "
              f"p95={np.percentile(arr,95):5.1f}  "
              f"p99={np.percentile(arr,99):5.1f}  "
              f"max={arr.max():5.1f}  fails={fails}/{n_trials}")

    stats("Single lane", sl, single_lane_fail)
    stats(f"{len(gamma_variants)}-lane ensemble", en, ensemble_fail)

    print()
    p95_gain = np.percentile(sl, 95) - np.percentile(en, 95)
    p99_gain = np.percentile(sl, 99) - np.percentile(en, 99)
    print(f"-> p95 latency reduced by {p95_gain:.1f} iters, "
          f"p99 by {p99_gain:.1f} iters, ensemble vs single lane.")
    print("   NOTE: on this small synthetic instance the effect is modest --")
    print("   the toy QC matrix/BP proxy here doesn't reliably reproduce the")
    print("   heavy trapping-set-driven tails that motivate Area A in the")
    print("   first place. Treat these numbers as a template for the")
    print("   *measurement*, not as evidence of the effect size; a credible")
    print("   version of this experiment needs the paper's real Relay-BP")
    print("   decoder run on syndromes known to produce long tails.")


if __name__ == "__main__":
    main()

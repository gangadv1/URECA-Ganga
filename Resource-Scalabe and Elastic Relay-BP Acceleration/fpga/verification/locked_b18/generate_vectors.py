"""Generate deterministic locked-b18 primitive vectors from Python integer rules."""
from __future__ import annotations
from pathlib import Path
import json

OUT = Path(__file__).resolve().parent
MIN18, MAX18 = -(1 << 17), (1 << 17) - 1
MIN22, MAX22 = -(1 << 21), (1 << 21) - 1


def sat(value, lo, hi): return max(lo, min(hi, int(value)))
def round16(value):
    return (-1 if value < 0 else 1) * ((abs(int(value)) + 8) // 16)
def bias(prior, previous, gamma):
    return sat(round16(16 * prior + gamma * (previous - prior)), MIN18, MAX18)


def check(values, syndrome):
    if len(values) == 1: return [-MAX18 if syndrome else MAX18]
    mags = [abs(x) for x in values]
    first = min(range(len(values)), key=mags.__getitem__)
    min1 = mags[first]
    min2 = min(mags[:first] + mags[first + 1:])
    parity = syndrome ^ (sum(x < 0 for x in values) & 1)
    out = []
    for i, x in enumerate(values):
        mag = min2 if i == first else min1
        negative = parity ^ (x < 0)
        out.append(sat(-mag if negative else mag, MIN18, MAX18))
    return out


def variable(prior, previous, gamma, mus):
    b = bias(prior, previous, gamma)
    total_raw = sum(mus); total = sat(total_raw, MIN22, MAX22)
    marginal = sat(b + total, MIN18, MAX18)
    decision = int(marginal <= 0)
    nus = [sat(marginal - mu, MIN18, MAX18) for mu in mus]
    return b, total, int(total != total_raw), marginal, decision, nus, prior if decision else 0


def main():
    arithmetic_inputs = [
        -(1 << 24), -2097152, -131073, MIN18, -25, -24, -23, -9, -8, -7,
        -1, 0, 1, 7, 8, 9, 23, 24, 25, MAX18, 131072, 2097151, (1 << 24)-1,
    ]
    with (OUT / "arithmetic_vectors.txt").open("w") as f:
        for value in arithmetic_inputs:
            clipped = sat(value, MIN18, MAX18)
            f.write(f"{value} {clipped} {int(clipped != value)} {round16(value)}\n")

    bias_inputs = [
        (0, 0, 0), (1, 9, 2), (0, 4, 2), (0, -4, 2), (0, 2, 4), (0, -2, 4),
        (7, 7, -4), (-7, 11, -4), (100, -100, 11), (MAX18, MIN18, 11),
        (MIN18, MAX18, -4), (MAX18, MAX18, 4), (MIN18, MIN18, 2),
        (131060, 131071, 11), (-131060, -131072, 11),
    ]
    with (OUT / "bias_vectors.txt").open("w") as f:
        for p, m, g in bias_inputs: f.write(f"{p} {m} {g} {bias(p,m,g)}\n")

    check_inputs = [
        ([7], 0), ([7], 1), ([-7], 0),
        ([3, -5], 0), ([3, -5], 1), ([3, -3, 7], 0),
        ([3, -3, 3], 1), ([0, 5, -6], 0), ([MIN18, MAX18, -2, 2], 1),
        ([9, -4, 7, -4, 12], 0), ([1, 1, 1, 1, 1, 1], 1),
    ]
    with (OUT / "check_vectors.txt").open("w") as f:
        for values, syn in check_inputs:
            padded = values + [0] * (9-len(values)); expected = check(values, syn) + [0] * (9-len(values))
            f.write(" ".join(map(str, [len(values), syn, *padded, *expected])) + "\n")

    variable_inputs = []
    gammas = [0, 2, 4, -4, 11, 2, 4, -4, 11]
    for degree in range(1, 10):
        mus = [((-1)**k) * (degree * 13 + k * 7) for k in range(degree)]
        variable_inputs.append((degree * 3 - 14, 9 - degree * 5, gammas[degree-1], mus))
    variable_inputs += [
        (0, 0, 0, [0]),
        (5, -5, 2, [-4]),
        (MAX18, MIN18, 11, [MAX18] * 9),
        (MIN18, MAX18, -4, [MIN18] * 9),
        (100, -100, 4, [-50, -50, 0, 50, 50]),
    ]
    with (OUT / "variable_vectors.txt").open("w") as f:
        for prior, previous, gamma, mus in variable_inputs:
            b,total,accsat,marg,decision,nus,weight = variable(prior,previous,gamma,mus)
            padded = mus + [0]*(9-len(mus)); padded_nu = nus + [0]*(9-len(nus))
            f.write(" ".join(map(str,[len(mus),prior,previous,gamma,*padded,b,total,accsat,marg,decision,*padded_nu,weight]))+"\n")
    manifest = {"arithmetic_vectors": len(arithmetic_inputs),
                "bias_vectors": len(bias_inputs), "check_vectors": len(check_inputs),
                "variable_vectors": len(variable_inputs), "oracle": "integer rules matching reference/relay_bp_fixed.py",
                "coverage": ["zero", "signed extrema", "saturation", "gamma 0/2/4/-4/11",
                             "positive/negative half rounding", "equal/repeated minima", "syndrome 0/1",
                             "marginal zero", "variable degree 1..9"]}
    (OUT / "vector_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")

if __name__ == "__main__": main()

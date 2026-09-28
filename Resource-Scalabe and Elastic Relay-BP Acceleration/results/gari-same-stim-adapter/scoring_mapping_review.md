# Independent review: mapping native GARI corrections into canonical scoring

This review concerns the single-member configuration reproduced from official
GARI commit `6380d52e76d8c9cb0b4eedf3e8d2429b24cef78d`. It does not change a decoder,
run a decoder benchmark, repair a returned correction, or use a sampled error.

## Canonical scoring contract

The existing scorer in
`../circuit-level-baseline/run_circuit_level_baseline.py:131–135` computes

```
predicted_syndrome = H c mod 2
predicted_logical  = L c mod 2
syndrome_valid    = (predicted_syndrome == sampled_syndrome)
logical_match     = (predicted_logical == stored_logical_label)
success           = syndrome_valid AND logical_match
```

Equality means equality of every bit. The dimensions are
`H: 1728 × 67752`, `L: 12 × 67752`, and `c: 67752`.
The logical label belongs exclusively to the scorer. Native convergence and
full canonical syndrome validity must be recorded separately.

## Expanded graph and hard-decision ordering

In the preserved official `helper_functions.py`, `det_and_err_encoding`
selects X-detector rows as `hx` and Z-detector rows as `hz` (lines 402–406).
Let `P` place X-detector rows first, then Z-detector rows, preserving each
group's original order. The fault groups are:

- `I_A = i_hx_only`: faults touching only X detectors;
- `I_B = i_hz_only`: faults touching only Z detectors;
- `I_Y = i_hy_only`: faults touching both groups.

The groups are generated at lines 408–425. In this canonical static graph,
their sizes are `7920`, `8784`, and `51048`; the row groups contain `792` and
`936` detectors. Write `D_A = H[X,I_A]` and `D_B = H[Z,I_B]`.
Each mixed column's X and Z projections matches exactly one corresponding
pure column. Let the binary incidence matrices for these projections be
`Q_A` and `Q_B`. Official first-match index lookup is at lines 197–212 and
434–435; graph construction is at lines 439–456.

The native hard decision is ordered

```
u = (a, b, z, x, y)
    7920 8784 7920 8784 51048 bits

       [ D_A  0    0    0    0   ]
G  =   [ 0    D_B  0    0    0   ]
       [ I    0    I    0    Q_A ]
       [ 0    I    0    I    Q_B ]
```

Thus `G` has `18432` rows and `84456` columns. The first `16704` variables
`(a,b)` are auxiliary effective corrections. The suffix `(z,x,y)` is the
original DEM-fault decision in grouped order. These are distinct objects.
The supplied syndrome is `(P s, 0, 0)`; zeros on the additional constraints
are static consistency conditions. `stim_batched_data_v2.py:252–262`
builds this vector and converts it to signs `1 - 2*bit` for C.

## Exact auxiliary correction lift

For a returned native candidate, define one fixed canonical correction:

```
c[I_A] = a
c[I_B] = b
c[I_Y] = 0
```

If an official parser uses a different column order, apply a previously
verified static column map before these assignments. The map must preserve
both detector and logical incidence. This is a DEM correction representative,
not a claim about which physical errors occurred.

By construction, for every binary candidate, including one that violates
bottom constraints,

```
P H c = (D_A a, D_B b).
```

The canonical graph satisfies `L[:,I_A] = 0`. Therefore

```
L c = L[:,I_B] b = L_dz b.
```

This is exactly the native logical prediction: the official driver sets
`l_dz = l[:, i_hz_only]` at line 182, and
`my_decoders/hbp_decoder_v2.c:616–626` multiplies it by
`Hdec[nx:nx+nz]`. It does **not** read the physical-fault suffix for its
logical prediction. The auxiliary lift uses only the returned decisions
and static indices; no search, label, error realization, or corrective solve
is necessary.

Independent static checks in this review found:

- all `67752` original detector supports are distinct;
- no same-detector/different-logical collision;
- all `51048` mixed columns have both pure projections;
- `L[:,I_A]` has zero nonzero entries;
- every mixed column has the same logical action as its pure B projection.

These are required assertions, not assumptions to extend to another circuit.
The last identity can be written `L[:,I_Y] = L[:,I_B] Q_B`.

## Why the physical-fault suffix is not interchangeable

Let `t` embed `(z,x,y)` into the original fault order. Define bottom residuals

```
delta_A = a + z + Q_A y mod 2
delta_B = b + x + Q_B y mod 2.
```

Then

```
P H(c + t) = (D_A delta_A, D_B delta_B)
L(c + t)   = L[:,I_B] delta_B.
```

Both representations agree in syndrome and logical action if all bottom
constraints hold. Native early stopping does not require this. Blindly
scoring `t` may therefore score a logical prediction different from the
official native output. Retain it as a diagnostic if useful; the auxiliary
lift is the direct representation of the native A/B correction.

## Native convergence is narrower than full-syndrome validity

With native early stopping enabled,
`hbp_decoder_v2.c:315–355` checks rows `[mx,m)`, meaning only

```
D_B b == s_Z.
```

It does not require `D_A a == s_X` or either bottom consistency block.
The common scorer must nevertheless check **all 1728** original detector
bits against `H c`. A candidate may consequently be native-converged and
fail the common scorer. Record this result without changing native stopping,
repairing the candidate, retrying it, or selecting an alternative using a
logical label.

The kernel returns a zero-based loop index and iterates through `Nloop`
inclusively (`hbp_decoder_v2.c:178,373`). The native batched wrapper accepts
only indices strictly below `Nloop` (`:564–576`). On rejection it selects no
member and emits zero logical prediction with the sentinel `Nloop`
(`:629–634`). A retained last-kernel candidate must be distinguished from an
accepted native result; do not present that diagnostic candidate as a
native-selected correction. This review does not alter these semantics.

## Deterministic test separating syndrome validity from logical success

`construct_logical_witness.py` reads only the two frozen static incidence
artifacts and `package.json`. In ascending original DEM column order it
performs GF(2) elimination of detector columns, preserving fault supports
and logical actions. It stops at the first dependency with a nonzero
logical action. It does not run a decoder or read a sample artifact.

The generated `logical_kernel_witness.json` contains a weight-46 correction
`w`, found after examining 344 columns with detector rank 106, satisfying

```
H w = 0
L w = 2028 as a little-endian bit mask != 0.
```

Both identities are independently checked using `faults.npz` and
`edge_lists.npz`. With a constructed zero syndrome and a constructed zero
logical label, the canonical scorer must return
`syndrome_valid=true`, `logical_action_match=false`, and `success=false`.
This fixture is solely for scorer validation; it must never enter decoder
inputs, decoder selection, or candidate repair.

Reproduce the fixture from the URECA repository root:

```sh
.venv/bin/python 'Resource-Scalabe and Elastic Relay-BP Acceleration/results/gari-same-stim-adapter/construct_logical_witness.py'
```

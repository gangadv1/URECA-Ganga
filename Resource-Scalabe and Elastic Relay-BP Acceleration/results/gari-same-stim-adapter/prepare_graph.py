"""Build GARI's unchanged graph conversion from the frozen canonical DEM.

No circuit generation, sampling, labels, physical-error samples or Relay results.
Run once with the native-reproduction Python 3.11 dependency versions.
"""
from pathlib import Path
import csv
import hashlib
import importlib.metadata
import json
import os
import sys
import time

import numpy as np
import scipy.sparse as sp
import stim
from ldpc.ckt_noise.dem_matrices import detector_error_model_to_check_matrices

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
OFFICIAL = HERE / 'official_gari'
PACKAGE = PROJECT / 'graphs/generated/gross_circuit_level/memory_Z_r12_p0p003'
CACHE = HERE / 'graph_cache'
sys.path.insert(0, str(OFFICIAL))
from helper_functions import det_and_err_encoding, build_Hcols_Hrows, syndrome_index_bb


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_matrices():
    with np.load(PACKAGE / 'faults.npz') as f:
        H = sp.csc_matrix((np.ones(len(f['detector_indices']), dtype=np.uint8),
                           f['detector_indices'], f['detector_indptr']), shape=(1728, 67752))
        L = sp.csc_matrix((np.ones(len(f['observable_indices']), dtype=np.uint8),
                           f['observable_indices'], f['observable_indptr']), shape=(12, 67752))
        return H, L, f['probabilities'].copy()


def column_keys(H, L):
    return [(tuple(H.indices[H.indptr[j]:H.indptr[j+1]]),
             tuple(L.indices[L.indptr[j]:L.indptr[j+1]])) for j in range(H.shape[1])]


def main():
    start = time.perf_counter()
    CACHE.mkdir(exist_ok=True)
    circuit_path = PACKAGE / 'circuit.stim'
    assert digest(circuit_path) == '839d2fa8ce95c62e32e2d465fb646a835e184be6ceca6e4b32f046f5c506cd20'
    circuit = stim.Circuit.from_file(str(circuit_path))
    # Extract DEM from the unchanged frozen circuit, exactly as the official driver.
    # Text DEM serialization rounds some probabilities; canonical NPZ retains full precision.
    # This does not generate a circuit or sample any shots.
    dem = circuit.detector_error_model(decompose_errors=False, flatten_loops=True, ignore_decomposition_failures=True)
    assert str(dem) == str(stim.DetectorErrorModel.from_file(str(PACKAGE / 'detector_error_model.dem')))
    matrices = detector_error_model_to_check_matrices(dem, allow_undecomposed_hyperedges=True)
    H, L, p = canonical_matrices()
    GH, GL = matrices.check_matrix.tocsc(), matrices.observables_matrix.tocsc()
    original_keys, gari_keys = column_keys(H, L), column_keys(GH, GL)
    assert len(set(original_keys)) == len(original_keys) == 67752
    assert len(set(k[0] for k in original_keys)) == 67752, 'Detector-only collision in ldpc converter'
    lookup = {key: j for j, key in enumerate(original_keys)}
    column_map = np.array([lookup[key] for key in gari_keys], dtype=np.int64)
    assert len(set(column_map)) == 67752 and GH.shape == H.shape
    assert (H[:, column_map] != GH).nnz == 0 and (L[:, column_map] != GL).nnz == 0
    assert np.array_equal(p[column_map], matrices.priors), 'DEM prior mismatch'
    print('All 67,752 H/L/prior columns bijectively matched to frozen canonical graph', flush=True)

    # Verify native positional basis rule independently via actual measurement records.
    measurements, basis = [], []
    for op in circuit.flattened():
        if op.name in ('M', 'MX', 'MY', 'MR', 'MRX', 'MRY'):
            measurements.extend([op.name] * len(op.targets_copy()))
        elif op.name == 'DETECTOR':
            names = {measurements[len(measurements) + t.value] for t in op.targets_copy()}
            assert names in ({'M'}, {'MX'}), names
            basis.append(3 if names == {'M'} else 1)
    tags = syndrome_index_bb(12, matrices, circuit)
    assert np.array_equal(tags, basis), 'Native detector order does not match measured canonical basis'
    print('All 1,728 detector basis tags independently resolved and match native rule', flush=True)

    # Call the official implementation as-is, including its graph augmentation.
    print('Starting unchanged official det_and_err_encoding', flush=True)
    encoding = det_and_err_encoding(12, matrices, circuit)
    print('Official graph augmentation complete', flush=True)
    big = encoding.big_matrix
    Hcols, Hrows = build_Hcols_Hrows(big.toarray())
    mx, nx = encoding.dx.shape
    mz, nz = encoding.dz.shape
    m, n = H.shape
    A = encoding.i_hx_only
    B = encoding.i_hz_only
    Y = encoding.i_hy_only
    assert (mx, mz, nx, nz) == (792, 936, 7920, 8784)
    assert big.shape == (m + nx + nz, n + nx + nz)
    assert np.all(encoding.i_dx_in_hx[Y] >= 0) and np.all(encoding.i_dz_in_hz[Y] >= 0)
    assert GL[:, A].nnz == 0, 'Auxiliary A correction has logical action; native B-only lift invalid'
    assert np.array_equal(GL[:, B].toarray(), L[:, column_map[B]].toarray())
    top_order = np.concatenate((np.flatnonzero(tags == 1), np.flatnonzero(tags == 3)))
    inverse = np.argsort(top_order)
    assert (big[:m, :nx+nz] != GH[top_order][:, np.concatenate((A, B))]).nnz == 0

    # Exact driver lines 206–230, including first-match column aggregation.
    priors_ab = np.zeros(nx + nz, dtype=float)
    for i in range(nx):
        priors_ab[i] = np.sum(matrices.priors[np.where(encoding.i_dx_in_hx == i)[0]])
    for i in range(nz):
        priors_ab[nx+i] = np.sum(matrices.priors[np.where(encoding.i_dz_in_hz == i)[0]])
    priors = np.zeros(big.shape[1], dtype=float)
    priors[:nx+nz] = 0.5
    priors[nx+nz:2*nx+nz] = matrices.priors[A]
    priors[2*nx+nz:2*(nx+nz)] = matrices.priors[B]
    priors[2*(nx+nz):] = matrices.priors[Y]
    llr, llr_ab = np.log((1-priors)/priors), np.log((1-priors_ab)/priors_ab)
    assert np.isfinite(llr).all() and np.isfinite(llr_ab).all()
    np.savez_compressed(CACHE / 'decoder_inputs.npz', Hcols=Hcols, Hrows=Hrows,
        llr=llr, llr_ab=llr_ab, priors=priors, priors_ab=priors_ab,
        tags=tags, top_order=top_order, raw_to_gari=inverse, official_to_canonical=column_map,
        pure_A=A, pure_B=B, mixed_Y=Y, dx=encoding.dx, dz=encoding.dz,
        l_dz=GL[:, B].toarray(), dims=np.array([m,n,mx,mz,nx,nz]),
        mixed_to_A=encoding.i_dx_in_hx[Y], mixed_to_B=encoding.i_dz_in_hz[Y])
    sp.save_npz(CACHE / 'expanded_H.npz', big)
    sp.save_npz(CACHE / 'canonical_H.npz', H)
    sp.save_npz(CACHE / 'canonical_L.npz', L)
    with (HERE / 'input_mapping.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['gari_row','raw_detector_index','basis','operation','binary_value','C_value'])
        for row, raw in enumerate(top_order):
            writer.writerow([row,int(raw),'X' if tags[raw]==1 else 'Z','reorder',f's[{raw}]',f'1-2*s[{raw}]'])
        for row in range(m, big.shape[0]):
            writer.writerow([row,'','static correlation constraint','introduced known-zero constraint',0,1])
    np.save(CACHE / 'expanded_variable_to_canonical.npy', np.concatenate((column_map[A], column_map[B], column_map[A], column_map[B], column_map[Y])))
    manifest = dict(circuit_sha256=digest(circuit_path), dem_sha256=digest(PACKAGE/'detector_error_model.dem'),
        canonical_H_shape=list(H.shape), canonical_L_shape=list(L.shape), expanded_shape=list(big.shape),
        A_checks=mx,B_checks=mz,A_variables=nx,B_variables=nz,Y_variables=len(Y),
        column_mapping_identity=bool(np.array_equal(column_map,np.arange(n))),
        all_H_L_prior_columns_verified=True, detector_basis_resolved_from_measurements=True,
        native_basis_rule_matches=True, auxiliary_lift_H_identity=True, auxiliary_lift_L_identity=True,
        sampled_information_used=False, construction_seconds=time.perf_counter()-start,
        python=sys.version, dependencies={x:importlib.metadata.version(x) for x in ['stim','ldpc','numpy','scipy','sinter']},
        cache_hashes={p.name:digest(p) for p in CACHE.iterdir() if p.is_file()})
    (HERE/'graph_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2),flush=True)


if __name__ == '__main__':
    main()

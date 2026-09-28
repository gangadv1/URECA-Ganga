"""One-shot adapter for the pinned, unchanged official GARI implementation.

Only decode(raw_syndrome) is the shot-input boundary. No labels, error samples,
Relay-BP outputs, adaptive priors, candidate repair, retries, or post-selection.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import importlib.util
import json
import os

import numpy as np
import scipy.sparse as sp

HERE = Path(__file__).resolve().parent
LIMIT = 400
ALPHA = 0.96875
SCHEDULE_SEED = 1
SCHEDULE = 2


def _binary_vector(value, size, name):
    array = np.asarray(value)
    if array.shape != (size,) or array.dtype.kind not in 'biu' or not np.isin(array, (0, 1)).all():
        raise ValueError(f'{name} must contain exactly {size} binary integer/bool values')
    return np.ascontiguousarray(array, dtype=np.int8)


@dataclass(frozen=True)
class GariResult:
    # Canonical-DEM-space correction representative of native auxiliary A/B output.
    correction: np.ndarray
    predicted_observables: np.ndarray
    native_converged: bool
    iterations: int  # native zero-based index, capped to rejection sentinel 400
    raw_expanded_candidate: np.ndarray
    raw_auxiliary_correction: np.ndarray
    physical_tail_candidate: np.ndarray  # diagnostic only; NOT substituted for native output
    expanded_parity_valid: bool
    full_syndrome_valid: bool


class GariSameStimAdapter:
    def __init__(self):
        self._cache = HERE / 'graph_cache'
        manifest = json.loads((HERE/'graph_manifest.json').read_text())
        for name, expected in manifest['cache_hashes'].items():
            actual = hashlib.sha256((self._cache/name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f'Static graph cache hash mismatch: {name}')
        source = json.loads((HERE/'source_hashes.json').read_text())
        for name, record in source['files'].items():
            actual = hashlib.sha256((HERE/'official_gari'/name).read_bytes()).hexdigest()
            if actual != record['before']:
                raise ValueError(f'Official source changed: {name}')
        with np.load(self._cache/'decoder_inputs.npz', allow_pickle=False) as data:
            self._data = {k: data[k] for k in data.files}
        self.H = sp.load_npz(self._cache/'canonical_H.npz')
        self.L = sp.load_npz(self._cache/'canonical_L.npz')
        self._expanded_H = sp.load_npz(self._cache/'expanded_H.npz')
        self.m, self.n, self.mx, self.mz, self.nx, self.nz = map(int, self._data['dims'])
        if (self.m, self.n, self.mx, self.mz, self.nx, self.nz) != (1728,67752,792,936,7920,8784):
            raise ValueError('Wrong graph dimensions')
        self.expanded_dimension = self._expanded_H.shape[0]
        self._A = self._data['official_to_canonical'][self._data['pure_A']]
        self._B = self._data['official_to_canonical'][self._data['pure_B']]
        self._Y = self._data['official_to_canonical'][self._data['mixed_Y']]
        # The official wrapper loads its .so relative to cwd. Restore cwd immediately;
        # source file, ABI signatures, and decoder calls remain unchanged.
        prior_cwd = Path.cwd()
        try:
            os.chdir(HERE/'official_gari')
            spec = importlib.util.spec_from_file_location('gari_pinned_wrapper', Path('my_decoders/hbplib_wrapper_v2.py').resolve())
            self._official = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self._official)
        finally:
            os.chdir(prior_cwd)

    def transform(self, raw_syndrome):
        raw = _binary_vector(raw_syndrome, self.m, 'raw_syndrome')
        binary = np.zeros(self.expanded_dimension, dtype=np.int8)
        binary[:self.m] = raw[self._data['top_order']]
        return 1 - 2*binary

    def _auxiliary_lift(self, candidate):
        correction = np.zeros(self.n, dtype=np.int8)
        correction[self._A] = candidate[:self.nx]
        correction[self._B] = candidate[self.nx:self.nx+self.nz]
        return correction

    def _tail_lift(self, candidate):
        tail = np.zeros(self.n, dtype=np.int8)
        k = self.nx+self.nz
        tail[self._A] = candidate[k:k+self.nx]
        tail[self._B] = candidate[k+self.nx:2*k]
        tail[self._Y] = candidate[2*k:]
        return tail

    def decode(self, raw_syndrome):
        raw = _binary_vector(raw_syndrome, self.m, 'raw_syndrome')
        bipolar = self.transform(raw)
        candidate, iterations, _ = self._official.ldpc_dec_msaa_quantum_serial_big_matrix_c(
            self._data['llr'], LIMIT, self._data['Hrows'], self._data['Hcols'],
            ALPHA, bipolar, SCHEDULE_SEED, (self.m,self.n), (self.mx,self.nx),
            custom_random_schedule_HBP=SCHEDULE, early_stopping=True)
        native_converged = bool(iterations < LIMIT)
        auxiliary = self._auxiliary_lift(candidate)
        # Exactly mimic ensemble=1 batch acceptance: no accepted member => zero action.
        correction = auxiliary.copy() if native_converged else np.zeros(self.n, dtype=np.int8)
        predicted = np.asarray(self.L @ correction).ravel() % 2
        native_prediction = ((self._data['l_dz'] @ candidate[self.nx:self.nx+self.nz]) % 2
                             if native_converged else np.zeros(12, dtype=np.int8))
        if not np.array_equal(predicted, native_prediction):
            raise RuntimeError('Canonical logical action disagrees with exact native output')
        expanded_binary = (1-bipolar)//2
        return GariResult(correction=correction, predicted_observables=predicted,
            native_converged=native_converged, iterations=int(iterations),
            raw_expanded_candidate=candidate, raw_auxiliary_correction=auxiliary,
            physical_tail_candidate=self._tail_lift(candidate),
            expanded_parity_valid=bool(np.array_equal((self._expanded_H@candidate)%2,expanded_binary)),
            full_syndrome_valid=bool(np.array_equal((self.H@correction)%2,raw)))

    def native_batch_equivalence_probe(self, raw_syndrome):
        """Validation only: same shot through original ens=1 batched entry point.

        This probe never chooses a correction; its outputs are compared with decode.
        """
        return self._official.ldpc_dec_msaa_quantum_serial_big_matrix_c_ensemble_batched_ler(
            self._data['llr'],self._data['llr_ab'],1,LIMIT,
            self._data['Hrows'],self._data['Hcols'],ALPHA,self.transform(raw_syndrome)[None,:],
            SCHEDULE_SEED,(self.m,self.n),(self.mx,self.nx),1,'i',
            self.nx,self.nz,self.mx,self.m,self._data['dz'],self._data['l_dz'],
            SCHEDULE,early_stopping=True,num_threads=4)

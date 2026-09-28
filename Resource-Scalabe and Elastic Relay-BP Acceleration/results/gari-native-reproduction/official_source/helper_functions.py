import stim
import numpy as np
from numpy import ndarray, dtype
from scipy.sparse import csc_matrix, csr_matrix
from typing import List, FrozenSet, Dict, Any
from dataclasses import dataclass
from ldpc.mod2 import nullspace
from stim import Circuit

from codes_q import *
import networkx as nx
import matplotlib.pyplot as plt
from build_circuit import build_circuit

def bb_circuit(d, p,p1,p2,p3,p4,r, z_basis=True, use_both= False, HZH=False, use_hperp = False):
    code, A_list, B_list = 0, 0, 0
    if (d == 6):
        # [[72, 12, 6]]
        code, A_list, B_list = create_bivariate_bicycle_codes(6, 6, [3], [1, 2], [1, 2], [3])
    elif (d == 10):
        # [[90,8,10]]
        code, A_list, B_list = create_bivariate_bicycle_codes(15, 3, [9], [1, 2], [2, 7], [0])
    elif (d == 12):
        # [[144,12,12]]
        code, A_list, B_list = create_bivariate_bicycle_codes(12, 6, [3], [1, 2], [1, 2], [3])
    elif (d == 18):
        # [[288,12,18]]
        code, A_list, B_list = create_bivariate_bicycle_codes(12, 12, [3], [2, 7], [1, 2], [3])
    elif (d == 24):
        # [[360,12,<=24]]
        code, A_list, B_list = create_bivariate_bicycle_codes(30, 6, [9], [1, 2], [25, 26], [3])
    elif (d == 34):
        # [[756,16,<=34]]
        code, A_list, B_list = create_bivariate_bicycle_codes(21, 18, [3], [10, 17], [3, 19], [5])

    circuit = build_circuit(code, A_list, B_list,
                            p=p, # physical error rate
                            p1=p1,p2=p2, p3=p3, p4=p4,
                            num_repeat=r,  # usually set to code distance
                            z_basis=z_basis,  # whether in the z-basis or x-basis
                            use_both=use_both,  # whether use measurement results in both basis to decode one basis
                            HZH=HZH,
                            use_hperp = use_hperp #to use hperp encoding
                            )
    return circuit, code

@dataclass
class DemMatrices:
    check_matrix: csc_matrix
    observables_matrix: csc_matrix
    priors: np.ndarray


def non_zero_rows(h):
    return np.unique(np.nonzero(h.toarray())[0])


def plot_matrix(h):
    src_ids, dst_ids = np.nonzero(h)
    dst_ids += h.shape[0]
    G = nx.Graph()
    # G = nx.DiGraph()
    for (s, t) in zip(src_ids, dst_ids):
        G.add_edge(s, t)

    color_map = ['red' if node <= max(src_ids) else 'green' for node in G]
    nx.draw(G, node_color=color_map, with_labels=True)
    plt.show()
    # # plt.savefig("trained_models/d3_panqec.png")
    girth = nx.girth(G)
    cycles = nx.cycle_basis(G)
    n_cycles = len(cycles)

    print("girth : ", girth)
    print("num cycles :", n_cycles)
    # ad = nx.to_numpy_array(G).astype("int8")
    hnew = h.copy()
    # if n_cycles:
    #     hnew = rem_cycles(G, hnew)
    #     # st = nx.minimum_spanning_tree(G)
    #     # ad = nx.to_numpy_array(st).astype("int8")
    #     plot_matrix(hnew)
    # plt.show()
    return hnew
    # return None

def count_iterable(i):
    return sum(1 for e in i)
def find_cycles(h):
    src_ids, dst_ids = np.nonzero(h)
    dst_ids += h.shape[0]
    G = nx.Graph()
    # G = nx.DiGraph()
    for (s, t) in zip(src_ids, dst_ids):
        G.add_edge(s, t)

    # color_map = ['red' if node <= max(src_ids) else 'green' for node in G]
    # nx.draw(G, node_color=color_map, with_labels=True)
    # plt.show()
    # # plt.savefig("trained_models/d3_panqec.png")
    girth = nx.girth(G)
    cycles = nx.cycle_basis(G)
    # cycles = nx.minimum_cycle_basis(G)
    # cycles = nx.simple_cycles(G)
    n_cycles = len(cycles)
    # cycles4 = (nx.simple_cycles(G,length_bound=4))
    # cycles6 = (nx.simple_cycles(G, length_bound=6))
    # cycles_tot = (nx.simple_cycles(G))

    cycles4 = (nx.simple_cycles(G,length_bound=4))
    cycles6 = (nx.simple_cycles(G, length_bound=6))
    # cycles_tot = count_iterable(nx.simple_cycles(G))

    # plt.show()
    return cycles,girth,n_cycles,cycles4,cycles6#,cycles_tot


def syndrome_mask(code_size):
    '''
    Creates a surface code grid. 1: X-stabilizer. 3: Z-stabilizer for the standard stim surface code.
    '''
    M = code_size + 1

    syndrome_matrix_X = np.zeros((M, M), dtype=np.uint8)

    # starting from northern boundary:
    syndrome_matrix_X[::2, 1:M - 1:2] = 1

    # starting from first row inside the grid:
    syndrome_matrix_X[1::2, 2::2] = 1

    syndrome_matrix_Z = np.rot90(syndrome_matrix_X) * 3

    syndrome_matrix = (syndrome_matrix_X + syndrome_matrix_Z)

    return syndrome_matrix


def syndrome_index_sc(syndrome_matrix, d, circuit):
    det_cord = circuit.get_detector_coordinates()
    n_det = len(det_cord)
    z_det_index = np.zeros(n_det, dtype='int')
    x_det_index = np.zeros(n_det, dtype='int')
    for i in range(n_det):
        if syndrome_matrix[int(det_cord[i][1] // 2), int(det_cord[i][0] // 2)] == 3:
            z_det_index[i] = 3
        else:
            x_det_index[i] = 1

    det_index = z_det_index + x_det_index
    return det_index


def surface_code_one_basis_circuit(d, r, circuit, z_basis=True):
    syndrome_matrix = syndrome_mask(d, d)
    det_cord = circuit.get_detector_coordinates()
    n_det = len(det_cord)
    z_det_index = np.zeros(n_det, dtype='int')
    x_det_index = np.zeros(n_det, dtype='int')

    circuit_len = len(circuit)
    popped = 0
    # for i in range(n_det):
    for j in range(circuit_len - 1, -1, -1):
        if circuit[j].name == 'DETECTOR':
            cord = circuit[j].gate_args_copy()
            if syndrome_matrix[int(cord[1] // 2), int(cord[0] // 2)] == 1 and z_basis:  # remove x detectors
                circuit.pop(j)
                popped += 1

            if not z_basis and syndrome_matrix[int(cord[1] // 2), int(cord[0] // 2)] == 3:
                circuit.pop(j)
                popped += 1

    return circuit


def syndrome_index_bb(d, matrices, circuit):
    n, m = matrices.check_matrix.shape
    det_index = np.zeros(n, dtype='int')
    x = 1
    z = 3
    num_z_det_qubits = circuit.num_qubits // 4
    det_index[:num_z_det_qubits] = z
    for i in range(d - 1):
        j = num_z_det_qubits + 2 * i * num_z_det_qubits
        det_index[j:j + num_z_det_qubits] = z
        det_index[j + num_z_det_qubits:j + 2 * num_z_det_qubits] = x
        # det_index[(i+1)*num_z_det_qubits:(i+2)*num_z_det_qubits] = z
        # det_index[(i+2)*num_z_det_qubits:(i+3)*num_z_det_qubits] = x

    j = num_z_det_qubits + 2 * (d - 1) * num_z_det_qubits
    det_index[j:] = z
    return det_index


def a_in_b_idx(a, b):
    # We need to transpose `a` and `b` for easier column-wise comparison.
    aT = a.T
    bT = b.T

    # Initialize index array with -1
    a_in_b = np.full(bT.shape[0], fill_value=-1, dtype=int)

    # Compare each column in `bT` with all columns in `aT`
    for j in range(bT.shape[0]):
        matches = np.all(aT == bT[j], axis=1)  # Check which columns of `a` match the j-th column of `b`
        indices = np.where(matches)[0]  # Find indices where the match is true
        if len(indices) > 0:
            a_in_b[j] = indices[0]  # Store the first matching index

    return a_in_b

def a_in_b_test(a,b):
    dx3 = np.zeros_like(a)
    for c in range(a.shape[1]):
        for j in range(b.shape[1]):
            if (a[:, c] == b[:, j]).all():
                dx3[:, c] = b[:, j]
                break
    equal = (dx3 == a).all()
    print(equal)
    return equal

def detect_data_qubits(circuit: stim.Circuit) -> list[int]:
    """Detect data qubits as those that are only measured once in a circuit.

    Warning: This is hacky and likely will only work with your typical memory circuits.
    Code taken from the relay-bp library
    """
    qubit_times_measured = [0 for qubit in range(circuit.num_qubits)]

    for inst in circuit:
        if inst.name.startswith("M") and not inst.gate_args_copy():
            for qubit in inst.targets_copy():
                qubit_times_measured[qubit.qubit_value] += 1

    return [
        qubit
        for qubit, times_measured in enumerate(qubit_times_measured)
        if times_measured == 1
    ]


def filter_detectors_by_basis(
    circuit: stim.Circuit,
    basis: str,
    qubits: list[int] | None = None,
) -> tuple[Circuit, ndarray[Any, dtype[Any]]]:
    """Return a new circuit filtering any detectors which do not detect the specified basis for the input qubits.
    Code taken from the relay-bp library
    Args:
        circuit: The original circuit
        basis: "X" or "Z"
        qubits: Data qubits to inject test errors on. Should typically be data qubits. Defaults
            to automatically detected data qubits which may not be robust.

    returns:
        The filtered circuit
    """
    assert basis in ("X", "Z")

    pauli_error = "Z" if basis == "X" else "X"

    circuit = circuit.flattened()

    noiseless_circuit = circuit.without_noise()
    sampler = noiseless_circuit.compile_detector_sampler()
    reference_detectors, reference_observables = sampler.sample(
        1, separate_observables=True
    )
    reference_detectors = reference_detectors[0, :]
    reference_observables = reference_observables[0, :]
    num_detectors = len(reference_detectors)

    detector_is_sensitive = np.full(num_detectors, False, dtype=bool)

    if qubits is None:
        to_test = detect_data_qubits(noiseless_circuit)
    else:
        to_test = qubits

    to_test_set = set(to_test)

    inst_idx = 0
    while to_test:
        for qubit in to_test:
            injected_circuit = stim.Circuit()
            injected_circuit += noiseless_circuit
            injected_circuit.insert(
                inst_idx,
                stim.CircuitInstruction(f"{pauli_error}_ERROR", [qubit], [1.0]),
            )

            injected_sampler = injected_circuit.compile_detector_sampler()
            injected_detectors, injected_observables = injected_sampler.sample(
                1, separate_observables=True
            )
            injected_detectors = injected_detectors[0, :]
            injected_observables = injected_observables[0, :]

            detectors_flipped = np.where(reference_detectors != injected_detectors)
            detector_is_sensitive[detectors_flipped] = True

        to_test = []
        for inst in noiseless_circuit[inst_idx:]:
            # Is a reset we must inject errors after
            inst_idx += 1
            if inst.name.startswith("R") or inst.name.startswith("M"):
                to_test = list(to_test_set)
                break

    filtered_circuit = stim.Circuit()
    detector_idx = 0
    for inst in circuit:
        if inst.name == "DETECTOR":
            to_insert = detector_is_sensitive[detector_idx]
            detector_idx += 1
            if not to_insert:
                continue
        filtered_circuit.append(inst)

    det_index = np.zeros(len(detector_is_sensitive), dtype='int')
    if basis == "Z":
        det_index.fill(1)   # x detectors
        det_index[detector_is_sensitive] = 3 # z detectors
    else:
        det_index.fill(3)
        det_index[detector_is_sensitive] = 1


    return filtered_circuit, det_index

def syndrome_index_bb_code_google(d, circuit):
    det_cord = circuit.get_detector_coordinates()
    n_det = len(det_cord)
    z_det_index = np.zeros(n_det, dtype='int')
    x_det_index = np.zeros(n_det, dtype='int')
    for i in range(n_det):
        if det_cord.get(i)[3] >= 3:
            z_det_index[i] = 3
        else:
            x_det_index[i] = 1

    det_index = z_det_index + x_det_index
    return det_index

def build_Hcols_Hrows(H):
    H = np.asarray(H)

    # Hcols: nonzero row indices per column
    nz_row_indices_per_col = [np.flatnonzero(H[:, i]) + 1 for i in range(H.shape[1])]
    max_col_nnz = max(len(indices) for indices in nz_row_indices_per_col)
    Hcols = np.zeros((H.shape[1], max_col_nnz), dtype=int)

    for i, indices in enumerate(nz_row_indices_per_col):
        Hcols[i, :len(indices)] = indices

    # Hrows: nonzero column indices per row
    nz_col_indices_per_row = [np.flatnonzero(H[i, :]) + 1 for i in range(H.shape[0])]
    max_row_nnz = max(len(indices) for indices in nz_col_indices_per_row)
    Hrows = np.zeros((H.shape[0], max_row_nnz), dtype=int)

    for i, indices in enumerate(nz_col_indices_per_row):
        Hrows[i, :len(indices)] = indices

    return Hcols, Hrows

@dataclass
class data_encoding:
    det_encoding: np.ndarray
    err_encoding: np.ndarray
    i_hx: np.ndarray
    i_hz: np.ndarray
    i_hx_only: np.ndarray
    i_hy_only: np.ndarray
    i_hz_only: np.ndarray
    hx_red: np.ndarray
    hz_red: np.ndarray
    hx_red_ker: np.ndarray
    hz_red_ker: np.ndarray
    det_index: np.ndarray
    dx : np.ndarray
    dz : np.ndarray
    i_dx_in_hx: np.ndarray
    i_dz_in_hz: np.ndarray
    big_matrix: csc_matrix
    # big_matrix: np.ndarray


def det_and_err_encoding(d, matrices, circuit,variant='zurich',noise=None):
    if d % 2 == 0:
        det_index = None
        if variant == 'zurich':
            det_index = syndrome_index_bb(d, matrices, circuit)
        elif variant == 'ibm':
            circuit_z,det_index = filter_detectors_by_basis(circuit,'Z')
        elif variant == 'google':
            det_index = syndrome_index_bb_code_google(d, circuit)
    else:
        det_index = syndrome_index_sc(syndrome_mask(d, d), d, circuit)
    det_encoding = np.where(det_index == 3, 1, 0) + np.where(det_index == 1, 3, 0)
    h = matrices.check_matrix.toarray()
    hxz = (h.T * det_index).T
    hx = h[np.where(det_index == 1)[0]]  # detects z error
    hz = h[np.where(det_index == 3)[0]]  # detects x error

    i_hx = np.unique(np.nonzero(hx)[1])  # non zero indices
    i_hz = np.unique(np.nonzero(hz)[1])
    i_hy = np.intersect1d(i_hx, i_hz)

    i_hx_only = np.setdiff1d(i_hx, i_hy)
    i_hz_only = np.setdiff1d(i_hz, i_hy)
    i_hy_only = i_hy

    hx_red = hx[:, i_hx]
    hz_red = hz[:, i_hz]
    hx_red_ker = nullspace(hx_red)
    hz_red_ker = nullspace(hz_red)
    err_encoding = np.zeros(h.shape[1], dtype='int')
    err_encoding[i_hx_only] = 3  # z error locations -> goes to x det
    err_encoding[i_hy_only] = 2  # y error locations -> goes to both det
    err_encoding[i_hz_only] = 1  # x error locations -> goes to z det

    dx = hx[:, i_hx_only]
    dz = hz[:, i_hz_only]
    i_dx_in_hx = a_in_b_idx(dx, hx)
    i_dz_in_hz = a_in_b_idx(dz, hz)

    """ new big matrix """
    hx_yonly = hx[:, i_hy_only]
    hz_yonly = hz[:, i_hy_only]

    i_dx_in_hx_yonly = a_in_b_idx(dx, hx_yonly)
    i_dz_in_hz_yonly = a_in_b_idx(dz, hz_yonly)
    m, n = h.shape
    mx, nx = dx.shape
    mz, nz = dz.shape
    big_matrix = np.zeros((2 * h.shape[0], dx.shape[1] + dz.shape[1] + h.shape[1]), 'int')
    """ dx,dz part """
    big_matrix = np.zeros((m + nx + nz, n + nx + nz), 'int')
    big_matrix[:mx, :nx] = dx
    big_matrix[mx:m, nx:nx + nz] = dz
    """ identity matrix part """
    big_matrix[m:, :nx + nz] = np.eye(nx + nz, dtype='int')
    big_matrix[m:, nx + nz:2 * (nx + nz)] = np.eye(nx + nz, dtype='int')

    """ y part of big matrix """
    big_matrix_y_part = big_matrix[m:, 2 * (nx + nz):]
    for i, c in enumerate(i_dx_in_hx_yonly):
        big_matrix_y_part[c, i] = 1

    for i, c in enumerate(i_dz_in_hz_yonly):
        big_matrix_y_part[c + nx, i] = 1

    big_matrix[m:, 2 * (nx + nz):] = big_matrix_y_part

    return data_encoding(det_encoding=det_encoding, err_encoding=err_encoding, i_hx=i_hx, i_hz=i_hz,
                             i_hx_only=i_hx_only, i_hy_only=i_hy_only, i_hz_only=i_hz_only,
                             # hx_red=hx_red, hz_red=hz_red, hx_red_ker=hx_red_ker, hz_red_ker=hz_red_ker,
                             hx_red=None, hz_red=None, hx_red_ker=None, hz_red_ker=None,
                         det_index=det_index,
                         dx=dx,dz=dz,
                         i_dx_in_hx=i_dx_in_hx,i_dz_in_hz=i_dz_in_hz,big_matrix=csc_matrix(big_matrix.astype('uint8')))
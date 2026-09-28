"""
MIT License

Copyright (c) 2024 Anqi Gong

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import stim
from codes_q import *

def build_circuit(code, A_list, B_list, p,p1,p2,p3,p4,num_repeat, z_basis=True, use_both=False, HZH=False,use_hperp = False):
    #code taken from https://github.com/gongaa/SlidingWindowDecoder
    n = code.N
    a1, a2, a3 = A_list
    b1, b2, b3 = B_list

    def nnz(m):
        a, b = m.nonzero()
        return b[np.argsort(a)]

    A1, A2, A3 = nnz(a1), nnz(a2), nnz(a3)
    B1, B2, B3 = nnz(b1), nnz(b2), nnz(b3)

    A1_T, A2_T, A3_T = nnz(a1.T), nnz(a2.T), nnz(a3.T)
    B1_T, B2_T, B3_T = nnz(b1.T), nnz(b2.T), nnz(b3.T)

    # |+> ancilla: 0 ~ n/2-1. Control in CNOTs.
    X_check_offset = 0
    # L data qubits: n/2 ~ n-1. 
    L_data_offset = n // 2
    # R data qubits: n ~ 3n/2-1.
    R_data_offset = n
    # |0> ancilla: 3n/2 ~ 2n-1. Target in CNOTs.
    Z_check_offset = 3 * n // 2

    p_after_clifford_depolarization = p1
    p_after_reset_flip_probability = p2
    p_before_measure_flip_probability = p3
    p_before_round_data_depolarization = p4

    detector_circuit_str = ""
    for i in range(n // 2):
        detector_circuit_str += f"DETECTOR rec[{-n // 2 + i}]\n"
    detector_circuit = stim.Circuit(detector_circuit_str)

    detector_repeat_circuit_str = ""
    for i in range(n // 2):
        detector_repeat_circuit_str += f"DETECTOR rec[{-n // 2 + i}] rec[{-n - n // 2 + i}]\n"
    detector_repeat_circuit = stim.Circuit(detector_repeat_circuit_str)

    def append_blocks(circuit, repeat=False):
        # Round 1
        if repeat:
            for i in range(n // 2):
                # measurement preparation errors
                circuit.append("X_ERROR", Z_check_offset + i, p_after_reset_flip_probability)
                if HZH:
                    circuit.append("X_ERROR", X_check_offset + i, p_after_reset_flip_probability)
                    circuit.append("H", [X_check_offset + i])
                    circuit.append("DEPOLARIZE1", X_check_offset + i, p_after_clifford_depolarization)
                else:
                    circuit.append("Z_ERROR", X_check_offset + i, p_after_reset_flip_probability)
                # identity gate on R data
                circuit.append("DEPOLARIZE1", R_data_offset + i, p_before_round_data_depolarization)
        else:
            for i in range(n // 2):
                circuit.append("H", [X_check_offset + i])
                if HZH:
                    circuit.append("DEPOLARIZE1", X_check_offset + i, p_after_clifford_depolarization)

        for i in range(n // 2):
            # CNOTs from R data to to Z-checks
            circuit.append("CNOT", [R_data_offset + A1_T[i], Z_check_offset + i])
            circuit.append("DEPOLARIZE2", [R_data_offset + A1_T[i], Z_check_offset + i],
                           p_after_clifford_depolarization)
            # identity gate on L data
            circuit.append("DEPOLARIZE1", L_data_offset + i, p_before_round_data_depolarization)

        # tick
        circuit.append("TICK")

        # Round 2
        for i in range(n // 2):
            # CNOTs from X-checks to L data
            circuit.append("CNOT", [X_check_offset + i, L_data_offset + A2[i]])
            circuit.append("DEPOLARIZE2", [X_check_offset + i, L_data_offset + A2[i]], p_after_clifford_depolarization)
            # CNOTs from R data to Z-checks
            circuit.append("CNOT", [R_data_offset + A3_T[i], Z_check_offset + i])
            circuit.append("DEPOLARIZE2", [R_data_offset + A3_T[i], Z_check_offset + i],
                           p_after_clifford_depolarization)

        # tick
        circuit.append("TICK")

        # Round 3
        for i in range(n // 2):
            # CNOTs from X-checks to R data
            circuit.append("CNOT", [X_check_offset + i, R_data_offset + B2[i]])
            circuit.append("DEPOLARIZE2", [X_check_offset + i, R_data_offset + B2[i]], p_after_clifford_depolarization)
            # CNOTs from L data to Z-checks
            circuit.append("CNOT", [L_data_offset + B1_T[i], Z_check_offset + i])
            circuit.append("DEPOLARIZE2", [L_data_offset + B1_T[i], Z_check_offset + i],
                           p_after_clifford_depolarization)

        # tick
        circuit.append("TICK")

        # Round 4
        for i in range(n // 2):
            # CNOTs from X-checks to R data
            circuit.append("CNOT", [X_check_offset + i, R_data_offset + B1[i]])
            circuit.append("DEPOLARIZE2", [X_check_offset + i, R_data_offset + B1[i]], p_after_clifford_depolarization)
            # CNOTs from L data to Z-checks
            circuit.append("CNOT", [L_data_offset + B2_T[i], Z_check_offset + i])
            circuit.append("DEPOLARIZE2", [L_data_offset + B2_T[i], Z_check_offset + i],
                           p_after_clifford_depolarization)

        # tick
        circuit.append("TICK")

        # Round 5
        for i in range(n // 2):
            # CNOTs from X-checks to R data
            circuit.append("CNOT", [X_check_offset + i, R_data_offset + B3[i]])
            circuit.append("DEPOLARIZE2", [X_check_offset + i, R_data_offset + B3[i]], p_after_clifford_depolarization)
            # CNOTs from L data to Z-checks
            circuit.append("CNOT", [L_data_offset + B3_T[i], Z_check_offset + i])
            circuit.append("DEPOLARIZE2", [L_data_offset + B3_T[i], Z_check_offset + i],
                           p_after_clifford_depolarization)

        # tick
        circuit.append("TICK")

        # Round 6
        for i in range(n // 2):
            # CNOTs from X-checks to L data
            circuit.append("CNOT", [X_check_offset + i, L_data_offset + A1[i]])
            circuit.append("DEPOLARIZE2", [X_check_offset + i, L_data_offset + A1[i]], p_after_clifford_depolarization)
            # CNOTs from R data to Z-checks
            circuit.append("CNOT", [R_data_offset + A2_T[i], Z_check_offset + i])
            circuit.append("DEPOLARIZE2", [R_data_offset + A2_T[i], Z_check_offset + i],
                           p_after_clifford_depolarization)

        # tick
        circuit.append("TICK")

        # Round 7
        for i in range(n // 2):
            # CNOTs from X-checks to L data
            circuit.append("CNOT", [X_check_offset + i, L_data_offset + A3[i]])
            circuit.append("DEPOLARIZE2", [X_check_offset + i, L_data_offset + A3[i]], p_after_clifford_depolarization)
            # Measure Z-checks
            circuit.append("X_ERROR", Z_check_offset + i, p_before_measure_flip_probability)
            circuit.append("MR", [Z_check_offset + i])
            # identity gates on R data, moved to beginning of the round
            # circuit.append("DEPOLARIZE1", R_data_offset + i, p_before_round_data_depolarization)

        # Z check detectors
        if z_basis:
            if repeat:
                circuit += detector_repeat_circuit
            else:
                circuit += detector_circuit
        elif use_both and repeat:
            circuit += detector_repeat_circuit

        # tick
        circuit.append("TICK")

        # Round 8
        for i in range(n // 2):
            if HZH:
                circuit.append("H", [X_check_offset + i])
                circuit.append("DEPOLARIZE1", X_check_offset + i, p_after_clifford_depolarization)
                circuit.append("X_ERROR", X_check_offset + i, p_before_measure_flip_probability)
                circuit.append("MR", [X_check_offset + i])
            else:
                circuit.append("Z_ERROR", X_check_offset + i, p_before_measure_flip_probability)
                circuit.append("MRX", [X_check_offset + i])
            # identity gates on L data, moved to beginning of the round
            # circuit.append("DEPOLARIZE1", L_data_offset + i, p_before_round_data_depolarization)

        # X basis detector
        if not z_basis:
            if repeat:
                circuit += detector_repeat_circuit
            else:
                circuit += detector_circuit
        elif use_both and repeat:
            circuit += detector_repeat_circuit

        # tick
        circuit.append("TICK")

    circuit = stim.Circuit()
    for i in range(n // 2):  # ancilla initialization
        circuit.append("R", X_check_offset + i)
        circuit.append("R", Z_check_offset + i)
        circuit.append("X_ERROR", X_check_offset + i, p_after_reset_flip_probability)
        circuit.append("X_ERROR", Z_check_offset + i, p_after_reset_flip_probability)
    for i in range(n):
        circuit.append("R" if z_basis else "RX", L_data_offset + i)
        circuit.append("X_ERROR" if z_basis else "Z_ERROR", L_data_offset + i, p_after_reset_flip_probability)

    # begin round tick
    circuit.append("TICK")
    append_blocks(circuit, repeat=False)  # encoding round

    rep_circuit = stim.Circuit()
    append_blocks(rep_circuit, repeat=True)
    circuit += (num_repeat - 1) * rep_circuit

    for i in range(0, n):
        # flip before collapsing data qubits
        # circuit.append("X_ERROR" if z_basis else "Z_ERROR", L_data_offset + i, p_before_measure_flip_probability)
        circuit.append("M" if z_basis else "MX", L_data_offset + i)

    pcm = code.hz if z_basis else code.hx
    # pcm = code.hx_perp if z_basis else code.hx # maan edit
    logical_pcm = code.lz if z_basis else code.lx

    stab_detector_circuit_str = ""  # stabilizers
    for i, s in enumerate(pcm):
        nnz = np.nonzero(s)[0]
        det_str = "DETECTOR"
        for ind in nnz:
            det_str += f" rec[{-n + ind}]"
        det_str += f" rec[{-n - n + i}]" if z_basis else f" rec[{-n - n // 2 + i}]"
        det_str += "\n"
        stab_detector_circuit_str += det_str
    stab_detector_circuit = stim.Circuit(stab_detector_circuit_str)
    circuit += stab_detector_circuit

    if use_hperp:
        if z_basis:
            l_in_hperp = (code.hx_perp[:, None] == code.lz).all(-1).any(1) #lz_in_hxperp
            hperp_wo_l = code.hx_perp[np.nonzero(l_in_hperp==0)[0],:]  #hxperp without lz
            l_app_hperp = np.append(code.lz,hperp_wo_l,axis=0) #lz append hxperp
        else:
            l_in_hperp = (code.hz_perp[:, None] == code.lx).all(-1).any(1)
            hperp_wo_l = code.hz_perp[np.nonzero(l_in_hperp == 0)[0], :]
            l_app_hperp = np.append(code.lx, hperp_wo_l,axis=0)  # lx append hzperp
        log_detector_circuit_str = ""  # logical operators
        for i, l in enumerate(l_app_hperp):
            nnz = np.nonzero(l)[0]
            det_str = f"OBSERVABLE_INCLUDE({i})"
            for ind in nnz:
                det_str += f" rec[{-n + ind}]"
            det_str += "\n"
            log_detector_circuit_str += det_str
        log_detector_circuit = stim.Circuit(log_detector_circuit_str)
        circuit += log_detector_circuit
    else:
        log_detector_circuit_str = ""  # logical operators
        for i, l in enumerate(logical_pcm):
            nnz = np.nonzero(l)[0]
            det_str = f"OBSERVABLE_INCLUDE({i})"
            for ind in nnz:
                det_str += f" rec[{-n + ind}]"
            det_str += "\n"
            log_detector_circuit_str += det_str
        log_detector_circuit = stim.Circuit(log_detector_circuit_str)
        circuit += log_detector_circuit

    return circuit


import stim
import sinter
# from beliefmatching import detector_error_model_to_check_matrices
from ldpc.ckt_noise.dem_matrices import detector_error_model_to_check_matrices
# import beliefmatching
from ldpc.bposd_decoder import BpOsdDecoder
from ldpc.bp_decoder import BpDecoder
from helper_functions import bb_circuit,surface_code_one_basis_circuit,det_and_err_encoding,a_in_b_idx,build_Hcols_Hrows
from codes_q import *
from ldpc.mod2 import *
import pymatching
import pickle
import os

# from ldpc.ckt_noise.not_an_arb_ckt_simulator import get_stabilizer_time_steps, stim_circuit_from_time_steps
import numpy as np
import time
# import my_decoders.qec_stim_tests_serial_EQUIP_meeting_fast as fast_bp
from my_decoders.hbplib_wrapper_v2 import ldpc_dec_msaa_quantum_serial_big_matrix_c, ldpc_dec_msaa_quantum_serial_big_matrix_c_ensemble_batched_ler
import hashlib


def main(dist,p, itrs, msf, rs,shots, cs, max_errs, priort,ens,poi, num_threads=None):
    # Better thread handling: use specified threads or default to 1
    if num_threads is None or num_threads <= 0:
        num_threads = 1
    print(f"Using {num_threads} thread(s) for parallel processing")
    
    d = dist
    r = d
    noise_model = 'CL'

    temp_p = 0.001  # temp p value to generate circuit to make big matrix
    p = p
    z_basis = True
    use_both = True
    use_hperp = False
    HZH = False
    decompose_error = False
    bp_method = "ms"
    schedule = "serial"

    mitr = itrs
    msf = msf
    rs = rs
    prt = priort
    cs = cs  # custom schduling
    et = 1  # early stopping
    poi = poi  # prob= 'w' or itr 'i'
    ens = ens

    num_shots = shots



    decoders = 0
    filepath = 0
    filepath_fig = 0
    if ens == 0:
        decoders = [f'HBP_etB_corr_big_sr_{mitr}_{msf}_{rs}_{prt}_{cs}_et{et}']
        filepath = f"data/BB_etB_corr_{mitr}_{msf}_{rs}_{prt}_{cs}_et{et}_d{d}_{os.getenv('SLURM_JOB_ID')}.csv"
        filepath_fig = f"data/BB_corr_{mitr}_{msf}_{rs}_{prt}_{cs}_et{et}_d{d}_{os.getenv('SLURM_JOB_ID')}.png"
    else:
        decoders = [f'HBP_etB_corr_big_sr_{mitr}_{msf}_{rs}_{prt}_{cs}_et{et}_en{ens}_{poi}']
        filepath = f"data/BB_etB_corr_{mitr}_{msf}_{rs}_{prt}_{cs}_et{et}_en{ens}_{poi}_d{d}_{os.getenv('SLURM_JOB_ID')}.csv"
        filepath_fig = f"data/BB_corr_{mitr}_{msf}_{rs}_{prt}_{cs}_et{et}_en{ens}_{poi}_d{d}_{os.getenv('SLURM_JOB_ID')}.png"

    print(f"distance {d} rounds {r}, num_shots = {num_shots}, {noise_model} noise at {p}")
    print(f"max iter = {mitr}, bp method = {bp_method}, msf = {msf}, schedule = {schedule}, random_schedule_seed = {rs}")
    print(f"decompose_error: {decompose_error},z_basis: {z_basis}, use_both_basis: {use_both}, use_hperp_in_circuit: {use_hperp}, HZH:{HZH}")
    print(f"prior type,0 or 1 = direct or 2 = sum: {prt}")
    print(f"use horizontal bp: True, custom_random_schedule_HBP: {cs}, early_stopping: {et}")
    print(f"num shots = {num_shots}, num_threads = {num_threads}")
    print(decoders)

    if noise_model == "CL":
        p1 = p2 = p3 = p4 = p
    if noise_model == 'PH':
        p1 = 0
        p2 = p3 = p4 = p
    if noise_model == 'CC':
        p1 = p2 = p3 = 0
        p4 = p

    if use_both:
        noise_model += f"_both"
    else:
        noise_model += f"_zdet"


    if d % 2 == 0:
        circuit = None
        _,code = bb_circuit(d, p=0,p1=0,p2=0,p3=0,p4=0,r=d)
        # fname = f"data/circuits/{code.name}_d{d}_{noise_model}_{p}.stim"
        try:
            fname = f"data/circuits/{code.name}_d{d}_{noise_model}_{p}.stim"
            # fname = f"data/circuits/circuit_d6_memz_ibm.stim"
            circuit = stim.Circuit.from_file(fname)
        # circuit_tmp = stim.Circuit.from_file(fname)
        # tmp_string = str(circuit_tmp)
        # tmp_string = tmp_string.replace('0.001', str(p))
        # circuit = stim.Circuit(tmp_string)
        except:
            circuit, code = bb_circuit(d, p,p1=p1,p2=p2,p3=p3,p4=p4,r=r,z_basis=z_basis,use_both=use_both,HZH=HZH,use_hperp = use_hperp)
            fname = f"data/circuits/{code.name}_d{d}_{noise_model}_{p}.stim"
            with open(fname, 'w') as file:
                circuit.to_file(file)
        # circuit2, _ = bb_circuit(d, p,p1=0,p2=p,p3=p,p4=p,r=r,z_basis=z_basis,use_both=use_both,HZH=False,use_hperp = False)
    else:
        code = create_rotated_surface_codes(d)
        circuit = stim.Circuit.generated(
            "surface_code:rotated_memory_z",
            distance=d,
            rounds=r,
            after_clifford_depolarization=p1,
            after_reset_flip_probability=p2,
            before_measure_flip_probability=p3,
            before_round_data_depolarization=p4)

        if not use_both:
            circuit = surface_code_one_basis_circuit(d, r, circuit.flattened().copy(), z_basis=z_basis)

        # circuit2 = circuit

    # fname = f"data/circuits/{code.name}_d{d}_{noise_model}_{p}.stim"
    # with open(fname, 'w') as file:
    #     circuit.to_file(file)
    print("circuit done")
    dem = circuit.detector_error_model(decompose_errors=decompose_error,flatten_loops=True, ignore_decomposition_failures=True)
    matrices = detector_error_model_to_check_matrices(dem, allow_undecomposed_hyperedges=True)
    print("dem and matrices done")
    # all_matrices_xz = det_and_err_encoding(d, matrices, circuit)

    all_matrices_xz = None
    try:
        print("trying to read all_matrices_xz ...")
        all_matrices_xz = pickle.load(open(f'data/circuits/{code.name}_d{d}_{noise_model}_matrices.pkl', 'rb'))
        print("all_matrices_xz read ...")
        # from scipy.sparse import csc_matrix
        # all_matrices_xz.big_matrix = csc_matrix(all_matrices_xz.big_matrix)
    except:
        print("could not read. So calculating all_matrices_xz...")
        all_matrices_xz = det_and_err_encoding(d, matrices, circuit)
        print("all_matrices_xz calculated ...")
        with open(f"data/circuits/{code.name}_d{d}_{noise_model}_matrices.pkl", 'wb') as file:
            # A new file will be created
            pickle.dump(all_matrices_xz, file, protocol=pickle.HIGHEST_PROTOCOL)

    Hcols, Hrows = 0,0
    try:
        Hcols, Hrows = pickle.load(open(f'data/circuits/{code.name}_d{d}_{noise_model}_hcols_hrows.pkl', 'rb'))
        print("Hcols, Hrows read ...")
    except:
        Hcols, Hrows = build_Hcols_Hrows(all_matrices_xz.big_matrix.toarray())
        print("Hcols, Hrows calculated ...")
        with open(f"data/circuits/{code.name}_d{d}_{noise_model}_hcols_hrows.pkl", 'wb') as file:
            # A new file will be created
            pickle.dump((Hcols, Hrows), file, protocol=pickle.HIGHEST_PROTOCOL)



    h = matrices.check_matrix.toarray().astype(np.int8)
    l = matrices.observables_matrix.toarray().astype(np.int8)
    big_matrix_shape = all_matrices_xz.big_matrix.shape
    print("freeing up big_matrix ...")
    all_matrices_xz.big_matrix = None
    det_index = all_matrices_xz.det_index

    hxz = (matrices.check_matrix.toarray().T * det_index).T
    hx = matrices.check_matrix.toarray()[np.where(det_index == 1)[0]]
    hz = matrices.check_matrix.toarray()[np.where(det_index == 3)[0]]


    m, n = h.shape
    mx, nx = all_matrices_xz.dx.shape
    mz, nz = all_matrices_xz.dz.shape

    i_hx_only = all_matrices_xz.i_hx_only
    i_hz_only = all_matrices_xz.i_hz_only
    i_hy_only = all_matrices_xz.i_hy_only

    l_dz = l[:, all_matrices_xz.i_hz_only]

    n_total_ler_dz_count = 0
    try:
        file = open(filepath, 'r')
        try:
            n_total_ler_dz_count = sinter.stats_from_csv_files(filepath)[0].errors
            print(f"ERROR: {filepath} already has {n_total_ler_dz_count} errors")
        except:
            print(f"ERROR: {filepath} does not have any errors, appending to the header of the file...")
        else:
            if sinter.stats_from_csv_files(filepath)[0].errors >= max_errs:
                print(f"ERROR: {filepath} already has {sinter.stats_from_csv_files(filepath)[0].errors} errors, skipping and printing stats...")
                print(f"logical error rate per round = {sinter.shot_error_rate_to_piece_error_rate(sinter.stats_from_csv_files(filepath)[0].errors / sinter.stats_from_csv_files(filepath)[0].shots, pieces=r, values=code.K)}")
                stats = sinter.stats_from_csv_files(filepath)
                for stat in stats:
                    print(repr(stat))
                return
    except:
        with open(filepath, 'w+') as file:
            print(sinter.CSV_HEADER,file=file)
        print("created new file ...")


    """ priors"""
    priors_big = np.zeros(big_matrix_shape[1], dtype="float")
    priors_ab = np.zeros(nx + nz, dtype="float")
    for i in range(nx):
        # aaa= matrices.priors[np.where(i_dx_in_hx == i)[0]]
        priors_ab[i] = np.sum(matrices.priors[np.where(all_matrices_xz.i_dx_in_hx == i)[0]])
    for i in range(nz):
        # aaa= matrices.priors[np.where(i_dz_in_hz == i)[0]]
        priors_ab[nx + i] = np.sum(matrices.priors[np.where(all_matrices_xz.i_dz_in_hz == i)[0]])

    if prt == 0:
        priors_big[:nx + nz] = 0.5  # zero llr
    elif prt == 2:
        priors_big[:nx + nz] = priors_ab
    else:
        raise NotImplementedError
    # priors_big[nx+nz:] = matrices.priors
    priors_big[nx + nz:2 * nx + nz] = matrices.priors[all_matrices_xz.i_hx_only]
    priors_big[2 * nx + nz:2 * (nx + nz)] = matrices.priors[all_matrices_xz.i_hz_only]
    priors_big[2 * (nx + nz):] = matrices.priors[all_matrices_xz.i_hy_only]

    # Configure a decoder using the circuit.

    llr = np.log((1 - priors_big) / priors_big)
    llr_ab = np.log((1 - priors_ab) / priors_ab)

    chunks_until_max_shots = 10**9 // num_shots
    not_converged = None
    introduced_ler = None
    print("i, \tp, \terror_cound_so_far, \tnum_shots, \tn_fail, \trf_dz_tot, \trf_dz_tot_per_r, \tconverge_itr, \tTime ")
    for chunki in range(chunks_until_max_shots):
        st_dem = time.time()
        dem_sampler: stim.CompiledDemSampler = dem.compile_sampler()
        # det_data, obs_data, err_data = dem_sampler.sample(shots=num_shots, return_errors=True, bit_packed=False)
        # det_data = det_data.astype("int8")
        # obs_data = obs_data.astype("int8")
        # err_data = err_data.astype("int8")

        det_data, obs_data,_ = dem_sampler.sample(shots=num_shots, bit_packed=False)
        det_data = det_data.astype("int8")
        obs_data = obs_data.astype("int8")
        # print(f"DEBUG: dem sampler completed successfully! in {time.time() - st_dem} seconds")
        # print(f"{len(np.unique(err_data,axis=0))} unique in train set")



        """ extend det data """
        det_data_big_matrix = np.zeros((num_shots,big_matrix_shape[0]),dtype='int8')
        det_data_big_matrix[:,:mx] = det_data[:,np.where(det_index == 1)[0]] # X det = detects z error
        det_data_big_matrix[:,mx:m] = det_data[:,np.where(det_index == 3)[0]] # Z det = detects x error

        """ extend err data """

        # print("error calculation done")


        detectors_bin_batch = 1 - 2 * det_data_big_matrix.astype(np.int8)


        llr_batch = llr  # 1D array of length N with LLR values same for each shot
        llr_ab_batch = llr_ab  # 1D array of length N with LLR values same for each shot

        # Configure batch processing parameters
        batch_size = num_shots
        st = time.time()

        if ens==0:
            ens=1
        logical_errors_out_ens, iterations_out_ens = ldpc_dec_msaa_quantum_serial_big_matrix_c_ensemble_batched_ler(
            llr_batch, llr_ab_batch, batch_size, mitr,
            Hrows, Hcols,
            msf, detectors_bin_batch,
            rs, h.shape, all_matrices_xz.dx.shape,
            ens, poi,
            nx, nz, mx, m,
            all_matrices_xz.dz, l_dz,
            cs, early_stopping=bool(et), num_threads=num_threads
        )


        et = time.time()

        ''' total logical error'''

        n_total_ler_dz = np.any((logical_errors_out_ens+obs_data) % 2, axis=1).sum()

        ler_per_round_dz = sinter.shot_error_rate_to_piece_error_rate(n_total_ler_dz / num_shots, pieces=r, values=code.K)
        avg_itr_converge_dz = iterations_out_ens.mean()
        n_total_ler_dz_count += n_total_ler_dz
        print(f"{chunki}, \t{p}, \t{n_total_ler_dz_count}, \t{num_shots}, \t{n_total_ler_dz}, \t{n_total_ler_dz/num_shots }, \t{ler_per_round_dz}, \t{round(avg_itr_converge_dz,2)}, \t{round(et - st,2)}, "
              # f"\t{n_total_ler_dz / num_shots}, \t{ler_per_round_dz} \t{round(converge_itr[converge_itr < (mitr)].mean())},"
              # f"\t{np.any((rf_big[:, :nx] @ dx.T) % 2, axis=1).sum() / num_shots}, \t{np.any((rf_big[:, nx:nx + nz] @ dz.T) % 2, axis=1).sum() / num_shots},"
              # f"\t{convergence_dz_count/num_shots}"
              )
        json_metadata = {'p': p,'d': d,'rounds': r,}
        sha = hashlib.sha256()
        sha.update((decoders[0]+f"_d{d}_p{p}_r{r}").encode())
        strong_id = sha.hexdigest()
        csv_line = sinter._data._csv_out.csv_line(shots=num_shots,errors=n_total_ler_dz,discards=0,seconds=round(et-st),decoder=decoders[0],strong_id=strong_id,json_metadata=json_metadata,custom_counts={'avg_itr': round(avg_itr_converge_dz),'base':1})
        print(csv_line, file=open(filepath, 'a'))




        if n_total_ler_dz_count >= max_errs:
            print(f"ERROR: {filepath} has {sinter.stats_from_csv_files(filepath)[0].errors} errors now, printing stats...")
            stats = sinter.stats_from_csv_files(filepath)
            for stat in stats:
                print(repr(stat))
            break

    print(f"logical error rate per round = {sinter.shot_error_rate_to_piece_error_rate(sinter.stats_from_csv_files(filepath)[0].errors / sinter.stats_from_csv_files(filepath)[0].shots, pieces=r, values=code.K)}")


if __name__ == '__main__':
    dist = 6
    p= 0.002
    itrs = 400
    msf = 0.96875
    rs = 1
    priort = 0
    cs = 2
    shots = 1024*16
    max_errs = 100
    ens = 0
    poi = 'i'
    num_threads = 4  # Default to None (will use 1 thread)
    import sys

    if len(sys.argv) - 1 == 1:
        dist = int(sys.argv[1])
    if len(sys.argv) - 1 == 6:
        dist = int(sys.argv[1])
        itrs = int(sys.argv[2])
        msf = float(sys.argv[3])
        rs = int(sys.argv[4])
        shots = 1024*int(sys.argv[5])
        priort = int(sys.argv[6])
    if len(sys.argv) - 1 == 12:
        dist = int(sys.argv[1])
        p = float(sys.argv[2])
        itrs = int(sys.argv[3])
        msf = float(sys.argv[4])
        rs = int(sys.argv[5])
        priort = int(sys.argv[6])
        cs = int(sys.argv[7])
        shots = 1024*int(sys.argv[8])
        max_errs = int(sys.argv[9])
        ens = int(sys.argv[10])
        poi = sys.argv[11]
        num_threads = int(sys.argv[12])
    # print(dist,"\n",shots)
    # print(sys.argv[1],sys.argv[2],len(sys.argv))
    main(dist,p, itrs, msf, rs, shots, cs=cs, max_errs=max_errs, priort=priort,ens=ens,poi=poi,num_threads=num_threads)
    # main()

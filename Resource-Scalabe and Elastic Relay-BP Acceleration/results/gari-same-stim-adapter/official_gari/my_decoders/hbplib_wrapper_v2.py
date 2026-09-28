import ctypes
import numpy as np

# Cargar biblioteca compartida
lib = ctypes.CDLL('my_decoders/hbplib_v2.so')

# Signature of the method
lib.ldpc_dec_msaa_quantum_serial_big_matrix_c.argtypes = [
    ctypes.POINTER(ctypes.c_double), ctypes.c_int,
    ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int,
    ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int,
    ctypes.c_double, ctypes.POINTER(ctypes.c_int8),
    ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int,
    ctypes.POINTER(ctypes.c_int8), ctypes.POINTER(ctypes.c_double)
]
lib.ldpc_dec_msaa_quantum_serial_big_matrix_c.restype = ctypes.c_int

def ldpc_dec_msaa_quantum_serial_big_matrix_c(
    llr, Nloop,
    Hrows,
    Hcols,
    alpha, Syn_x,
    random_order, hshape, dxshape,
    custom_random_schedule_HBP=0,
    early_stopping=False
):
    # Convertir a tipos C
    llr = np.ascontiguousarray(llr, dtype=np.float64)
    Hrows = np.ascontiguousarray(Hrows, dtype=np.int32)
    Hcols = np.ascontiguousarray(Hcols, dtype=np.int32)
    Syn_x = np.ascontiguousarray(Syn_x, dtype=np.int8)

    N = llr.shape[0]
    # Hdec_out = np.zeros((Nloop + 1, N), dtype=np.int8)
    Hdec_out = np.zeros(N, dtype=np.int8)
    # Hdec_out = (ctypes.c_int8 * ((Nloop + 1) * N))()
    lambda_out = np.zeros(N, dtype=np.float64)

    iters = lib.ldpc_dec_msaa_quantum_serial_big_matrix_c(
        # double* llr, int Nloop,
        llr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), ctypes.c_int(Nloop),
        # int* Hrows, int Hrows_r, int Hrows_c,
        Hrows.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), ctypes.c_int(Hrows.shape[0]), ctypes.c_int(Hrows.shape[1]),
        # int* Hcols, int Hcols_r, int Hcols_c,
        Hcols.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), ctypes.c_int(Hcols.shape[0]), ctypes.c_int(Hcols.shape[1]),
        # double alpha, int8_t* Syn_x,
        ctypes.c_double(alpha), Syn_x.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
        # int random_order, int hshape0, int dxshape0,
        ctypes.c_int(random_order), ctypes.c_int(hshape[0]), ctypes.c_int(dxshape[0]),
        # int custom_random_schedule_HBP, int early_stopping,
        ctypes.c_int(custom_random_schedule_HBP), ctypes.c_int(early_stopping),
        Hdec_out.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
        lambda_out.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
    )
    if iters > Nloop:
        iters = Nloop

    return Hdec_out, iters, lambda_out


# Batched Ensemble Decoding Function signature
lib.ldpc_dec_msaa_quantum_serial_big_matrix_c_ensemble_batched_ler.argtypes = [
    ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_int, ctypes.c_int,  # llr_batch, llr_ab_batch, batch_size, N, Nloop
    ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int,  # Hrows, Hrows_r, Hrows_c
    ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_int,  # Hcols, Hcols_r, Hcols_c
    ctypes.c_double, ctypes.POINTER(ctypes.c_int8),  # alpha, Syn_x_batch
    ctypes.c_int, ctypes.c_int, ctypes.c_int,  # random_order, hshape0, dxshape0
    ctypes.c_int, ctypes.c_int, ctypes.c_int,  # custom_random_schedule_HBP, early_stopping, num_threads
    ctypes.c_int, ctypes.c_char,  # ensemble_size, prob_or_itr
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,  # nx, nz, mx, m
    ctypes.POINTER(ctypes.c_int8), ctypes.c_int, ctypes.c_int,  # dz, dz_rows, dz_cols
    ctypes.POINTER(ctypes.c_int8), ctypes.c_int, ctypes.c_int,  # l_dz, l_dz_rows, l_dz_cols
    ctypes.POINTER(ctypes.c_int8), ctypes.POINTER(ctypes.c_int)  # logical_errors_out, iterations_out
]
lib.ldpc_dec_msaa_quantum_serial_big_matrix_c_ensemble_batched_ler.restype = None


def ldpc_dec_msaa_quantum_serial_big_matrix_c_ensemble_batched_ler(
    llr_batch, llr_ab_batch, batch_size, Nloop,
    Hrows, Hcols,
    alpha, Syn_x_batch,
    random_order, hshape, dxshape,
    ensemble_size, prob_or_itr,
    nx, nz, mx, m,
    dz, l_dz,
    custom_random_schedule_HBP=0,
    early_stopping=False,
    num_threads=0
):
    """
    Batched LDPC decoder with ensemble decoding
    
    Parameters:
    - llr_batch: 1D array of length N with LLR values same for each shot
    - llr_ab_batch: 1D array of length N with LLR values same for each shot
    - batch_size: number of shots to process
    - ensemble_size: number of ensemble runs per shot
    - prob_or_itr: 'w' for weight-based, 'i' for iteration-based selection
    - Syn_x_batch: 2D array of shape (batch_size, Hrows_r) with syndrome data
    - nx, nz, mx, m: matrix dimensions
    - dz: Z stabilizer matrix
    - l_dz: logical operator matrix for Z errors
    - num_threads: number of OpenMP threads (0 = auto-detect)
    
    Returns:
    - logical_errors_out: 2D array of logical error rates for all shots
    - iterations_out: 1D array of iteration counts for each shot (best ensemble)
    """
    # Convert to C types and ensure contiguous arrays
    llr_batch = np.ascontiguousarray(llr_batch, dtype=np.float64)
    llr_ab_batch = np.ascontiguousarray(llr_ab_batch, dtype=np.float64)
    Hrows = np.ascontiguousarray(Hrows, dtype=np.int32)
    Hcols = np.ascontiguousarray(Hcols, dtype=np.int32)
    Syn_x_batch = np.ascontiguousarray(Syn_x_batch, dtype=np.int8)
    dz = np.ascontiguousarray(dz, dtype=np.int8)
    l_dz = np.ascontiguousarray(l_dz, dtype=np.int8)
    
    N = llr_batch.shape[0]  # 1D array, so N is the first (and only) dimension
    
    # Allocate output arrays
    logical_errors_out = np.zeros((batch_size, l_dz.shape[0]), dtype=np.int8)
    iterations_out = np.zeros(batch_size, dtype=np.int32)
    # print("hey almost in c")
    lib.ldpc_dec_msaa_quantum_serial_big_matrix_c_ensemble_batched_ler(
        # Input arrays
        llr_batch.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        llr_ab_batch.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        ctypes.c_int(batch_size), ctypes.c_int(N), ctypes.c_int(Nloop),
        # Matrix data
        Hrows.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), 
        ctypes.c_int(Hrows.shape[0]), ctypes.c_int(Hrows.shape[1]),
        Hcols.ctypes.data_as(ctypes.POINTER(ctypes.c_int)), 
        ctypes.c_int(Hcols.shape[0]), ctypes.c_int(Hcols.shape[1]),
        # Parameters
        ctypes.c_double(alpha),
        Syn_x_batch.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
        ctypes.c_int(random_order), ctypes.c_int(hshape[0]), ctypes.c_int(dxshape[0]),
        ctypes.c_int(custom_random_schedule_HBP), ctypes.c_int(early_stopping),
        ctypes.c_int(num_threads),
        # Ensemble parameters
        ctypes.c_int(ensemble_size), ctypes.c_char(ord(prob_or_itr)),
        # Matrix dimensions
        ctypes.c_int(nx), ctypes.c_int(nz), ctypes.c_int(mx), ctypes.c_int(m),
        # Matrices
        dz.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
        ctypes.c_int(dz.shape[0]), ctypes.c_int(dz.shape[1]),
        l_dz.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
        ctypes.c_int(l_dz.shape[0]), ctypes.c_int(l_dz.shape[1]),
        # Output arrays
        logical_errors_out.ctypes.data_as(ctypes.POINTER(ctypes.c_int8)),
        iterations_out.ctypes.data_as(ctypes.POINTER(ctypes.c_int))
    )
    
    return logical_errors_out, iterations_out
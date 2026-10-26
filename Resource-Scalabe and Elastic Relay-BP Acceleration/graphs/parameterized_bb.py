"""BB algebra in the existing positive-shift convention; distance is unknown."""
from pathlib import Path
import hashlib, json, sys
import numpy as np
from scipy import sparse
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
sys.path.insert(0,str(HERE))
import bb_code
GARI=ROOT/'results/gari-same-stim-adapter/official_gari'
sys.path.insert(0,str(GARI))
from codes_q import css_code
from utils import rank
from build_circuit import build_circuit

def normalized_terms(terms,l,m):
    if not isinstance(terms,(list,tuple)) or not terms:
        raise ValueError('Polynomial must be a nonempty list of [x_exponent,y_exponent] monomials')
    if any(not isinstance(t,(list,tuple)) or len(t)!=2 or any(type(v) is not int for v in t) for t in terms):
        raise ValueError('Each monomial requires two integer exponents')
    return [(x%l,y%m) for x,y in terms]

def construct(l,m,A,B):
    if type(l) is not int or type(m) is not int or l<1 or m<1:
        raise ValueError('l and m must be positive integers')
    a,b=normalized_terms(A,l,m),normalized_terms(B,l,m)
    aa=bb_code.build_block(tuple(a),l,m);bb=bb_code.build_block(tuple(b),l,m)
    hx=np.hstack((aa,bb));hz=np.hstack((bb.T,aa.T))
    if not bb_code.matrices_commute(hx,hz):raise ValueError('BB CSS checks do not commute')
    rx,rz=int(rank(hx)),int(rank(hz));k=2*l*m-rx-rz
    metadata=dict(l=l,m=m,A=[list(t) for t in a],B=[list(t) for t in b],n=2*l*m,k=k,d=None,rank_hx=rx,rank_hz=rz,
                  convention='index=x*m+y; row(x,y) connects column(x+dx,y+dy); Hx=[A B], Hz=[B.T A.T]; GF(2)',
                  matrix_sha256=hashlib.sha256(hx.tobytes()+hz.tobytes()).hexdigest())
    return hx,hz,metadata

def generate(l,m,A,B,p,rounds):
    hx,hz,metadata=construct(l,m,A,B)
    if not np.isfinite(p) or not 0<p<1:raise ValueError('physical_p must lie strictly between0 and1')
    if type(rounds) is not int or rounds<1:raise ValueError('rounds must be a positive integer')
    for name in ('A','B'):
        terms=[tuple(t) for t in metadata[name]]
        if len(terms)!=3 or len(set(terms))!=3:
            raise ValueError('Existing circuit schedule requires exactly three distinct modulo-torus monomials in '+name)
    if metadata['k']<1:raise ValueError('Memory-observable circuit requires k>0; algebraic k=0 codes are supported only as matrices')
    # None prevents the inherited class from attempting its expensive/non-quantum distance routine.
    code=css_code(hx,hz,code_distance=None,check_css=True)
    if code.K!=metadata['k']:raise ValueError('Independent code dimension disagreement')
    if (code.lz.shape!=(code.K,code.N) or np.any((hx@code.lz.T)%2)
            or int(rank((code.lx@code.lz.T)%2))!=code.K):
        raise ValueError('Logical quotient basis is invalid')
    parts=lambda name:[sparse.csr_matrix(bb_code.build_block((tuple(t),),l,m)) for t in metadata[name]]
    circuit=build_circuit(code,parts('A'),parts('B'),p,p,p,p,p,rounds,z_basis=True)
    try:circuit.detector_error_model(decompose_errors=False,flatten_loops=True)
    except ValueError as e:raise ValueError('Unsupported monomial ordering/circuit schedule: nondeterministic detectors or observables') from e
    ideal_detectors,ideal_observables=circuit.without_noise().compile_detector_sampler(seed=0).sample(2,separate_observables=True)
    if ideal_detectors.any() or ideal_observables.any():
        raise ValueError('Circuit does not preserve noiseless stabilizer/logical memory labels')
    metadata.update(noise_model='gari_uniform_p_memory_z',memory_basis='Z',distance_status='not computed',
                    logical_basis_sha256=hashlib.sha256(code.lz.tobytes()).hexdigest(),
                    generator_sources={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
                        (HERE/'bb_code.py',Path(__file__),GARI/'codes_q.py',GARI/'utils.py',GARI/'build_circuit.py')})
    return circuit,hx,hz,code.lz,metadata

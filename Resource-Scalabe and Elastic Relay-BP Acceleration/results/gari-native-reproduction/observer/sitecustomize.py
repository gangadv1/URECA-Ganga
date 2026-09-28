"""Passive observer: never changes GARI data, randomness, parameters, or decisions.
Records already-produced per-shot outputs after the native decoder timer stops.
"""
import os,sys,pathlib,json,time
_target='/tmp/gari-native-6380d52/stim_batched_data_v2.py'
_out=pathlib.Path(os.environ['GARI_CAPTURE_DIR'])
_line=next(i for i,s in enumerate(pathlib.Path(_target).read_text().splitlines(),1) if 'avg_itr_converge_dz = iterations_out_ens.mean()' in s)
def _local(frame,event,arg):
    if event=='line' and frame.f_lineno==_line:
        import numpy as np
        d=frame.f_locals
        np.savez_compressed(_out/f'chunk_{d["chunki"]:04d}.npz',iterations=d['iterations_out_ens'],predicted_observables=d['logical_errors_out_ens'],observed_observables=d['obs_data'])
        rec=dict(chunk=int(d['chunki']),shots=int(d['num_shots']),logical_errors=int(d['n_total_ler_dz']),decoder_seconds=float(d['et']-d['st']),iteration_mean=float(d['iterations_out_ens'].mean()),native_converged=int((d['iterations_out_ens']<d['mitr']).sum()),native_nonconverged=int((d['iterations_out_ens']==d['mitr']).sum()),dem_shape=list(d['h'].shape),expanded_shape=list(d['big_matrix_shape']),dx_shape=list(d['all_matrices_xz'].dx.shape),dz_shape=list(d['all_matrices_xz'].dz.shape),llr_finite=bool(np.isfinite(d['llr']).all()),llr_ab_finite=bool(np.isfinite(d['llr_ab']).all()))
        with (_out/'chunks.jsonl').open('a') as f:f.write(json.dumps(rec)+'\n')
    return _local

def _global(frame,event,arg):
    if event=='call' and frame.f_code.co_filename.endswith('/gari-native-6380d52/stim_batched_data_v2.py') and frame.f_code.co_name=='main':return _local
    return None
sys.settrace(_global)

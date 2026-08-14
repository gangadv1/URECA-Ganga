from pathlib import Path
import json,numpy as np
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;OUT.mkdir(exist_ok=True)
d=np.load(ROOT/'fpga/verification/memory_backed_intermediate/intermediate_input.npz');H=d['H'].astype(np.uint8);C,V=H.shape
rng=np.random.default_rng(38419);cases=[]
# Valid vector and its exact syndrome.
valid=rng.integers(0,2,V,dtype=np.uint8);cases.append(('valid',valid,(H@valid)%2))
pert=valid.copy();pert[0]^=1;cases.append(('one_bit_perturbation',pert,(H@valid)%2))
multi=rng.integers(0,2,V,dtype=np.uint8);cases.append(('multiple_mismatches',multi,rng.integers(0,2,C,dtype=np.uint8)))
cases.append(('all_zero',np.zeros(V,dtype=np.uint8),rng.integers(0,2,C,dtype=np.uint8)))
cases.append(('all_one',np.ones(V,dtype=np.uint8),rng.integers(0,2,C,dtype=np.uint8)))
oracle=json.load(open(ROOT/'fpga/verification/memory_backed_intermediate/oracle.json'))
trace_dec=np.array(oracle['records'][-1]['decision'],dtype=np.uint8);trace_syn=(H@trace_dec)%2
cases.append(('relay_trace_decision',trace_dec,trace_syn))
summ=[]
with (OUT/'convergence_cases.txt').open('w') as f:
 for cid,(name,dec,syn) in enumerate(cases):
  pred=(H@dec)%2;mismatch=(pred^syn);f.write(' '.join(map(str,[cid,*dec,*syn,*pred,int(mismatch.sum()),int(not mismatch.any())]))+'\n')
  summ.append({'case':cid,'name':name,'mismatches':int(mismatch.sum()),'converged':int(not mismatch.any())})
(OUT/'manifest.json').write_text(json.dumps({'checks':C,'variables':V,'incidences':int(H.sum()),'cases':summ,'predicted_syndrome_comparisons':len(cases)*C},indent=2)+'\n')

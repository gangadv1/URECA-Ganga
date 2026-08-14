from pathlib import Path
import numpy as np,json,hashlib
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;OUT.mkdir(exist_ok=True)
d=np.load(ROOT/'fpga/verification/memory_backed_intermediate/intermediate_input.npz');H=d['H'].astype(np.uint8)
rows=[];edge_var=[]
for row in H:
 edge_var.extend(np.flatnonzero(row).tolist());rows.append(len(edge_var))
cp=[0]+rows;E=len(edge_var);rng=np.random.default_rng(91827)
cases=[]
cases.append((np.arange(H.shape[0])%2,np.array([((-1)**e)*(3+(e%11)) for e in range(E)])))
cases.append((1-np.arange(H.shape[0])%2,rng.integers(-40,41,size=E)))
v=np.full(E,9);v[::3]=-9;v[1::7]=0;cases.append((rng.integers(0,2,size=H.shape[0]),v))
cases.append((rng.integers(0,2,size=H.shape[0]),rng.choice([-131072,-131071,-1,0,1,131070,131071],size=E)))
def update(nu,syn):
 mu=np.zeros(E,dtype=np.int64)
 for c in range(H.shape[0]):
  a,b=cp[c:c+2];x=nu[a:b];m=np.abs(x);first=int(np.argmin(m));second=int(np.min(np.delete(m,first))) if len(x)>1 else 131071;p=int(syn[c])^(int(np.sum(x<0))&1)
  for k in range(len(x)):
   mag=second if k==first else int(m[first]);neg=p^int(x[k]<0);mu[a+k]=max(-131072,min(131071,-mag if neg else mag))
 return mu
with (OUT/'check_cases.txt').open('w') as f:
 for cid,(syn,nu) in enumerate(cases):f.write(' '.join(map(str,[cid,*syn.tolist(),*nu.tolist(),*update(nu,syn).tolist()]))+'\n')
meta={'checks':int(H.shape[0]),'variables':int(H.shape[1]),'incidences':E,'cases':len(cases),'comparisons':len(cases)*E,'check_ptr':cp,'edge_var':edge_var,'coverage':['syndrome 0/1','alternating signs','zeros','equal/repeated minima','18-bit extrema','degrees 3..9','unaligned rows']}
(OUT/'manifest.json').write_text(json.dumps(meta,indent=2)+'\n')

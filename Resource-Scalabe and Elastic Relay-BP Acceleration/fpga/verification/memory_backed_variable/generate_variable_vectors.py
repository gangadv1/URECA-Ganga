from pathlib import Path
import json,numpy as np
from scipy import sparse
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;OUT.mkdir(exist_ok=True)
d=np.load(ROOT/'fpga/verification/memory_backed_intermediate/intermediate_input.npz');H=d['H'].astype(np.uint8);csr=sparse.csr_matrix(H);csc=csr.tocsc();E=csr.nnz;V=H.shape[1]
lookup={(int(csr.indices[e]),c):e for c in range(H.shape[0]) for e in range(csr.indptr[c],csr.indptr[c+1])}
ve=[]
for v in range(V):
 for p in range(csc.indptr[v],csc.indptr[v+1]):ve.append(lookup[(v,int(csc.indices[p]))])
vp=csc.indptr.tolist();rng=np.random.default_rng(71291);cases=[]
cases.append((np.zeros(V,dtype=int),np.zeros(V,dtype=int),np.array([2,-4,4,11]*5),np.zeros(E,dtype=int)))
cases.append((rng.integers(-30,31,V),rng.integers(-50,51,V),rng.integers(-4,12,V),rng.integers(-90,91,E)))
cases.append((np.full(V,131071),np.full(V,-131072),np.array([-4,11]*10),np.full(E,131071)))
cases.append((np.full(V,-131072),np.full(V,131071),np.array([11,-4]*10),np.full(E,-131072)))
def sat(x,lo=-131072,hi=131071):return max(lo,min(hi,int(x)))
def r16(x):return (-1 if x<0 else 1)*((abs(int(x))+8)//16)
records=[]
with (OUT/'variable_cases.txt').open('w') as f:
 for cid,(prior,prev,gamma,mu) in enumerate(cases):
  biases=[];sums=[];margs=[];decs=[];nus=np.zeros(E,dtype=int)
  for v in range(V):
   b=sat(r16(16*prior[v]+gamma[v]*(prev[v]-prior[v])));s=sum(int(mu[e]) for e in ve[vp[v]:vp[v+1]]);s=max(-(1<<21),min((1<<21)-1,s));m=sat(b+s);dec=int(m<=0)
   biases.append(b);sums.append(s);margs.append(m);decs.append(dec)
   for e in ve[vp[v]:vp[v+1]]:nus[e]=sat(m-int(mu[e]))
  weight=int(np.dot(prior,np.array(decs)));f.write(' '.join(map(str,[cid,*prior,*prev,*gamma,*mu,*biases,*sums,*margs,*decs,weight,*nus]))+'\n')
  records.append({'case':cid,'weight':weight,'zero_marginals':int(np.sum(np.array(margs)==0)),'saturated_marginals':int(np.sum(np.abs(margs)>=131071))})
(OUT/'manifest.json').write_text(json.dumps({'variables':V,'incidences':E,'cases':records,'var_ptr':vp,'var_edge':ve,'comparisons':{'bias':4*V,'sum':4*V,'marginal':4*V,'decision':4*V,'nu':4*E}},indent=2)+'\n')

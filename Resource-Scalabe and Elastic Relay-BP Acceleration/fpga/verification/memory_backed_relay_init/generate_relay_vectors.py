from pathlib import Path
import json,numpy as np
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;OUT.mkdir(exist_ok=True)
d=np.load(ROOT/'fpga/verification/memory_backed_intermediate/intermediate_input.npz');H=d['H'].astype(np.uint8);C,V=H.shape
ev=[v for w in json.load(open(ROOT/'fpga/verification/memory_backed_intermediate/images/edge_var.json')) for v in w][:int(H.sum())];E=len(ev);rng=np.random.default_rng(66109);cases=[]
for cid in range(5):
 prior=rng.integers(-120,121,V);marg=np.clip(-prior*(cid+2)+rng.integers(-7,8,V),-131072,131071)
 gamma=np.array([[-4,0,2,4,11][(v+cid)%5] for v in range(V)]);dirty_nu=rng.integers(-500,501,E);dirty_mu=rng.integers(-500,501,E)
 cases.append((prior,marg,gamma,dirty_nu,dirty_mu))
with (OUT/'relay_cases.txt').open('w') as f:
 for cid,(p,m,g,n,u) in enumerate(cases):f.write(' '.join(map(str,[cid,*p,*m,*g,*n,*u]))+'\n')
(OUT/'manifest.json').write_text(json.dumps({'checks':C,'variables':V,'incidences':E,'cases':5,'edge_var':ev,
 'expected_nu_rule':'nu[e]=prior[edge_var[e]]','mu_semantics':'not cleared; mu_valid=0 until CHECK_UPDATE overwrites all edges',
 'coverage':['failed-leg-style state','successful-leg-style state','mixed signed gamma','marginals differ from priors','prior bank conflicts','partial final P=4 chunk']},indent=2)+'\n')

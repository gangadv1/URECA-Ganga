from pathlib import Path
import sys,pickle,json,numpy as np,hashlib
sys.path.insert(0,'/tmp/gari-native-6380d52')
from scipy.sparse import issparse
out=Path('/Users/gangadevi.aa/Desktop/URECA-Ganga/Resource-Scalabe and Elastic Relay-BP Acceleration/results/gari-native-reproduction')
a=Path('/tmp/gari-nms-audit/data/circuits');b=Path('/tmp/gari-native-6380d52/data/circuits');r={}
for name in ['BB_n144_k12_d12_CL_both_matrices.pkl','BB_n144_k12_d12_CL_both_hcols_hrows.pkl']:
 with (a/name).open('rb') as f:x=pickle.load(f)
 with (b/name).open('rb') as f:y=pickle.load(f)
 fields=zip(['Hcols','Hrows'],x,y) if isinstance(x,tuple) else ((k,v,getattr(y,k)) for k,v in vars(x).items())
 r[name]={}
 for k,v,w in fields:
  same=(v!=w).nnz==0 if issparse(v) else bool(np.array_equal(v,w))
  r[name][k]=dict(equal=same,shape=list(v.shape) if hasattr(v,'shape') else None)
(out/'cross_environment_static_graph_comparison.json').write_text(json.dumps(r,indent=2))
print('All static graph fields equal:',all(v['equal'] for f in r.values() for v in f.values()))

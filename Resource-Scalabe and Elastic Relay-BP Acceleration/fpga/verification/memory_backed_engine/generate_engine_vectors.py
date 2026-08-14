from pathlib import Path
import json,numpy as np
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;OUT.mkdir(exist_ok=True)
d=np.load(ROOT/'fpga/verification/memory_backed_intermediate/intermediate_input.npz');oracle=json.load(open(ROOT/'fpga/verification/memory_backed_intermediate/oracle.json'))
imgs=ROOT/'fpga/verification/memory_backed_intermediate/images';flat=lambda n:[x for w in json.load(open(imgs/f'{n}.json')) for x in w]
cp=json.load(open(imgs/'check_ptr.json'));ev=flat('edge_var')[:76];vp=json.load(open(imgs/'var_ptr.json'));ve=flat('var_edge')[:76]
gamma=np.asarray(json.load(open(imgs/'gamma.json')),dtype=int).reshape(-1).tolist()[:40]
with (OUT/'graph.txt').open('w') as f:f.write(' '.join(map(str,[*cp,*ev,*vp,*ve,*gamma]))+'\n')
with (OUT/'shots.txt').open('w') as f:
 for s in range(3):
  final=oracle['finals'][s];records=[r for r in oracle['records'] if r['shot']==s]
  f.write(' '.join(map(str,[s,*d['priors'][s].tolist(),*d['syndromes'][s].tolist(),len(records),final['converged'],final['legs'],final['weight'],*final['correction']]))+'\n')
with (OUT/'iterations.txt').open('w') as f:
 for r in oracle['records']:
  f.write(' '.join(map(str,[r['shot'],r['leg'],r['iteration'],r['converged'],*r['mu'],*r['marginal'],*r['nu'],*r['decision']]))+'\n')
(OUT/'manifest.json').write_text(json.dumps({'shots':3,'iteration_records':len(oracle['records']),'checks':12,'variables':20,'incidences':76,'first_limit':2,'later_limit':3},indent=2)+'\n')

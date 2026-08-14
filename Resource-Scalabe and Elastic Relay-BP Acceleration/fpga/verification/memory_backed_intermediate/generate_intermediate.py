from pathlib import Path
import sys,json,numpy as np
from scipy import sparse
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'reference'))
from relay_bp_fixed import FixedRelayBPDecoder,FixedRelayConfig,FixedRelayLegConfig
from fixedpoint import FixedConfig
from generate_memory_image import convert
OUT=Path(__file__).resolve().parent
def main():
 rng=np.random.default_rng(47021);C,V=12,20
 # Deterministic irregular rows: degrees 3..9, including nonmultiples of four.
 H=np.zeros((C,V),dtype=np.uint8)
 degrees=[3,4,5,6,7,8,9,3,5,7,8,9]
 for c,d in enumerate(degrees): H[c,rng.choice(V,d,replace=False)]=1
 # Ensure every variable participates, without exceeding degree nine.
 for v in np.flatnonzero(H.sum(0)==0): H[int(rng.integers(C)),v]=1
 # Exercise the supported degree-nine variable boundary deterministically.
 v_peak=int(np.argmax(H.sum(0)))
 for c in np.flatnonzero(H[:,v_peak]==0)[:9-int(H[:,v_peak].sum())]: H[c,v_peak]=1
 gamma=[np.full(V,2,dtype=int),rng.integers(-4,12,size=V,dtype=int)]
 config=FixedRelayConfig(fixed=FixedConfig(b=18,g=4,M=16),leg_configs=(
   FixedRelayLegConfig(2,gamma=np.array(gamma[0])/16),FixedRelayLegConfig(3,gamma=np.array(gamma[1])/16)),S=1,R=2)
 shots=[];kinds=set()
 for _ in range(20000):
  prior=rng.choice([-11,-8,-5,5,8,11],size=V);syn=rng.integers(0,2,size=C,dtype=np.uint8)
  d=FixedRelayBPDecoder(H,config);r=d.decode(prior,syn)
  kind='first' if r.converged and r.relay_legs==1 else 'relay' if r.converged else 'fail'
  if kind not in kinds:
   shots.append((prior,syn));kinds.add(kind)
  if len(kinds)==3:break
 if len(kinds)<3: raise RuntimeError(kinds)
 pri=np.array([x[0] for x in shots]);syn=np.array([x[1] for x in shots])
 np.savez(OUT/'intermediate_input.npz',H=H,priors=pri,syndromes=syn,gamma=np.array(gamma))
 images,meta=convert(H,pri,syn,OUT/'images',gamma)
 # Full oracle records, using exact locked rules but exposing arrays.
 from importlib.util import spec_from_file_location,module_from_spec
 spec=spec_from_file_location('small',ROOT/'fpga/verification/small_graph_b18/generate_small_graph_vectors.py');m=module_from_spec(spec);spec.loader.exec_module(m)
 # local generic trace implementation
 cp=images['check_ptr'];ev=[x for w in images['edge_var'] for x in w][:meta['incidences']]
 vp=images['var_ptr'];ve=[x for w in images['var_edge'] for x in w][:meta['incidences']]
 records=[]; finals=[]
 for si,(prior,syndrome) in enumerate(shots):
  hand=prior.copy();trace=[];conv=False;dec=np.zeros(V,dtype=np.uint8)
  for leg,limit in enumerate([2,3]):
   nu=prior[np.array(ev)].copy();prev=hand.copy()
   for it in range(1,limit+1):
    bias=np.array([m.sat(m.r16(16*prior[j]+gamma[leg][j]*(prev[j]-prior[j]))) for j in range(V)])
    mu=np.zeros(meta['incidences'],dtype=np.int64)
    for c in range(C):
     a,b=cp[c:c+2];vals=nu[a:b];mags=np.abs(vals);first=int(np.argmin(mags));second=int(np.min(np.delete(mags,first))) if b-a>1 else 131071
     parity=int(syndrome[c])^(int(np.sum(vals<0))&1)
     for q in range(b-a):mu[a+q]=(-1 if parity^int(vals[q]<0) else 1)*(second if q==first else int(mags[first]))
    incoming=np.zeros(V,dtype=np.int64)
    for v in range(V): incoming[v]=sum(mu[e] for e in ve[vp[v]:vp[v+1]])
    incoming=np.clip(incoming,m.GLO,m.GHI);marg=np.array([m.sat(bias[v]+incoming[v]) for v in range(V)]);dec=(marg<=0).astype(np.uint8)
    newnu=np.array([m.sat(marg[v]-mu[e]) for e,v in enumerate(ev)]);res=(H@dec)%2^syndrome
    trace.append({'shot':si,'leg':leg+1,'iteration':it,'mu':mu.tolist(),'nu':newnu.tolist(),'marginal':marg.tolist(),'decision':dec.tolist(),'converged':int(not res.any())})
    nu=newnu;prev=marg;hand=marg.copy()
    if not res.any():conv=True;break
   if conv:break
  records+=trace;finals.append({'shot':si,'converged':int(conv),'iterations':len(trace),'legs':trace[-1]['leg'],'correction':dec.tolist(),'weight':int(dec@prior)})
 (OUT/'oracle.json').write_text(json.dumps({'records':records,'finals':finals},indent=2)+'\n')
 (OUT/'fixture_summary.json').write_text(json.dumps({'dimensions':meta,'check_degrees':degrees,'variable_degrees':H.sum(0).tolist(),'case_types':sorted(kinds)},indent=2)+'\n')
 print(meta['checks'],meta['variables'],meta['incidences'],[(x['converged'],x['iterations'],x['legs']) for x in finals])
if __name__=='__main__':main()

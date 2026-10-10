#!/usr/bin/env python3
"""Paired hardware-cycle screening study for the frozen N=1/N=2 design."""
from __future__ import annotations
import csv,hashlib,json,math,os,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from scipy import sparse
from scipy.stats import norm
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'reference'),str(ROOT/'fpga/verification/parallel_n2')]
from fixedpoint import FixedConfig
from relay_bp_fixed import FixedRelayBPDecoder,FixedRelayConfig,FixedRelayLegConfig
from gamma_rng_reference import vector
OUT=Path(__file__).resolve().parent;PKG=ROOT/'graphs/generated/gross_circuit_level/memory_Z_r12_p0p003';SAMPLES=ROOT/'results/circuit-level-multiseed/paired_samples.npz'
C,V,E,P=1728,67752,391320,4;R,S,FIRST_LIMIT,LATER_LIMIT=32,1,80,60
CHECK,VARIABLE,CONVERGENCE,RELAY=508753,2489173,790855,969916
ITER_PHASE=CHECK+VARIABLE+CONVERGENCE;BASE_SEED=0x6A09E667F3BCC909
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def splitmix(x):
 x=(x+0x9e3779b97f4a7c15)&((1<<64)-1);z=x;z=(z^(z>>30))*0xbf58476d1ce4e5b9&((1<<64)-1);z=(z^(z>>27))*0x94d049bb133111eb&((1<<64)-1);return (z^(z>>31))&((1<<64)-1)
def seeds(sample_seed,shot,n=8):
 if n<1:raise ValueError("n must be >= 1")
 s0=splitmix(BASE_SEED^sample_seed^(shot*0x100000001b3))
 out=[s0]
 for _ in range(1,n):
  out.append(splitmix(out[-1]^0xd1b54a32d192ed03))
 return tuple(out)
def load_problem():
 with np.load(PKG/'edge_lists.npz') as d:de,oe=d['detector_edges'],d['observable_edges']
 with np.load(PKG/'faults.npz') as d:p=d['probabilities']
 h=sparse.csr_matrix((np.ones(len(de),np.uint8),(de[:,1],de[:,0])),shape=(C,V));a=sparse.csr_matrix((np.ones(len(oe),np.uint8),(oe[:,1],oe[:,0])),shape=(12,V));return h,a,np.log((1-p)/p)
def gamma_legs(seed):
 state=seed;configs=[FixedRelayLegConfig(FIRST_LIMIT,gamma=.125)];words=[0];states=[state]
 for _ in range(1,R):
  vals,_,state,rej=vector(state,V);configs.append(FixedRelayLegConfig(LATER_LIMIT,gamma=np.asarray(vals,dtype=np.float64)/16));words.append(V+rej);states.append(state)
 return tuple(configs),words,states
def hw_cycles(iterations,legs,converged,words):
 # Exact controller formula calibrated against complete intermediate RTL and the exhaustive Tier-2 one-iteration RTL.
 total=iterations*ITER_PHASE+legs*RELAY+V+9+8*(iterations-legs)
 total+=sum(words[1:legs])+9*max(0,legs-1)
 if converged and legs>1:total+=2
 return int(total),int(total-1 if converged else total)
def decode_one(h,a,priors,syndrome,logical,seed):
 legs,words,states=gamma_legs(seed);d=FixedRelayBPDecoder(h,FixedRelayConfig(fixed=FixedConfig(b=18,g=4,M=16,clip=None,separate_scale=True),leg_configs=legs,S=S,R=R,seed=0));r=d.decode(priors,syndrome);dec=r.decoded_error.astype(np.uint8)
 syn=bool(np.array_equal(np.asarray(h@dec).reshape(-1)&1,syndrome));log=bool(np.array_equal(np.asarray(a@dec).reshape(-1)&1,logical));conv=bool(syn)
 natural,result=hw_cycles(r.total_iterations,r.relay_legs,conv,words);used_words=sum(words[1:r.relay_legs]);return {'syndrome_converged':int(syn),'logical_correct':int(syn and log),'syndrome_valid_logical_error':int(syn and not log),'non_convergence':int(not syn),'iterations':int(r.total_iterations),'legs':int(r.relay_legs),'weight':r.metadata.get('best_weight'),'natural_cycles':natural,'result_cycles':result,'rng_words':int(used_words),'gamma_coefficients':int(max(0,r.relay_legs-1)*V),'initial_rng_state':int(seed),'final_rng_state':int(states[r.relay_legs-1]),'decision':dec}
def task(args):
 seed_index,shot,sample_seed,syndrome,logical=args
 h,a,priors=load_problem()
 ns=(1,2,4,8,16)
 trajectory_seeds=seeds(sample_seed,shot,max(ns))
 engines=[decode_one(h,a,priors,syndrome,logical,x) for x in trajectory_seeds]

 row={
  'p':.003,
  'sample_seed':sample_seed,
  'seed_index':seed_index,
  'shot':shot,
  'detector_sample_hash':hashlib.sha256(np.packbits(syndrome).tobytes()).hexdigest(),
  'logical_sample_hash':hashlib.sha256(np.packbits(logical).tobytes()).hexdigest(),
 }

 for i,(seed,e) in enumerate(zip(trajectory_seeds,engines)):
  row[f's{i}']=seed
  for k,v in e.items():
   if k!='decision':
    row[f'e{i}_{k}']=v

 for n in ns:
  active=engines[:n]
  successes=[
   (e['result_cycles'],i)
   for i,e in enumerate(active)
   if e['syndrome_converged']
  ]

  if successes:
   cycles,winner=min(successes)
   selected=active[winner]
  else:
   cycles=max(e['result_cycles'] for e in active)
   winner=-1
   selected=None

  row[f'n{n}_cycles']=int(cycles)
  row[f'n{n}_winner']=int(winner)
  row[f'n{n}_syndrome_converged']=int(selected is not None)
  row[f'n{n}_logical_correct']=0 if selected is None else selected['logical_correct']
  row[f'n{n}_syndrome_valid_logical_error']=0 if selected is None else selected['syndrome_valid_logical_error']
  row[f'n{n}_non_convergence']=int(selected is None)
  row[f'n{n}_active_work']=int(sum(e['natural_cycles'] for e in active))

 return row

def pct(x,q):return float(np.percentile(np.asarray(x,dtype=float),q))
def desc(x):
 a=np.asarray(x,dtype=float);return {'mean':float(a.mean()),'p50':pct(a,50),'p90':pct(a,90),'p95':pct(a,95),'p99':pct(a,99),'max':float(a.max()),'std':float(a.std(ddof=1)) if len(a)>1 else 0.}
def wilson(k,n):
 z=norm.ppf(.975);p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d;return [c-h,c+h]
def bootstrap(rows,n_value,samples=2000):
 rng=np.random.default_rng(20260814+n_value)
 a=np.array([r['n1_cycles'] for r in rows])
 b=np.array([r[f'n{n_value}_cycles'] for r in rows])
 vals=[]
 for _ in range(samples):
  ix=rng.integers(0,len(rows),len(rows))
  vals.append([
   np.mean(a[ix]-b[ix]),
   np.percentile(a[ix],90)-np.percentile(b[ix],90),
   np.percentile(a[ix],99)-np.percentile(b[ix],99)
  ])
 z=np.asarray(vals)
 return {
  k:[float(x) for x in np.percentile(z[:,i],[2.5,97.5])]
  for i,k in enumerate(('mean_reduction','p90_difference','p99_difference'))
 }

def main():
 shots=int(os.environ.get('SHOTS','32'))
 seed_count=int(os.environ.get('SEED_COUNT','1'))
 ns=(1,2,4,8,16)
 OUT.mkdir(parents=True,exist_ok=True)

 with np.load(SAMPLES) as d:
  ss=d['syndromes'][:seed_count,:shots]
  ll=d['observed_logicals'][:seed_count,:shots]
  sample_seeds=d['sample_seeds'][:seed_count]

 jobs=[
  (i,j,int(sample_seeds[i]),ss[i,j],ll[i,j])
  for i in range(seed_count)
  for j in range(shots)
 ]

 rows=[]
 t=time.time()

 with ThreadPoolExecutor(max_workers=min(4,len(jobs))) as ex:
  fs={ex.submit(task,j):j for j in jobs}
  for k,f in enumerate(as_completed(fs),1):
   rows.append(f.result())
   print(f'completed {k}/{len(jobs)} elapsed={time.time()-t:.1f}s',flush=True)

 rows.sort(key=lambda r:(r['seed_index'],r['shot']))

 fields=list(rows[0])
 with (OUT/'per_shot_results.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields)
  w.writeheader()
  w.writerows(rows)

 nshots=len(rows)
 latency={}
 logical={}
 winners={}
 active_work={}

 for n in ns:
  key=f'n{n}'
  latency[key]=desc([r[f'{key}_cycles'] for r in rows])

  succ=sum(r[f'{key}_logical_correct'] for r in rows)
  conv=sum(r[f'{key}_syndrome_converged'] for r in rows)

  logical[key]={
   'shots':nshots,
   'syndrome_convergence_rate':conv/nshots,
   'logical_success_rate':succ/nshots,
   'logical_success_wilson95':wilson(succ,nshots),
   'syndrome_valid_logical_errors':sum(r[f'{key}_syndrome_valid_logical_error'] for r in rows),
   'non_convergence':sum(r[f'{key}_non_convergence'] for r in rows),
  }

  winners[key]={
   f'engine{i}':sum(r[f'{key}_winner']==i for r in rows)
   for i in range(n)
  }
  winners[key]['all_fail']=sum(r[f'{key}_winner']<0 for r in rows)

  active_work[key]=desc([r[f'{key}_active_work'] for r in rows])

 baseline=latency['n1']
 reductions={}

 for n in ns[1:]:
  current=latency[f'n{n}']
  reductions[f'n1_to_n{n}']={
   q:(baseline[q]-current[q])/baseline[q]
   for q in ('mean','p50','p90','p95','p99','max')
  }
  reductions[f'n1_to_n{n}']['bootstrap95']=bootstrap(rows,n)

 marginal={}
 for prev,current_n in zip(ns[:-1],ns[1:]):
  a=latency[f'n{prev}']
  b=latency[f'n{current_n}']
  marginal[f'n{prev}_to_n{current_n}']={
   q:(a[q]-b[q])/a[q]
   for q in ('mean','p50','p90','p95','p99','max')
  }

 aggregate={
  'shots':nshots,
  'trajectory_counts':list(ns),
  'latency':latency,
  'logical':logical,
  'winners':winners,
  'active_work':active_work,
  'reductions_vs_n1':reductions,
  'marginal_reductions':marginal,
 }

 (OUT/'aggregate_summary.json').write_text(
  json.dumps(aggregate,indent=2)+'\n'
 )
 (OUT/'logical_performance.json').write_text(
  json.dumps(logical,indent=2)+'\n'
 )

 order=sorted(rows,key=lambda r:r['n1_cycles'],reverse=True)
 tail={
  'top10_percent':order[:max(1,math.ceil(.1*nshots))],
  'top5_percent':order[:max(1,math.ceil(.05*nshots))],
  'top1_percent':order[:max(1,math.ceil(.01*nshots))] if nshots>=100 else [],
  'p99_warning':'unstable below several hundred shots' if nshots<300 else None,
 }
 (OUT/'tail_analysis.json').write_text(json.dumps(tail,indent=2)+'\n')

 per=[]
 for seed in sample_seeds:
  g=[r for r in rows if r['sample_seed']==seed]
  entry={'sample_seed':int(seed),'shots':len(g)}
  for n in ns:
   entry[f'n{n}_latency']=desc([r[f'n{n}_cycles'] for r in g])
  per.append(entry)

 (OUT/'per_seed_summary.json').write_text(json.dumps(per,indent=2)+'\n')

 manifest={
  'stage':'canonical_n_scaling',
  'p':.003,
  'shots':nshots,
  'trajectory_counts':list(ns),
  'sample_seeds':[int(x) for x in sample_seeds],
  'configuration':{
   'first_gamma_encoded':2,
   'later_interval':[-.24,.66],
   'distribution_counts_per_720':{'-4':17,'-3_through_10':50,'11':3},
   'S':1,'R':32,'first_limit':80,'later_limit':60,
   'b':18,'accumulator_bits':22,'M':16,'P':4,
  },
  'cycle_model':{
   'calibration':'exhaustive Tier-2 RTL one iteration and complete intermediate multi-leg RTL',
   'check':CHECK,
   'variable':VARIABLE,
   'convergence':CONVERGENCE,
   'relay_init':RELAY,
   'metric':'architectural cycles; first syndrome-valid trajectory wins',
  },
  'rng':{
   'algorithm':'xorshift64(13,7,17)',
   'base_seed':BASE_SEED,
   'trajectory_seed_derivation':'s0 preserves canonical seed; s[i]=splitmix(s[i-1] XOR 0xd1b54a32d192ed03)',
   'regression':'N1 trajectory0 and N2 trajectories0-1 preserve historical canonical seeds',
  },
  'hashes':{
   'package_manifest':sha(PKG/'manifest.json'),
   'samples':sha(SAMPLES),
   'fixed_decoder':sha(ROOT/'reference/relay_bp_fixed.py'),
   'rng_reference':sha(ROOT/'fpga/verification/parallel_n2/gamma_rng_reference.py'),
   'rng_rtl':sha(ROOT/'fpga/rtl/relay_bp_gamma_rng.sv'),
  },
  'git_commit':subprocess.check_output(
   ['git','rev-parse','HEAD'],cwd=ROOT.parent,text=True
  ).strip(),
 }

 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

 print(json.dumps(aggregate,indent=2))

if __name__=='__main__':main()

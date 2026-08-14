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
def seeds(sample_seed,shot):
 s0=splitmix(BASE_SEED^sample_seed^(shot*0x100000001b3));return s0,splitmix(s0^0xd1b54a32d192ed03)
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
 seed_index,shot,sample_seed,syndrome,logical=args;h,a,priors=load_problem();s0,s1=seeds(sample_seed,shot);e0=decode_one(h,a,priors,syndrome,logical,s0);e1=decode_one(h,a,priors,syndrome,logical,s1)
 successes=[(e['result_cycles'],i) for i,e in enumerate((e0,e1)) if e['syndrome_converged']];winner=min(successes)[1] if successes else -1;n2cycles=min(x[0] for x in successes) if successes else max(e0['result_cycles'],e1['result_cycles']);selected=(e0,e1)[winner] if winner>=0 else None
 # Phase-safe cleanup model: loser drains at most its natural completion; exact RTL cancellation remains separately regression-calibrated.
 if winner>=0:
  loser=(e1,e0)[winner]
  if loser['natural_cycles']<=n2cycles:
   loser_q=n2cycles;cleanup=avoided=0
  else:
   request=n2cycles+1;loser_q=min(loser['natural_cycles'],request+max(CHECK,VARIABLE,CONVERGENCE,RELAY));cleanup=max(0,loser_q-n2cycles);avoided=max(0,loser['natural_cycles']-loser_q)
 else:loser_q=max(e0['natural_cycles'],e1['natural_cycles']);cleanup=avoided=0
 row={'p':.003,'sample_seed':sample_seed,'seed_index':seed_index,'shot':shot,'detector_sample_hash':hashlib.sha256(np.packbits(syndrome).tobytes()).hexdigest(),'logical_sample_hash':hashlib.sha256(np.packbits(logical).tobytes()).hexdigest(),'s0':s0,'s1':s1}
 for i,e in enumerate((e0,e1)):
  for k,v in e.items():
   if k!='decision':row[f'e{i}_{k}']=v
 row.update({'n1_cycles':e0['result_cycles'],'n2_cycles':n2cycles,'winner':winner,'same_cycle':int(winner==0 and e0['syndrome_converged'] and e1['syndrome_converged'] and e0['result_cycles']==e1['result_cycles']),'global_failure':int(winner<0),'n2_syndrome_converged':int(selected is not None),'n2_logical_correct':0 if selected is None else selected['logical_correct'],'n2_syndrome_valid_logical_error':0 if selected is None else selected['syndrome_valid_logical_error'],'n2_non_convergence':int(selected is None),'parallel_rescue':int(not e0['syndrome_converged'] and winner==1),'early_wrong_risk':int(winner==1 and selected['syndrome_valid_logical_error'] and e0['logical_correct']),'latency_reduction':e0['result_cycles']-n2cycles,'relative_reduction':(e0['result_cycles']-n2cycles)/e0['result_cycles'],'loser_quiescent_cycle':loser_q,'cleanup_cycles':cleanup,'avoided_loser_cycles':avoided,'pair_reuse_cycle':max(n2cycles,loser_q),'n1_active_work':e0['natural_cycles'],'n2_active_work':e0['natural_cycles']+e1['natural_cycles'] if winner<0 else n2cycles+loser_q})
 return row
def pct(x,q):return float(np.percentile(np.asarray(x,dtype=float),q))
def desc(x):
 a=np.asarray(x,dtype=float);return {'mean':float(a.mean()),'p50':pct(a,50),'p90':pct(a,90),'p95':pct(a,95),'p99':pct(a,99),'max':float(a.max()),'std':float(a.std(ddof=1)) if len(a)>1 else 0.}
def wilson(k,n):
 z=norm.ppf(.975);p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d;return [c-h,c+h]
def bootstrap(rows,n=2000):
 rng=np.random.default_rng(20260814);a=np.array([r['n1_cycles'] for r in rows]);b=np.array([r['n2_cycles'] for r in rows]);vals=[]
 for _ in range(n):
  ix=rng.integers(0,len(rows),len(rows));vals.append([np.mean(a[ix]-b[ix]),np.percentile(a[ix],90)-np.percentile(b[ix],90),np.percentile(a[ix],99)-np.percentile(b[ix],99)])
 z=np.asarray(vals);return {k:[float(x) for x in np.percentile(z[:,i],[2.5,97.5])] for i,k in enumerate(('mean_reduction','p90_difference','p99_difference'))}
def main():
 shots=int(os.environ.get('SHOTS','32'));seed_count=int(os.environ.get('SEED_COUNT','1'));OUT.mkdir(parents=True,exist_ok=True)
 with np.load(SAMPLES) as d:ss=d['syndromes'][:seed_count,:shots];ll=d['observed_logicals'][:seed_count,:shots];sample_seeds=d['sample_seeds'][:seed_count]
 jobs=[(i,j,int(sample_seeds[i]),ss[i,j],ll[i,j]) for i in range(seed_count) for j in range(shots)];rows=[];t=time.time()
 with ThreadPoolExecutor(max_workers=min(4,len(jobs))) as ex:
  fs={ex.submit(task,j):j for j in jobs}
  for k,f in enumerate(as_completed(fs),1):rows.append(f.result());print(f'completed {k}/{len(jobs)} elapsed={time.time()-t:.1f}s',flush=True)
 rows.sort(key=lambda r:(r['seed_index'],r['shot']));fields=list(rows[0]);
 with (OUT/'per_shot_results.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 n=len(rows);n1=desc([r['n1_cycles'] for r in rows]);n2=desc([r['n2_cycles'] for r in rows]);reduction=desc([r['latency_reduction'] for r in rows]);logical={}
 for name,prefix in [('n1','e0_'),('n2','n2_')]:
  succ=sum(r[prefix+'logical_correct'] for r in rows);conv=sum(r[prefix+'syndrome_converged'] for r in rows);logical[name]={'shots':n,'syndrome_convergence_rate':conv/n,'logical_success_rate':succ/n,'logical_success_wilson95':wilson(succ,n),'syndrome_valid_logical_errors':sum(r[prefix+'syndrome_valid_logical_error'] for r in rows),'non_convergence':sum(r[prefix+'non_convergence'] for r in rows)}
 winners={'engine0':sum(r['winner']==0 for r in rows),'engine1':sum(r['winner']==1 for r in rows),'same_cycle':sum(r['same_cycle'] for r in rows),'both_fail':sum(r['winner']<0 for r in rows)}
 aggregate={'shots':n,'n1_latency':n1,'n2_latency':n2,'paired_reduction':reduction,'percent_reductions':{q:(n1[q]-n2[q])/n1[q] for q in ('mean','p90','p99','max')},'bootstrap95':bootstrap(rows),'logical':logical,'winners':winners,'parallel_rescues':sum(r['parallel_rescue'] for r in rows),'early_wrong_risk':sum(r['early_wrong_risk'] for r in rows),'cancellation':{'cleanup':desc([r['cleanup_cycles'] for r in rows if r['winner']>=0]),'mean_avoided_loser_cycles':float(np.mean([r['avoided_loser_cycles'] for r in rows if r['winner']>=0])) if any(r['winner']>=0 for r in rows) else 0,'total_avoided_loser_cycles':sum(r['avoided_loser_cycles'] for r in rows),'n1_active_work_total':sum(r['n1_active_work'] for r in rows),'n2_active_work_total':sum(r['n2_active_work'] for r in rows),'pair_reuse':desc([r['pair_reuse_cycle'] for r in rows])}}
 (OUT/'aggregate_summary.json').write_text(json.dumps(aggregate,indent=2)+'\n');(OUT/'logical_performance.json').write_text(json.dumps(logical,indent=2)+'\n');(OUT/'cancellation_work.json').write_text(json.dumps(aggregate['cancellation'],indent=2)+'\n')
 order=sorted(rows,key=lambda r:r['n1_cycles'],reverse=True);tail={'top10_percent':order[:max(1,math.ceil(.1*n))],'top5_percent':order[:max(1,math.ceil(.05*n))],'top1_percent':order[:max(1,math.ceil(.01*n))] if n>=100 else [],'p99_warning':'unstable below several hundred shots' if n<300 else None};(OUT/'tail_analysis.json').write_text(json.dumps(tail,indent=2)+'\n')
 per=[]
 for seed in sample_seeds:
  g=[r for r in rows if r['sample_seed']==seed];per.append({'sample_seed':int(seed),'shots':len(g),'n1_latency':desc([r['n1_cycles'] for r in g]),'n2_latency':desc([r['n2_cycles'] for r in g])})
 (OUT/'per_seed_summary.json').write_text(json.dumps(per,indent=2)+'\n')
 manifest={'stage':'screening','p':.003,'shots':n,'sample_seeds':[int(x) for x in sample_seeds],'configuration':{'first_gamma_encoded':2,'later_interval':[-.24,.66],'distribution_counts_per_720':{'-4':17,'-3_through_10':50,'11':3},'S':1,'R':32,'first_limit':80,'later_limit':60,'b':18,'accumulator_bits':22,'M':16,'P':4},'cycle_model':{'calibration':'exhaustive Tier-2 RTL one iteration and complete intermediate multi-leg RTL','check':CHECK,'variable':VARIABLE,'convergence':CONVERGENCE,'relay_init':RELAY,'metric':'architectural cycles, candidate-valid for success and failure completion for non-convergence'},'rng':{'algorithm':'xorshift64(13,7,17)','base_seed':BASE_SEED,'pairing':'N1 S0 equals N2 engine0 S0; N2 engine1 uses independent S1'},'hashes':{'package_manifest':sha(PKG/'manifest.json'),'samples':sha(SAMPLES),'fixed_decoder':sha(ROOT/'reference/relay_bp_fixed.py'),'rng_reference':sha(ROOT/'fpga/verification/parallel_n2/gamma_rng_reference.py'),'n2_rtl':sha(ROOT/'fpga/rtl/relay_bp_parallel_n2_p4.sv'),'rng_rtl':sha(ROOT/'fpga/rtl/relay_bp_gamma_rng.sv')},'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT.parent,text=True).strip()}
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(aggregate,indent=2))
if __name__=='__main__':main()

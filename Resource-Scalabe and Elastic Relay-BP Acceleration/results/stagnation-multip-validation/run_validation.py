#!/usr/bin/env python3
"""Pre-registered multi-p validation of the fixed-point stagnation signal."""
from __future__ import annotations
import csv,hashlib,json,math,sys,time
from collections import Counter,defaultdict
from pathlib import Path
from typing import Any
import numpy as np
from scipy import sparse
import stim

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
sys.path[:0]=[str(ROOT/'reference'),str(ROOT/'fpga/verification/parallel_n2')]
from fixedpoint import FixedConfig
from gamma_rng_reference import vector as hardware_gamma_vector
from relay_bp_fixed import FixedRelayBPDecoder,FixedRelayConfig,FixedRelayLegConfig

V,C=67752,1728;FIRST,LATER,R=80,60,32;BASE=0x6A09E667F3BCC909
REGIMES=((.002,'0p002',20260902,64),(.004,'0p004',20260904,64))
P003=ROOT/'results/full-dataset-stagnation-analysis'

def sha_bytes(x):return hashlib.sha256(x).hexdigest()
def packed_hash(x):return sha_bytes(np.packbits(np.asarray(x,np.uint8)).tobytes())
def splitmix(x):
 x=(x+0x9e3779b97f4a7c15)&((1<<64)-1);z=x;z=(z^(z>>30))*0xbf58476d1ce4e5b9&((1<<64)-1);z=(z^(z>>27))*0x94d049bb133111eb&((1<<64)-1);return (z^(z>>31))&((1<<64)-1)
def decoder_seed(sample_seed,shot):return splitmix(BASE^sample_seed^(shot*0x100000001b3))
def write_csv(path,rows):
 with path.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def load_problem(tag):
 pkg=ROOT/f'graphs/generated/gross_circuit_level/memory_Z_r12_p{tag}'
 with np.load(pkg/'edge_lists.npz') as d:de,oe=d['detector_edges'],d['observable_edges']
 with np.load(pkg/'faults.npz') as d:p=d['probabilities']
 h=sparse.csr_matrix((np.ones(len(de),np.uint8),(de[:,1],de[:,0])),shape=(C,V));a=sparse.csr_matrix((np.ones(len(oe),np.uint8),(oe[:,1],oe[:,0])),shape=(12,V))
 return pkg,h,a,np.log((1-p)/p)
def gamma_schedule(seed):
 state=seed;cfg=[FixedRelayLegConfig(FIRST,gamma=.125)];meta=[{'state':state,'words':0,'accepted':0}]
 for _ in range(1,R):
  values,words,state,rejected=hardware_gamma_vector(state,V);cfg.append(FixedRelayLegConfig(LATER,gamma=np.asarray(values,float)/16));meta.append({'state':state,'words':len(words)+rejected,'accepted':V})
 return tuple(cfg),meta
class Collector:
 def __init__(self,p,sample_seed,shot,prior,h,syndrome):
  self.p,self.sample_seed,self.shot=p,sample_seed,shot;d=(np.rint(prior)<=0).astype(np.uint8);pred=np.asarray(h@d).reshape(-1).astype(np.uint8)&1
  self.prev=d;self.initial=int(np.count_nonzero(pred^syndrome));self.best=self.initial;self.since=0;self.sat=Counter();self.rows=[]
 def __call__(self,e):
  decision=np.asarray(e['decoded_error'],np.uint8);weight=int(np.asarray(e['residual'],np.uint8).sum());new=weight<self.best
  if new:self.best,self.since=weight,0
  else:self.since+=1
  churn=int(np.count_nonzero(decision^self.prev));sat=Counter({k:int(v) for k,v in dict(e['saturation_counts']).items()});delta=sat-self.sat
  self.rows.append({'p':self.p,'sample_seed':self.sample_seed,'shot':self.shot,'global_iteration':int(e['global_iteration']),'relay_leg':int(e['leg_index'])+1,'iteration_in_leg':int(e['iteration']),'residual_weight':weight,'best_residual':self.best,'iterations_since_best':self.since,'residual_minus_best':weight-self.best,'decision_churn':churn,'new_best':int(new),'converged':int(bool(e['converged'])),'saturation_hits':sum(delta.values())})
  self.prev=decision.copy();self.sat=sat
def summarize_legs(rows,initial):
 by=defaultdict(list)
 for r in rows:by[r['relay_leg']].append(r)
 out=[];start=best=initial
 for leg,rr in sorted(by.items()):
  minimum=min(x['residual_weight'] for x in rr);end=rr[-1]['residual_weight'];improvement=max(0,best-minimum);cat='productive' if rr[-1]['converged'] or improvement>0 else ('regressive' if end>start else 'stagnant')
  out.append({'p':rr[0]['p'],'sample_seed':rr[0]['sample_seed'],'shot':rr[0]['shot'],'relay_leg':leg,'iterations_used':len(rr),'start_residual':start,'end_residual':end,'minimum_residual':minimum,'global_best_before':best,'global_best_after':min(best,minimum),'global_best_improvement':improvement,'iterations_since_best_at_end':rr[-1]['iterations_since_best'],'residual_minus_best':end-min(best,minimum),'mean_decision_churn':float(np.mean([x['decision_churn'] for x in rr])),'max_decision_churn':max(x['decision_churn'] for x in rr),'category':cat,'converged':rr[-1]['converged'],'end_global_iteration':rr[-1]['global_iteration']})
  start=end;best=min(best,minimum)
 return out
def attach_targets(iterations,legs):
 bi=defaultdict(list);bl=defaultdict(list)
 for r in iterations:bi[(r['p'],r['sample_seed'],r['shot'])].append(r)
 for r in legs:bl[(r['p'],r['sample_seed'],r['shot'])].append(r)
 for key,rr in bi.items():
  ll=bl[key];new_at=[x['global_iteration'] for x in rr if x['new_best']]
  for r in rr:
   for n in (1,2,3):
    future=[x for x in ll if r['relay_leg']<x['relay_leg']<=r['relay_leg']+n];hit=any(x['global_best_improvement']>0 for x in future);enough=len(future)>=n
    r[f'target{n}_eligible']=int(hit or enough);r[f'target{n}']=int(not hit) if hit or enough else ''
   horizon=r['global_iteration']+120;hit=any(r['global_iteration']<x<=horizon for x in new_at);enough=rr[-1]['global_iteration']>=horizon
   r['target4_eligible']=int(hit or enough);r['target4']=int(not hit) if hit or enough else ''
 idx={(x['p'],x['sample_seed'],x['shot'],x['global_iteration']):x for x in iterations}
 for l in legs:
  r=idx[(l['p'],l['sample_seed'],l['shot'],l['end_global_iteration'])]
  for n in range(1,5):l[f'target{n}_eligible']=r[f'target{n}_eligible'];l[f'target{n}']=r[f'target{n}']
def metrics(rows,target,threshold=120):
 risk=[r for r in rows if int(r[f'target{target}_eligible']) and not int(r['converged'])];y=[int(r[f'target{target}']) for r in risk];pred=[int(r['iterations_since_best_at_end'])>=threshold for r in risk]
 tp=sum(a and b for a,b in zip(y,pred));tn=sum(not a and not b for a,b in zip(y,pred));fp=sum(not a and b for a,b in zip(y,pred));fn=sum(a and not b for a,b in zip(y,pred));d=lambda a,b:None if not b else a/b;tpr=d(tp,tp+fn);tnr=d(tn,tn+fp)
 return {'eligible_boundaries':len(y),'positives':sum(y),'base_rate':d(sum(y),len(y)),'predicted_positive':sum(pred),'precision':d(tp,tp+fp),'recall':tpr,'specificity':tnr,'false_positive_rate':d(fp,fp+tn),'false_negative_rate':d(fn,fn+tp),'balanced_accuracy':None if tpr is None or tnr is None else (tpr+tnr)/2,'tp':tp,'fp':fp,'tn':tn,'fn':fn}
def generate_samples(pkg,seed,shots):
 circuit=stim.Circuit.from_file(pkg/'circuit.stim');sampler=circuit.compile_detector_sampler(seed=seed);det,obs=sampler.sample(shots=shots,separate_observables=True)
 return det.astype(np.uint8),obs.astype(np.uint8)
def main():
 OUT.mkdir(parents=True,exist_ok=True);all_shots=[];all_legs=[];all_iterations=[];sample_data={};runtime={};package_audit=[]
 for p,tag,sample_seed,target_shots in REGIMES:
  pkg,h,action,prior=load_problem(tag);det,obs=generate_samples(pkg,sample_seed,target_shots);sample_data[f'p{tag}_syndromes']=det;sample_data[f'p{tag}_logicals']=obs
  started=time.perf_counter();times=[];completed=target_shots
  for shot in range(target_shots):
   t=time.perf_counter();seed=decoder_seed(sample_seed,shot);cfg,meta=gamma_schedule(seed);collector=Collector(p,sample_seed,shot,prior,h,det[shot])
   decoder=FixedRelayBPDecoder(h,FixedRelayConfig(fixed=FixedConfig(b=18,g=4,M=16,clip=None,separate_scale=True),leg_configs=cfg,S=1,R=R,seed=0),iteration_callback=collector);result=decoder.decode(prior,det[shot]);elapsed=time.perf_counter()-t;times.append(elapsed)
   decision=result.decoded_error.astype(np.uint8);pred=np.asarray(action@decision).reshape(-1).astype(np.uint8)&1;logical_correct=bool(result.converged and np.array_equal(pred,obs[shot]));used=int(result.relay_legs);legs=summarize_legs(collector.rows,collector.initial)
   row={'p':p,'sample_seed':sample_seed,'shot':shot,'syndrome_hash':packed_hash(det[shot]),'logical_hash':packed_hash(obs[shot]),'decoder_seed':seed,'converged':int(result.converged),'logical_success':int(logical_correct),'logical_error':int(result.converged and not logical_correct),'non_convergence':int(not result.converged),'iterations':int(result.total_iterations),'relay_legs':used,'selected_weight':result.metadata.get('best_weight'),'final_rng_state':meta[used-1]['state'],'random_word_count':sum(x['words'] for x in meta[:used]),'accepted_gamma_count':sum(x['accepted'] for x in meta[:used]),'wall_seconds':elapsed,'full_budget':int(not result.converged)}
   all_shots.append(row);all_legs.extend(legs);all_iterations.extend(collector.rows);print(f'p={p:.3f} {shot+1}/{target_shots}: {result.total_iterations}i {used}l {elapsed:.2f}s',flush=True)
   # Predeclared runtime control: after the deterministic minimum 32 p=.004 shots,
   # stop if projecting 64 exceeds 45 decoder-minutes for this regime.
   if p==.004 and shot+1>=32 and np.mean(times)*64>45*60:
    completed=shot+1;det=det[:completed];obs=obs[:completed];sample_data[f'p{tag}_syndromes']=det;sample_data[f'p{tag}_logicals']=obs;break
  runtime[str(p)]={'shots_completed':completed,'decoder_wall_seconds':sum(times),'elapsed_wall_seconds':time.perf_counter()-started,'mean_seconds_per_shot':float(np.mean(times)),'max_seconds_per_shot':max(times),'full_budget_trajectories':sum(x['full_budget'] for x in all_shots if x['p']==p),'projected_64_decoder_minutes':float(np.mean(times)*64/60)}
  with np.load(pkg/'circuit_samples.npz') as existing:existing_count=int(existing['detectors'].shape[0])
  package_audit.append({'p':p,'package_path':str(pkg.relative_to(ROOT)),'existing_sample_path':str((pkg/'circuit_samples.npz').relative_to(ROOT)),'existing_samples':existing_count,'existing_has_syndrome':True,'existing_has_logical':True,'validation_sample_seed':sample_seed,'validation_shots':completed})
 np.savez_compressed(OUT/'validation_samples.npz',**sample_data,p0p002_sample_seed=np.uint64(20260902),p0p004_sample_seed=np.uint64(20260904))
 attach_targets(all_iterations,all_legs)
 write_csv(OUT/'per_shot_results.csv',all_shots);write_csv(OUT/'per_leg_summary.csv',all_legs)
 # Frozen metrics and secondary sensitivity, with risk-set strata.
 validation={}
 for p in (.002,.004):
  ps=[x for x in all_shots if x['p']==p];pl=[x for x in all_legs if x['p']==p];key={(x['sample_seed'],x['shot']):x for x in ps}
  validation[str(p)]={'shots':len(ps),'outcomes':{'one_leg_success':sum(x['converged'] and x['relay_legs']==1 for x in ps),'multi_leg_success':sum(x['converged'] and x['relay_legs']>1 for x in ps),'failure':sum(x['non_convergence'] for x in ps),'logical_errors':sum(x['logical_error'] for x in ps)},'legs':len(pl),'unproductive_legs':sum(x['category']!='productive' for x in pl),'unproductive_leg_rate':float(np.mean([x['category']!='productive' for x in pl])),'frozen_120':{},'sensitivity_context':{}}
  strata={'all_multi_leg':[x for x in pl if key[(x['sample_seed'],x['shot'])]['relay_legs']>1],'multi_leg_success':[x for x in pl if key[(x['sample_seed'],x['shot'])]['relay_legs']>1 and key[(x['sample_seed'],x['shot'])]['converged']],'eventual_failure':[x for x in pl if key[(x['sample_seed'],x['shot'])]['non_convergence']]}
  for name,z in strata.items():validation[str(p)]['frozen_120'][name]={str(t):metrics(z,t,120) for t in range(1,5)}
  validation[str(p)]['sensitivity_context']={str(th):{str(t):metrics(strata['all_multi_leg'],t,th) for t in range(1,5)} for th in (60,240)}
 (OUT/'validation_metrics.json').write_text(json.dumps(validation,indent=2)+'\n')
 manifest={'purpose':'out-of-sample validation; frozen rule, no tuning','packages':package_audit,'sample_archive':'validation_samples.npz','sample_generation':'stim circuit detector sampler, separate observables','decoder_seed_derivation':'splitmix64(BASE_SEED ^ sample_seed ^ (shot * 0x100000001b3))','base_decoder_seed':BASE,'configuration':{'b':18,'accumulator_bits':22,'M':16,'S':1,'R':32,'first_gamma_encoded':2,'first_limit':80,'later_limit':60,'later_gamma_interval':[-.24,.66],'rng':'xorshift64(13,7,17)'},'frozen_rule':'iterations_since_last_strict_new_best >= 120 at completed relay-leg boundary','runtime_stop_rule':'p=.004 may stop after >=32 if projected 64-shot decoder time exceeds 45 minutes','runtime':runtime}
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(runtime,indent=2))
if __name__=='__main__':main()

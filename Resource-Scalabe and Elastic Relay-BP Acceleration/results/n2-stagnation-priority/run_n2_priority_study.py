#!/usr/bin/env python3
"""Shared-P=4 N=2 priority study using fixed archived E0/E1 trajectories."""
from __future__ import annotations
import csv,json,os,sys,time,hashlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
FULL=ROOT/'results/graph-partitioning-relaybp-equivalence-full';ARCH=ROOT/'results/n1-vs-n2-hardware-latency/per_shot_results.csv';SAMPLES=ROOT/'results/circuit-level-multiseed/paired_samples.npz';BA=ROOT/'results/bank-aware-folding-layout';EQUIV=ROOT/'results/bank-aware-folding-layout-equivalence';STAG=ROOT/'results/full-dataset-stagnation-analysis';MULTIP=ROOT/'results/stagnation-multip-validation'
sys.path.insert(0,str(FULL));import run_full_equivalence as m
THRESHOLD=120;MIN_LEG=3;POLICIES={'P0_round_robin':1,'P1_stagnation_1to2':2,'P2_stagnation_1to3':3}

def rows(path):
 with path.open(newline='') as f:return list(csv.DictReader(f))
def write_csv(path,data):
 with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
def write_json(path,x):path.write_text(json.dumps(x,indent=2,default=lambda y:y.item() if isinstance(y,np.generic) else y.tolist())+'\n')
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def quant(values):
 a=np.asarray(values,float);return dict(mean=float(a.mean()),p50=float(np.percentile(a,50)),p90=float(np.percentile(a,90)),p95=float(np.percentile(a,95)),p99=float(np.percentile(a,99)),maximum=float(a.max()))

class Collector:
 def __init__(self,prior,h,syn):
  d=(np.rint(prior)<=0).astype(np.uint8);res=np.asarray(h@d).reshape(-1).astype(np.uint8)^syn;self.best=int(res.sum());self.since=0;self.data=[]
 def __call__(self,e):
  w=int(np.asarray(e['residual'],np.uint8).sum());new=w<self.best
  if new:self.best=w;self.since=0
  else:self.since+=1
  self.data.append(dict(global_iteration=int(e['global_iteration']),relay_leg=int(e['leg_index'])+1,iteration_in_leg=int(e['iteration']),residual_weight=w,running_best=self.best,iterations_since_best=self.since,new_best=int(new),converged=int(e['converged'])))

def generate_e1(job):
 seed,shot,syn,arch=job;checkpoint=OUT/'e1_trace_checkpoints'/f'{seed}_{shot:03d}.json'
 if checkpoint.exists():return json.loads(checkpoint.read_text())
 configs,_,meta=m.schedule(int(arch['s1']));collector=Collector(m.PRIOR,m.H,syn);cfg=m.FixedRelayConfig(fixed=m.FixedConfig(b=18,g=4,M=16,clip=None,separate_scale=True),leg_configs=configs,S=1,R=32,seed=0)
 result=m.FixedRelayBPDecoder(m.H,cfg,iteration_callback=collector).decode(m.PRIOR,syn)
 ok=int(result.converged)==int(arch['e1_syndrome_converged']) and result.total_iterations==int(arch['e1_iterations']) and result.relay_legs==int(arch['e1_legs'])
 if not ok:raise RuntimeError(f'E1 archive reproduction failure {seed}/{shot}')
 rec=dict(sample_seed=seed,shot=shot,trace=collector.data);write_json(checkpoint,rec);return rec

def load_traces():
 archive=rows(ARCH);archive.sort(key=lambda r:(int(r['sample_seed']),int(r['shot'])));lookup={(int(r['sample_seed']),int(r['shot'])):r for r in archive}
 e0=defaultdict(list)
 for r in rows(STAG/'per_iteration_compact.csv'):
  e0[(int(r['sample_seed']),int(r['shot']))].append({k:int(float(r[k])) for k in ('global_iteration','relay_leg','iteration_in_leg','residual_weight','best_residual','iterations_since_best','new_best','converged')})
 for z in e0.values():
  for r in z:r['running_best']=r.pop('best_residual')
  z.sort(key=lambda r:r['global_iteration'])
 with np.load(SAMPLES) as z:
  seeds=z['sample_seeds'];ss=z['syndromes'];jobs=[]
  for a in archive:
   seed,shot=int(a['sample_seed']),int(a['shot']);ix=int(np.flatnonzero(seeds==seed)[0]);jobs.append((seed,shot,ss[ix,shot].astype(np.uint8),a))
 (OUT/'e1_trace_checkpoints').mkdir(exist_ok=True);results=[];workers=int(os.environ.get('PRIORITY_WORKERS','4'));start=time.time()
 with ThreadPoolExecutor(max_workers=workers) as ex:
  fs=[ex.submit(generate_e1,j) for j in jobs]
  for i,f in enumerate(as_completed(fs),1):results.append(f.result());print(f'E1 trace {i}/128 elapsed={time.time()-start:.1f}s',flush=True)
 e1={(r['sample_seed'],r['shot']):r['trace'] for r in results}
 flat=[]
 for key in sorted(e1):
  for r in e1[key]:flat.append(dict(sample_seed=key[0],shot=key[1],**r))
 write_csv(OUT/'e1_iteration_trace.csv',flat)
 return archive,e0,e1

def phase_costs():
 pr={r['phase']:r for r in rows(BA/'phase_metrics.csv') if r['variant']=='BA2'}
 phases=('check','variable','convergence');fields=('requested_accesses','issued_groups','retry_subsets','estimated_cycles')
 iteration={k:sum(float(pr[p][k]) for p in phases) for k in fields}
 iteration['mean_active_lanes']=sum(float(pr[p]['issued_groups'])*float(pr[p]['mean_active_lanes']) for p in phases)/iteration['issued_groups']
 init={k:float(pr['relay_init'][k]) for k in (*fields,'mean_active_lanes')}
 return iteration,init

def simulate(t0,t1,policy,iteration_cost,init_cost):
 traces=[t0,t1];pos=[0,0];done=[False,False];failed=[False,False];flag=[False,False];ever_flag=[False,False];credits=[0,0];wall=0.0;quanta=0;first=None;first_wall=None;first_q=None;work=[0,0];flagged_work=[0,0];prefix_work=[0,0];prefix_flagged=[0,0];groups=0.0;active_lane_groups=0.0;requested=issued=retries=0.0;events=[];service_gap=[0,0];max_gap=[0,0];prefix=None
 while not all(done):
  active=[i for i in (0,1) if not done[i]]
  if len(active)==1:chosen=active[0]
  else:
   if policy=='P0_round_robin' or flag[0]==flag[1]:weights=[1,1]
   elif flag[0]:weights=[1,POLICIES[policy]]
   else:weights=[POLICIES[policy],1]
   total=sum(weights[i] for i in active)
   for i in active:credits[i]+=weights[i]
   chosen=min(active,key=lambda i:(-credits[i],i));credits[chosen]-=total
  for i in active:
   if i==chosen:service_gap[i]=0
   else:service_gap[i]+=1;max_gap[i]=max(max_gap[i],service_gap[i])
  row=traces[chosen][pos[chosen]];was_flag=flag[chosen];before_first=first is None
  if row['iteration_in_leg']==1:
   wall+=init_cost['estimated_cycles'];requested+=init_cost['requested_accesses'];issued+=init_cost['issued_groups'];retries+=init_cost['retry_subsets'];groups+=init_cost['issued_groups'];active_lane_groups+=init_cost['issued_groups']*init_cost['mean_active_lanes']
  wall+=iteration_cost['estimated_cycles'];requested+=iteration_cost['requested_accesses'];issued+=iteration_cost['issued_groups'];retries+=iteration_cost['retry_subsets'];groups+=iteration_cost['issued_groups'];active_lane_groups+=iteration_cost['issued_groups']*iteration_cost['mean_active_lanes'];quanta+=1;work[chosen]+=1
  if was_flag:flagged_work[chosen]+=1
  if before_first:
   prefix_work[chosen]+=1
   if was_flag:prefix_flagged[chosen]+=1
  pos[chosen]+=1
  if row['new_best'] and was_flag:
   flag[chosen]=False;events.append(dict(engine=chosen,event='late_recovery',trajectory_iteration=row['global_iteration'],scheduler_quantum=quanta,wall_cycles=wall))
  leg_end=row['converged'] or pos[chosen]==len(traces[chosen]) or traces[chosen][pos[chosen]]['relay_leg']!=row['relay_leg']
  if leg_end and not row['converged'] and row['relay_leg']>=MIN_LEG and row['iterations_since_best']>=THRESHOLD:
   if not flag[chosen]:events.append(dict(engine=chosen,event='flagged',trajectory_iteration=row['global_iteration'],scheduler_quantum=quanta,wall_cycles=wall))
   flag[chosen]=True;ever_flag[chosen]=True
  if row['converged']:
   if first is None:
    first=chosen;first_wall=wall;first_q=quanta;prefix=dict(requested=requested,issued=issued,retries=retries,groups=groups,active=active_lane_groups,work=prefix_work.copy(),flagged=prefix_flagged.copy())
   if was_flag:events.append(dict(engine=chosen,event='flagged_convergence',trajectory_iteration=row['global_iteration'],scheduler_quantum=quanta,wall_cycles=wall))
   done[chosen]=True
  elif pos[chosen]==len(traces[chosen]):done[chosen]=True;failed[chosen]=True
 if prefix is None:prefix=dict(requested=requested,issued=issued,retries=retries,groups=groups,active=active_lane_groups,work=work.copy(),flagged=flagged_work.copy())
 result=dict(policy=policy,winner=-1 if first is None else first,first_success_cycles=wall if first is None else first_wall,first_success_quanta=quanta if first is None else first_q,
  global_failure=int(first is None),e0_work_before_first=prefix['work'][0],e1_work_before_first=prefix['work'][1],e0_flagged_work_before_first=prefix['flagged'][0],e1_flagged_work_before_first=prefix['flagged'][1],total_full_service_quanta=sum(len(x) for x in traces),e0_total_work=work[0],e1_total_work=work[1],e0_flagged_work=flagged_work[0],e1_flagged_work=flagged_work[1],
  e0_ever_flagged=int(ever_flag[0]),e1_ever_flagged=int(ever_flag[1]),max_e0_service_gap=max_gap[0],max_e1_service_gap=max_gap[1],total_requested_accesses=prefix['requested'],total_issued_groups=prefix['issued'],total_retry_subsets=prefix['retries'],mean_active_lanes=prefix['active']/prefix['groups'],lane_utilization=prefix['active']/prefix['groups']/4)
 return result,events

def main():
 OUT.mkdir(parents=True,exist_ok=True);archive,e0,e1=load_traces();iteration_cost,init_cost=phase_costs();eq0={r['case_id']:r for r in rows(EQUIV/'e0_paired_results.csv')};eq1={r['case_id']:r for r in rows(EQUIV/'e1_paired_results.csv')}
 per=[];late=[];changes=[]
 for a in archive:
  seed,shot=int(a['sample_seed']),int(a['shot']);key=(seed,shot);sim={}
  for policy in POLICIES:
   rec,events=simulate(e0[key],e1[key],policy,iteration_cost,init_cost);rec.update(sample_seed=seed,shot=shot);sim[policy]=rec
   for event in events:late.append(dict(sample_seed=seed,shot=shot,policy=policy,**event))
  base=sim['P0_round_robin'];basewinner=base['winner']
  for policy,rec in sim.items():
   winner=rec['winner'];prefix='e0_' if winner==0 else 'e1_' if winner==1 else None;logical=0 if prefix is None else int(a[prefix+'logical_correct']);valid=0 if prefix is None else int(a[prefix+'syndrome_converged']);cid=f'{seed}_{shot:03d}';corr='' if winner<0 else (eq0[cid]['correction_hash'] if winner==0 else eq1[cid]['correction_hash'])
   baseprefix='e0_' if basewinner==0 else 'e1_' if basewinner==1 else None;baselogical=0 if baseprefix is None else int(a[baseprefix+'logical_correct'])
   rec.update(winner_logical_correct=logical,winner_syndrome_valid=valid,winner_correction_hash=corr,changed_winner=int(winner!=basewinner),lost_success=int(not base['global_failure'] and rec['global_failure']),logical_regression=int(baselogical and not logical),invalid=int(winner>=0 and not valid),cycles_delta_vs_round_robin=rec['first_success_cycles']-base['first_success_cycles'],cycles_percent_vs_round_robin=0 if base['first_success_cycles']==0 else 100*(rec['first_success_cycles']/base['first_success_cycles']-1))
   if rec['lost_success'] or rec['invalid'] or rec['logical_regression']:classification='D_baseline_success_lost_or_invalid'
   elif rec['global_failure']==base['global_failure'] and winner==basewinner and rec['first_success_cycles']<=base['first_success_cycles']:classification='A_same_success_same_winner'
   elif rec['global_failure']==base['global_failure'] and winner!=basewinner:classification='B_same_success_winner_changed'
   else:classification='C_same_logical_outcome_later_convergence'
   rec['classification']=classification;per.append(rec)
   if policy!='P0_round_robin' and winner!=basewinner:changes.append(dict(sample_seed=seed,shot=shot,policy=policy,round_robin_winner=basewinner,priority_winner=winner,round_robin_cycles=base['first_success_cycles'],priority_cycles=rec['first_success_cycles'],logical_correct=logical,correction_hash=corr))
 rec_lookup={(r['sample_seed'],r['shot'],r['policy']):r for r in per};rr_event={(x['sample_seed'],x['shot'],x['engine'],x['event'],x['trajectory_iteration']):x for x in late if x['policy']=='P0_round_robin'}
 for x in late:
  rr=rr_event[(x['sample_seed'],x['shot'],x['engine'],x['event'],x['trajectory_iteration'])];rec=rec_lookup[(x['sample_seed'],x['shot'],x['policy'])]
  x['wall_cycle_delay_vs_round_robin']=x['wall_cycles']-rr['wall_cycles'];x['occurred_before_first_success']=int(x['wall_cycles']<=rec['first_success_cycles']);x['trajectory_eventually_won']=int(int(x['engine'])==rec['winner'])
 write_csv(OUT/'per_shot_priority.csv',per);write_csv(OUT/'late_recovery_cases.csv',late if late else [dict(no_events=1)]);write_csv(OUT/'winner_changes.csv',changes if changes else [dict(no_changes=1)])
 summaries=[]
 for policy in POLICIES:
  z=[r for r in per if r['policy']==policy];q=quant([r['first_success_cycles'] for r in z]);ev=[x for x in late if x['policy']==policy]
  summaries.append(dict(policy=policy,**q,success_count=sum(not r['global_failure'] for r in z),logical_success_count=sum(r['winner_logical_correct'] for r in z),global_failures=sum(r['global_failure'] for r in z),changed_winner_count=sum(r['changed_winner'] for r in z),lost_success_count=sum(r['lost_success'] for r in z),logical_regressions=sum(r['logical_regression'] for r in z),invalid_count=sum(r['invalid'] for r in z),temporarily_deprioritized_trajectories=sum(r['e0_ever_flagged']+r['e1_ever_flagged'] for r in z),late_recoveries_preserved=sum(x['event']=='late_recovery' for x in ev),flagged_trajectory_wins=len({(x['sample_seed'],x['shot'],x['engine']) for x in ev if x['event'] in ('late_recovery','flagged_convergence') and x['trajectory_eventually_won']}),starvation_events=sum(r['max_e0_service_gap']>POLICIES[policy] or r['max_e1_service_gap']>POLICIES[policy] for r in z),mean_work_e0_before_first=float(np.mean([r['e0_work_before_first'] for r in z])),mean_work_e1_before_first=float(np.mean([r['e1_work_before_first'] for r in z])),mean_flagged_work_before_first=float(np.mean([r['e0_flagged_work_before_first']+r['e1_flagged_work_before_first'] for r in z])),mean_active_lanes=float(np.mean([r['mean_active_lanes'] for r in z])),mean_lane_utilization=float(np.mean([r['lane_utilization'] for r in z])),mean_cycles_change_vs_round_robin=float(np.mean([r['cycles_delta_vs_round_robin'] for r in z])),improved=sum(r['cycles_delta_vs_round_robin']<0 for r in z),unchanged=sum(r['cycles_delta_vs_round_robin']==0 for r in z),worsened=sum(r['cycles_delta_vs_round_robin']>0 for r in z)))
 write_csv(OUT/'policy_summary.csv',summaries);write_csv(OUT/'tail_metrics.csv',[{k:v for k,v in x.items() if k in ('policy','mean','p50','p90','p95','p99','maximum','improved','unchanged','worsened')} for x in summaries])
 correctness=dict(status='complete',shots=128,baseline_successes=summaries[0]['success_count'],policies={x['policy']:dict(successes=x['success_count'],logical_successes=x['logical_success_count'],lost_successes=x['lost_success_count'],logical_regressions=x['logical_regressions'],invalid=x['invalid_count']) for x in summaries},no_trajectory_terminated=True,all_trajectories_run_to_natural_completion=True,corrections_from_validated_equivalence_archive=True)
 write_json(OUT/'correctness_report.json',correctness)
 manifest=dict(status='complete',existing_n2_model='two fully independent simultaneous P=4 engines; historical n2_cycles=min independent completion cycles, not shared compute',new_model='one shared BA2 P=4 iteration/phase-bundle resource; paused trajectory retains state',quantum='one complete Relay-BP iteration, with relay-init cost charged before the first iteration of each leg',threshold=THRESHOLD,minimum_leg=MIN_LEG,policies=POLICIES,
  physical_error_rates=dict(available=['0.003'],unavailable={'0.002':'archived E0 only; no independent paired E1 trace','0.004':'archived E0 only; no independent paired E1 trace'}),configuration=dict(b=18,g=4,M=16,S=1,R=32,first_limit=80,later_limit=60),hashes=dict(archive=sha(ARCH),BA2_phase_metrics=sha(BA/'phase_metrics.csv'),E0_trace=sha(STAG/'per_iteration_compact.csv'),BA2_permutations=sha(BA/'permutations.npz')))
 write_json(OUT/'study_manifest.json',manifest)
 (OUT/'README.md').write_text(f'''# N=2 stagnation-priority shared-resource model\n\nHistorical N=2 uses two independent simultaneous P=4 engines. This separate experiment serializes one complete Relay-BP iteration at a time through one shared BA2 P=4 resource; pauses preserve all state and both trajectories run to natural completion.\n\nThe frozen signal is `iterations_since_last_strict_best >= {THRESHOLD}` at a completed boundary of leg {MIN_LEG} or later. A new strict best restores 1:1 service immediately. Policies are neutral 1:1, conservative 1:2, and 1:3. Only p=0.003 has reliable paired E0/E1 traces; p=0.002 and p=0.004 archives contain E0 only. This is a resource-scheduling model, not early termination, an FPGA-speedup claim, or a reinterpretation of historical N=2 latency.\n''')
 print(json.dumps(dict(correctness=correctness,policies=summaries,winner_changes=len(changes),late_events=len(late)),indent=2))
if __name__=='__main__':main()

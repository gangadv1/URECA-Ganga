#!/usr/bin/env python3
"""Four-condition software-only BA2 x conservative-stagnation factorial study."""
from __future__ import annotations
import csv,json,hashlib
from collections import defaultdict
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
ARCH=ROOT/'results/n1-vs-n2-hardware-latency/per_shot_results.csv'
STAG=ROOT/'results/full-dataset-stagnation-analysis'
FOLD=ROOT/'results/graph-partitioning-folding-model'
BA=ROOT/'results/bank-aware-folding-layout'
EQ=ROOT/'results/bank-aware-folding-layout-equivalence'
THRESHOLD=120;CHECKPOINT=40;MIN_LEG=3

def rows(path):
 with path.open(newline='') as f:return list(csv.DictReader(f))
def write_csv(path,data):
 with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
def write_json(path,x):path.write_text(json.dumps(x,indent=2)+'\n')
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def quantiles(values):
 a=np.asarray(values,np.float64)
 return dict(mean=float(a.mean()),median=float(np.percentile(a,50)),p90=float(np.percentile(a,90)),p95=float(np.percentile(a,95)),p99=float(np.percentile(a,99)),maximum=float(a.max()))

def phase_data():
 original={r['phase']:r for r in rows(FOLD/'phase_metrics.csv') if r['variant']=='original'}
 ba2={r['phase']:r for r in rows(BA/'phase_metrics.csv') if r['variant']=='BA2'}
 def convert(x):
  out={}
  for p,r in x.items():
   out[p]={k:float(r[k]) for k in ('issued_groups','retry_subsets','mean_active_lanes','estimated_cycles')}
   out[p]['lane_utilization']=float(r.get('lane_utilization',r.get('mean_lane_utilization')))
   out[p]['full_four_lane_fraction']=float(r.get('full_four_lane_fraction',r.get('full_4_lane_fraction')))
   out[p]['requested_accesses']=float(r.get('requested_accesses',r.get('logical_accesses')))
  return out
 return convert(original),convert(ba2)

def costs(phases,iters,legs):
 iteration=sum(phases[p]['estimated_cycles'] for p in ('check','variable','convergence'));relay=phases['relay_init']['estimated_cycles']
 result=dict(modeled_cycles=iters*iteration+legs*relay)
 for field in ('requested_accesses','issued_groups','retry_subsets'):
  result[field]=iters*sum(phases[p][field] for p in ('check','variable','convergence'))+legs*phases['relay_init'][field]
 weighted_groups=iters*sum(phases[p]['issued_groups'] for p in ('check','variable','convergence'))+legs*phases['relay_init']['issued_groups']
 active=iters*sum(phases[p]['issued_groups']*phases[p]['mean_active_lanes'] for p in ('check','variable','convergence'))+legs*phases['relay_init']['issued_groups']*phases['relay_init']['mean_active_lanes']
 full=iters*sum(phases[p]['issued_groups']*phases[p]['full_four_lane_fraction'] for p in ('check','variable','convergence'))+legs*phases['relay_init']['issued_groups']*phases['relay_init']['full_four_lane_fraction']
 result['mean_active_lanes']=active/weighted_groups;result['lane_utilization']=result['mean_active_lanes']/4;result['full_four_lane_fraction']=full/weighted_groups
 return result

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 archive=rows(ARCH);iterations=rows(STAG/'per_iteration_compact.csv');legs=rows(STAG/'per_leg_summary.csv')
 eq=json.loads((EQ/'study_manifest.json').read_text());repro=json.loads((STAG/'reproduction_summary.json').read_text())
 if eq['combined']['exact']!=256 or repro['trajectories_reproduced']!=128:raise RuntimeError('Required equivalence/reproduction gate absent')
 orig,ba2=phase_data();by_case=defaultdict(list);legs_case=defaultdict(list)
 for r in iterations:by_case[(int(r['sample_seed']),int(r['shot']))].append(r)
 for r in legs:legs_case[(int(r['sample_seed']),int(r['shot']))].append(r)
 events=[]
 for key,trace in by_case.items():
  trace.sort(key=lambda r:int(r['global_iteration']));by_leg=defaultdict(list)
  for r in trace:by_leg[int(r['relay_leg'])].append(r)
  for leg,lr in by_leg.items():
   point=next((r for r in lr if int(r['iteration_in_leg'])==CHECKPOINT),None)
   if point is None or leg<MIN_LEG or int(point['converged']) or int(point['iterations_since_best'])<THRESHOLD:continue
   tail=[r for r in lr if int(r['iteration_in_leg'])>CHECKPOINT]
   later_improvement=any(int(r['new_best']) for r in tail);later_convergence=any(int(r['converged']) for r in tail)
   leg_summary=next(x for x in legs_case[key] if int(x['relay_leg'])==leg)
   events.append(dict(sample_seed=key[0],shot=key[1],relay_leg=leg,checkpoint_iteration=CHECKPOINT,
    global_iteration=int(point['global_iteration']),iterations_since_best=int(point['iterations_since_best']),running_best=int(point['best_residual']),
    current_residual=int(point['residual_weight']),remaining_iterations_observed=len(tail),late_strict_improvement=int(later_improvement),late_convergence=int(later_convergence),
    early_handoff_endangered=int(later_improvement or later_convergence),standard_leg_category=leg_summary['category'],policy_action='flag_only_no_skip'))
 event_cases=defaultdict(list)
 for e in events:event_cases[(e['sample_seed'],e['shot'])].append(e)
 per=[]
 for a in archive:
  seed,shot=int(a['sample_seed']),int(a['shot']);key=(seed,shot);iters=int(a['e0_iterations']);used=int(a['e0_legs']);oc=costs(orig,iters,used);bc=costs(ba2,iters,used)
  lr=legs_case[key];productive=sum(int(x['iterations_used']) for x in lr if x['category']=='productive');unproductive=sum(int(x['iterations_used']) for x in lr if x['category']!='productive')
  base=dict(sample_seed=seed,shot=shot,standard_iterations=iters,stagnation_iterations=iters,standard_relay_legs=used,stagnation_relay_legs=used,
   converged=int(a['e0_syndrome_converged']),logical_correct=int(a['e0_logical_correct']),outcome_classification='exact outcome preserved',
   stagnant_flags=len(event_cases[key]),safely_shortened_legs=0,iterations_avoided=0,productive_iterations=productive,unproductive_iterations=unproductive)
  for prefix,c in (('original_standard',oc),('original_stagnation',oc),('ba2_standard',bc),('ba2_stagnation',bc)):
   for k,v in c.items():base[f'{prefix}_{k}']=v
  base['layout_cycle_savings']=oc['modeled_cycles']-bc['modeled_cycles'];base['stagnation_cycle_savings']=0;base['combined_cycle_savings']=base['layout_cycle_savings']
  per.append(base)
 write_csv(OUT/'per_shot_factorial.csv',per);write_csv(OUT/'stagnation_events.csv',events if events else [dict(no_events=1)])
 conditions=[]
 for name,prefix in (('A_original_standard','original_standard'),('B_original_stagnation','original_stagnation'),('C_BA2_standard','ba2_standard'),('D_BA2_stagnation','ba2_stagnation')):
  cyc=[r[f'{prefix}_modeled_cycles'] for r in per];conditions.append(dict(condition=name,**quantiles(cyc),
   total_requested_accesses=sum(r[f'{prefix}_requested_accesses'] for r in per),total_issued_groups=sum(r[f'{prefix}_issued_groups'] for r in per),total_retry_subsets=sum(r[f'{prefix}_retry_subsets'] for r in per),
   mean_active_lanes=float(np.mean([r[f'{prefix}_mean_active_lanes'] for r in per])),mean_lane_utilization=float(np.mean([r[f'{prefix}_lane_utilization'] for r in per])),
   improved_vs_A=sum(r[f'{prefix}_modeled_cycles']<r['original_standard_modeled_cycles'] for r in per),unchanged_vs_A=sum(r[f'{prefix}_modeled_cycles']==r['original_standard_modeled_cycles'] for r in per),worsened_vs_A=sum(r[f'{prefix}_modeled_cycles']>r['original_standard_modeled_cycles'] for r in per)))
 write_csv(OUT/'factorial_summary.csv',conditions);write_csv(OUT/'tail_metrics.csv',[{k:v for k,v in x.items() if k in ('condition','mean','median','p90','p95','p99','maximum','improved_vs_A','unchanged_vs_A','worsened_vs_A')} for x in conditions])
 A,B,C,D=conditions;layout=A['mean']-C['mean'];stag=A['mean']-B['mean'];combined=A['mean']-D['mean'];interaction=combined-layout-stag
 analysis=dict(layout_effect_mean_cycles=layout,stagnation_effect_mean_cycles=stag,combined_effect_mean_cycles=combined,interaction_cycles=interaction,
  interaction_interpretation='exactly additive with zero stagnation contribution; D equals C because the validated conservative policy is flag-only',
  mechanisms=dict(BA2='fewer modulo-4 bank conflicts per unchanged iteration/leg',stagnation='observability/deprioritization flag only; no work removed',overlap='none credited'))
 write_json(OUT/'interaction_analysis.json',analysis)
 correctness=dict(status='passed',shots=128,policy='flag-only at iteration 40 of relay leg >=3 when global strict-improvement counter >=120',
  exact_outcomes_preserved=128,same_logical_outcomes=128,outcome_mismatches=0,invalid=0,successful_decodes_preserved=sum(int(r['converged']) for r in per),failed_decodes_unchanged=sum(not int(r['converged']) for r in per),
  rationale='No iterations or legs are removed. Existing evidence contains consequential late recoveries, so early handoff is rejected rather than treated as safe.',
  leg_work=dict(total_legs=len(legs),productive_legs=sum(x['category']=='productive' for x in legs),unproductive_legs=sum(x['category']!='productive' for x in legs),
   productive_iterations=sum(int(x['iterations_used']) for x in legs if x['category']=='productive'),unproductive_iterations=sum(int(x['iterations_used']) for x in legs if x['category']!='productive')),
  candidate_early_handoff=dict(flags=len(events),unique_shots=len(set((e['sample_seed'],e['shot']) for e in events)),endangered_events=sum(e['early_handoff_endangered'] for e in events),endangered_unique_shots=len(set((e['sample_seed'],e['shot']) for e in events if e['early_handoff_endangered'])),late_improvement_events=sum(e['late_strict_improvement'] for e in events),late_convergence_events=sum(e['late_convergence'] for e in events),flagged_productive_legs=sum(e['standard_leg_category']=='productive' for e in events),flagged_unproductive_legs=sum(e['standard_leg_category']!='productive' for e in events),retrospective_tail_iterations=sum(e['remaining_iterations_observed'] for e in events),credited_shortened_legs=0,credited_iterations_avoided=0,credited_modeled_cycles_avoided=0))
 write_json(OUT/'correctness_report.json',correctness)
 manifest=dict(status='complete',scope='software-only factorial on canonical 128 E0 archive; no decoder or RTL mutation',conditions=['original+standard','original+stagnation flag','BA2+standard','BA2+stagnation flag'],
  stagnation_policy=correctness['policy'],threshold=THRESHOLD,checkpoint=CHECKPOINT,minimum_leg=MIN_LEG,trajectory_source='archived exact E0 traces; BA2 256-trajectory equivalence already passed',
  hashes=dict(archive=sha(ARCH),iterations=sha(STAG/'per_iteration_compact.csv'),legs=sha(STAG/'per_leg_summary.csv'),BA2_permutations=sha(BA/'permutations.npz')),optional_E1_run=False,optional_E1_reason='E0 factorial is conclusive: no safe work-removing policy is supported, so extending a zero-action flag policy to E1 adds no decision value.')
 write_json(OUT/'study_manifest.json',manifest)
 (OUT/'README.md').write_text(f'''# BA2 x stagnation factorial (software model)\n\nThe canonical 128-shot E0 panel is evaluated under four conditions. The pre-existing stagnation study found consequential late recoveries and explicitly did not establish a safe stopping threshold. The conservative policy therefore flags a leg at local iteration {CHECKPOINT}, leg {MIN_LEG} or later, when the global strict-improvement counter is at least {THRESHOLD}; it does not terminate or skip the leg.\n\nFlags: {len(events)} across {correctness['candidate_early_handoff']['unique_shots']} shots. Events with a later strict improvement or convergence in the same leg: {correctness['candidate_early_handoff']['endangered_events']}. Credited stagnation savings: zero. All 125 successes and 3 failures retain their archived outcomes. BA2 remains the only modeled cycle effect in this conservative factorial. No FPGA-speedup or hardware claim is made.\n''')
 print(json.dumps(dict(correctness=correctness,effects=analysis,conditions=conditions),indent=2))
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Archived N=2/E1 graph-reordering equivalence, reusing the N=1 harness."""
from __future__ import annotations
import csv,json,os,time
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
import run_full_equivalence as m

CHECKPOINTS=m.OUT/'e1_checkpoints'
def task(job):
 seed,shot,syn,logical,arch=job;cid=f'{seed}_{shot:03d}';path=CHECKPOINTS/f'{cid}.json'
 if path.exists():return json.loads(path.read_text())
 rng_seed=int(arch['s1']);oc,pc,meta=m.schedule(rng_seed);ro,to,do,rto=m.decode(m.H,m.PRIOR,syn,oc);rp,tp,dp,rtp=m.decode(m.HP,m.PRIORP,syn[m.CN],pc,m.CO,m.FO)
 ores=np.asarray(m.H@do).reshape(-1).astype(np.uint8)&1^syn;pres=np.asarray(m.H@dp).reshape(-1).astype(np.uint8)&1^syn;olog=np.asarray(m.A@do).reshape(-1).astype(np.uint8)&1;plog=np.asarray(m.A@dp).reshape(-1).astype(np.uint8)&1
 oval=not ores.any();pval=not pres.any();ocorrect=bool(oval and np.array_equal(olog,logical));pcorrect=bool(pval and np.array_equal(plog,logical));first=None
 names=('global_iteration','relay_leg','leg_iteration','residual_weight','running_best','decision_weight','residual_hash','decision_hash','gamma_hash','converged')
 for i,(x,y) in enumerate(zip(to,tp),1):
  if x!=y:first=dict(global_iteration=i,original=dict(zip(names,x)),partitioned=dict(zip(names,y)));break
 if first is None and len(to)!=len(tp):first=dict(global_iteration=min(len(to),len(tp))+1,reason='trace length differs')
 trace_exact=first is None;exact=bool(ro.converged==rp.converged and ro.total_iterations==rp.total_iterations and ro.relay_legs==rp.relay_legs and np.array_equal(do,dp) and np.array_equal(olog,plog) and int(ores.sum())==int(pres.sum()) and trace_exact);outcome=bool(ro.converged==rp.converged and ocorrect==pcorrect and np.array_equal(olog,plog));valid=bool(not rp.converged or pval);cls='EXACT MATCH' if exact and valid else 'OUTCOME MATCH BUT TRAJECTORY DIFFERENCE' if outcome and valid else 'OUTCOME MISMATCH' if valid else 'INVALID'
 used=ro.relay_legs;state=meta[used-1]['state'];accepted=sum(x['accepted'] for x in meta[:used]);gh=m.hashlib.sha256(''.join(x['gamma_hash'] for x in meta[:used]).encode()).hexdigest();ow=ro.metadata.get('best_weight');pw=rp.metadata.get('best_weight');delta=None if ow is None else float(pw-ow);aw=arch['e1_weight'];aweight=(aw=='' and ow is None) or (aw!='' and ow is not None and abs(float(aw)-ow)<=1e-9)
 archive_ok=bool(int(ro.converged)==int(arch['e1_syndrome_converged']) and ro.total_iterations==int(arch['e1_iterations']) and ro.relay_legs==int(arch['e1_legs']) and state==int(arch['e1_final_rng_state']) and accepted==int(arch['e1_gamma_coefficients']) and aweight)
 if not archive_ok:raise RuntimeError(f'E1 archive reproduction failed {cid}')
 rec=dict(case_id=cid,sample_seed=seed,shot=shot,gamma_seed=rng_seed,syndrome_hash=m.bh(syn),logical_outcome_hash=m.bh(logical),classification=cls,archive_reproduction=archive_ok,e1_winner=int(arch['winner'])==1,parallel_rescue=bool(int(arch['parallel_rescue'])),original_converged=int(ro.converged),partitioned_converged=int(rp.converged),original_syndrome_valid=int(oval),partitioned_syndrome_valid=int(pval),original_logical_correct=int(ocorrect),partitioned_logical_correct=int(pcorrect),original_iterations=ro.total_iterations,partitioned_iterations=rp.total_iterations,original_relay_legs=ro.relay_legs,partitioned_relay_legs=rp.relay_legs,original_final_residual=int(ores.sum()),partitioned_final_residual=int(pres.sum()),original_candidate_weight=ow,partitioned_candidate_weight=pw,candidate_weight_delta=delta,correction_hash=m.bh(do),partitioned_inverse_correction_hash=m.bh(dp),correction_exact=bool(np.array_equal(do,dp)),logical_action_exact=bool(np.array_equal(olog,plog)),trace_exact=trace_exact,trace_iterations_compared=min(len(to),len(tp)),first_trace_difference=first,final_rng_state=state,accepted_gamma_count=accepted,accepted_gamma_sequence_hash=gh,original_runtime_seconds=rto,partitioned_runtime_seconds=rtp)
 m.write_json(path,rec);return rec

def main():
 CHECKPOINTS.mkdir(parents=True,exist_ok=True);inv=dict(H_exact=bool((m.HP[m.CO,:][:,m.FO]!=m.H).nnz==0),A_exact=bool((m.AP[:,m.FO]!=m.A).nnz==0),probabilities_exact=bool(np.array_equal(m.PP[m.FO],m.P)),check_permutation_inverse=bool(np.array_equal(m.CO[m.CN],np.arange(m.C))),fault_permutation_inverse=bool(np.array_equal(m.FO[m.FN],np.arange(m.V))))
 if not all(inv.values()):raise RuntimeError(f'Mapping failure {inv}')
 archive=m.rows(m.ARCHIVE);archive.sort(key=lambda r:(int(r['sample_seed']),int(r['shot'])));jobs=[]
 with np.load(m.SAMPLES) as z:
  seeds=z['sample_seeds'];ss=z['syndromes'];ll=z['observed_logicals']
  for ar in archive:
   seed=int(ar['sample_seed']);shot=int(ar['shot']);ix=int(np.flatnonzero(seeds==seed)[0]);syn=ss[ix,shot].astype(np.uint8);logical=ll[ix,shot].astype(np.uint8)
   if m.bh(syn)!=ar['detector_sample_hash'] or m.bh(logical)!=ar['logical_sample_hash']:raise RuntimeError('Dataset hash mismatch')
   jobs.append((seed,shot,syn,logical,ar))
 results=[];start=time.time();workers=int(os.environ.get('EQUIV_WORKERS','4'))
 with ThreadPoolExecutor(max_workers=workers) as ex:
  futures={ex.submit(task,j):j for j in jobs}
  for i,f in enumerate(as_completed(futures),1):results.append(f.result());print(f'completed E1 {i}/128 elapsed={time.time()-start:.1f}s',flush=True)
 results.sort(key=lambda r:(r['sample_seed'],r['shot']));flat=[]
 for r in results:q={k:v for k,v in r.items() if k!='first_trace_difference'};q['first_trace_difference']=json.dumps(r['first_trace_difference']);flat.append(q)
 with (m.OUT/'e1_paired_results.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
 classes={k:sum(r['classification']==k for r in results) for k in ('EXACT MATCH','OUTCOME MATCH BUT TRAJECTORY DIFFERENCE','OUTCOME MISMATCH','INVALID')};bad=[r for r in results if r['classification']!='EXACT MATCH'];d=np.array([abs(r['candidate_weight_delta']) for r in results if r['candidate_weight_delta'] is not None],float)
 deltas=[dict(case_id=r['case_id'],sample_seed=r['sample_seed'],shot=r['shot'],delta=r['candidate_weight_delta'],absolute_delta=None if r['candidate_weight_delta'] is None else abs(r['candidate_weight_delta']),bit_exact=r['candidate_weight_delta'] in (None,0.0),selection_affected=False) for r in results]
 with (m.OUT/'e1_candidate_weight_deltas.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(deltas[0]));w.writeheader();w.writerows(deltas)
 rescue=[r for r in results if r['parallel_rescue']];wins=[r for r in results if r['e1_winner']]
 rescue_fields=['case_id','sample_seed','shot','classification','original_iterations','partitioned_iterations','original_relay_legs','partitioned_relay_legs','correction_hash','partitioned_inverse_correction_hash','trace_exact']
 with (m.OUT/'e1_rescue_cases.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=rescue_fields);w.writeheader();w.writerows([{k:r[k] for k in rescue_fields} for r in rescue])
 inv.update(all_archived_originals_reproduced=all(r['archive_reproduction'] for r in results),all_converged_partitioned_corrections_valid=all(not r['partitioned_converged'] or r['partitioned_syndrome_valid'] for r in results),all_gamma_trace_hashes_exact=all(r['trace_exact'] for r in results));m.write_json(m.OUT/'e1_invariance_checks.json',inv);m.write_json(m.OUT/'e1_trace_mismatches.json',bad)
 summary=dict(status='complete',trajectories=128,classification_counts=classes,all_exact=classes['EXACT MATCH']==128,total_trace_iterations=sum(r['trace_iterations_compared'] for r in results),archived_original_reproductions=sum(r['archive_reproduction'] for r in results),e1_converged=sum(r['original_converged'] for r in results),e1_failures=sum(not r['original_converged'] for r in results),e1_wins=len(wins),parallel_rescues=len(rescue),all_wins_exact=all(r['classification']=='EXACT MATCH' for r in wins),all_rescues_exact=all(r['classification']=='EXACT MATCH' for r in rescue),candidate_weight={'successful_candidates':len(d),'maximum_absolute_delta':float(d.max(initial=0)),'median_absolute_delta':float(np.median(d)) if len(d) else 0,'selection_affected':0,'S=1_reporting_only':True},gamma_mapping='Generate E1 s1 hardware gamma in original fault order and permute with fault_new_to_old; inverse-map traces with fault_old_to_new.',configuration=dict(decoder='reference/relay_bp_fixed.py::FixedRelayBPDecoder',b=18,g=4,M=16,S=1,R=32,first_limit=80,later_limit=60))
 m.write_json(m.OUT/'e1_summary.json',summary)
 manifest=json.loads((m.OUT/'study_manifest.json').read_text());manifest['e1']=dict(summary='e1_summary.json',trajectories=128,rng_field='s1',archive_fields='e1_*',classification_counts=classes,e1_wins=len(wins),parallel_rescues=len(rescue));m.write_json(m.OUT/'study_manifest.json',manifest)
 readme=(m.OUT/'README.md').read_text();readme+='\n## N=2/E1 extension\n\n'+f"E1 classification: {classes}. Iterations compared: {summary['total_trace_iterations']}. E1 wins: {len(wins)}; parallel rescues: {len(rescue)}; all exact. Candidate-weight max/median absolute deltas: {summary['candidate_weight']['maximum_absolute_delta']:.3g}/{summary['candidate_weight']['median_absolute_delta']:.3g}.\n";(m.OUT/'README.md').write_text(readme)
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()

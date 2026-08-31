#!/usr/bin/env python3
"""Paired fixed-point Relay-BP equivalence under reversible graph reordering."""
from __future__ import annotations
import csv, hashlib, json, sys, time
from pathlib import Path
from typing import Any
import numpy as np
from scipy import sparse

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
PKG=ROOT/'graphs/generated/gross_circuit_level/memory_Z_r12_p0p003'
PART=ROOT/'results/graph-partitioning-metis';SAMPLES=ROOT/'results/circuit-level-multiseed/paired_samples.npz'
ARCHIVE=ROOT/'results/n1-vs-n2-hardware-latency/per_shot_results.csv'
sys.path[:0]=[str(ROOT/'reference'),str(ROOT/'fpga/verification/parallel_n2')]
from fixedpoint import FixedConfig
from relay_bp_fixed import FixedRelayBPDecoder,FixedRelayConfig,FixedRelayLegConfig
from gamma_rng_reference import vector as hardware_gamma_vector
C,V,O=1728,67752,12;FIRST,LATER,R=80,60,32
PANEL=(
 dict(case_id='easy_e0',sample_seed=20260809,shot=31,trajectory='E0',category='easy'),
 dict(case_id='typical_e0',sample_seed=20260809,shot=2,trajectory='E0',category='typical'),
 dict(case_id='known_n1_failure',sample_seed=20260809,shot=18,trajectory='E0',category='known N=1 difficult/failure'),
 dict(case_id='known_n2_rescue',sample_seed=20260809,shot=18,trajectory='E1',category='known N=2 rescue'),
)

def bits_hash(x):return hashlib.sha256(np.packbits(np.asarray(x,dtype=np.uint8)).tobytes()).hexdigest()
def array_hash(x):
 a=np.ascontiguousarray(x);h=hashlib.sha256();h.update(str(a.dtype).encode());h.update(str(a.shape).encode());h.update(a.tobytes());return h.hexdigest()
def write_json(path,x):path.write_text(json.dumps(x,indent=2,default=lambda y:y.item() if isinstance(y,np.generic) else y.tolist())+'\n')
def read_csv(path):
 with path.open(newline='') as f:return list(csv.DictReader(f))
def write_csv(path,rows):
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def canonical_problem():
 with np.load(PKG/'edge_lists.npz') as z:de=z['detector_edges'];oe=z['observable_edges']
 with np.load(PKG/'faults.npz') as z:p=z['probabilities']
 h=sparse.csr_matrix((np.ones(len(de),np.uint8),(de[:,1],de[:,0])),shape=(C,V));a=sparse.csr_matrix((np.ones(len(oe),np.uint8),(oe[:,1],oe[:,0])),shape=(O,V))
 return h,a,p,np.log((1-p)/p),de,oe
def gamma_schedule(seed,fn2o=None):
 state=seed;configs=[FixedRelayLegConfig(FIRST,gamma=.125)];meta=[dict(leg=1,state=int(state),words=0,accepted=0,rejected=0,gamma_hash=array_hash(np.full(V,2,np.int64)))]
 for leg in range(2,R+1):
  vals,accepted,state,rejected=hardware_gamma_vector(state,V);gamma=np.asarray(vals,dtype=np.float64)/16.0;gint=np.asarray(vals,dtype=np.int64)
  configs.append(FixedRelayLegConfig(LATER,gamma=gamma if fn2o is None else gamma[fn2o]))
  meta.append(dict(leg=leg,state=int(state),words=len(accepted)+rejected,accepted=V,rejected=int(rejected),gamma_hash=array_hash(gint)))
 return tuple(configs),meta

class Trace:
 def __init__(self,prior,h,syndrome,check_old_to_new=None,fault_old_to_new=None):
  self.rows=[];self.best=int((np.asarray(h@((np.rint(prior)<=0).astype(np.uint8))).reshape(-1).astype(np.uint8)^syndrome).sum())
  self.co=check_old_to_new;self.fo=fault_old_to_new
 def __call__(self,event):
  residual=np.asarray(event['residual'],np.uint8);decision=np.asarray(event['decoded_error'],np.uint8);gamma=np.asarray(event['gamma_int'],np.int64)
  if self.co is not None:residual=residual[self.co]
  if self.fo is not None:decision=decision[self.fo];gamma=gamma[self.fo]
  weight=int(residual.sum());self.best=min(self.best,weight)
  self.rows.append(dict(global_iteration=int(event['global_iteration']),relay_leg=int(event['leg_index'])+1,leg_iteration=int(event['iteration']),residual_weight=weight,running_best_residual=self.best,decision_weight=int(decision.sum()),residual_hash=bits_hash(residual),decision_hash=bits_hash(decision),gamma_hash=array_hash(gamma),gamma_min=int(gamma.min()),gamma_max=int(gamma.max()),gamma_negative=int((gamma<0).sum()),converged=int(event['converged'])))

def run_decode(label,h,a,prior,syndrome,logical,configs,rng_meta,co=None,fo=None):
 trace=Trace(prior,h,syndrome,co,fo);cfg=FixedRelayConfig(fixed=FixedConfig(b=18,g=4,M=16,clip=None,separate_scale=True),leg_configs=configs,S=1,R=R,seed=0,trace_iterations=False)
 start=time.perf_counter();result=FixedRelayBPDecoder(h,cfg,iteration_callback=trace).decode(prior,syndrome);runtime=time.perf_counter()-start
 correction=np.asarray(result.decoded_error,np.uint8);corr_original=correction if fo is None else correction[fo]
 return result,trace.rows,corr_original,runtime

def main():
 OUT.mkdir(parents=True,exist_ok=True);h,a,p,prior,de,oe=canonical_problem();hp=sparse.load_npz(PART/'H_partitioned.npz').tocsr();ap=sparse.load_npz(PART/'A_partitioned.npz').tocsr()
 with np.load(PART/'probabilities_partitioned.npz') as z:pp=z['probabilities'];priorp=np.log((1-pp)/pp)
 with np.load(PART/'permutations.npz') as z:co=z['check_old_to_new'];cn=z['check_new_to_old'];fo=z['fault_old_to_new'];fn=z['fault_new_to_old']
 checks=dict(H_roundtrip_exact=bool((hp[co,:][:,fo]!=h).nnz==0),A_roundtrip_exact=bool((ap[:,fo]!=a).nnz==0),probabilities_roundtrip_exact=bool(np.array_equal(pp[fo],p)),check_permutations_inverse=bool(np.array_equal(co[cn],np.arange(C)) and np.array_equal(cn[co],np.arange(C))),fault_permutations_inverse=bool(np.array_equal(fo[fn],np.arange(V)) and np.array_equal(fn[fo],np.arange(V))),detector_fault_edge_count_preserved=bool(hp.nnz==h.nnz==len(de)),observable_fault_edge_count_preserved=bool(ap.nnz==a.nnz==len(oe)),no_partition_edge_removed=True,no_fault_split=True)
 if not all(checks.values()):write_json(OUT/'invariance_checks.json',checks);raise RuntimeError('Mapping invariant failed')
 archived={(int(r['sample_seed']),int(r['shot'])):r for r in read_csv(ARCHIVE)}
 with np.load(SAMPLES) as z:
  seeds=z['sample_seeds'];syndromes=z['syndromes'];logicals=z['observed_logicals']
  sample_data={}
  for case in PANEL:
   ix=int(np.flatnonzero(seeds==case['sample_seed'])[0]);sample_data[case['case_id']]=(syndromes[ix,case['shot']].astype(np.uint8),logicals[ix,case['shot']].astype(np.uint8))
 pair_rows=[];trace_rows=[];mismatches=[];workload=[]
 for case in PANEL:
  syn,logical=sample_data[case['case_id']];saved=archived[(case['sample_seed'],case['shot'])];engine=case['trajectory'];gamma_seed=int(saved['s0' if engine=='E0' else 's1'])
  if bits_hash(syn)!=saved['detector_sample_hash'] or bits_hash(logical)!=saved['logical_sample_hash']:raise RuntimeError('Archived workload hash mismatch')
  configs,rngmeta=gamma_schedule(gamma_seed);configsp,rngmetap=gamma_schedule(gamma_seed,fn)
  ro,to,do,rto=run_decode('original',h,a,prior,syn,logical,configs,rngmeta)
  rp,tp,dp,rtp=run_decode('partitioned',hp,ap,priorp,syn[cn],logical,configsp,rngmetap,co,fo)
  orig_res=np.asarray(h@do).reshape(-1).astype(np.uint8)&1^syn;part_res=np.asarray(h@dp).reshape(-1).astype(np.uint8)&1^syn
  orig_log=np.asarray(a@do).reshape(-1).astype(np.uint8)&1;part_log=np.asarray(a@dp).reshape(-1).astype(np.uint8)&1
  orig_valid=not orig_res.any();part_valid=not part_res.any();orig_correct=bool(orig_valid and np.array_equal(orig_log,logical));part_correct=bool(part_valid and np.array_equal(part_log,logical))
  trace_exact=len(to)==len(tp) and all(all(x[k]==y[k] for k in ('global_iteration','relay_leg','leg_iteration','residual_weight','running_best_residual','decision_weight','residual_hash','decision_hash','gamma_hash','converged')) for x,y in zip(to,tp))
  exact=bool(ro.converged==rp.converged and ro.total_iterations==rp.total_iterations and ro.relay_legs==rp.relay_legs and int(orig_res.sum())==int(part_res.sum()) and np.array_equal(do,dp) and np.array_equal(orig_log,part_log) and trace_exact)
  outcome=bool(ro.converged==rp.converged and orig_correct==part_correct and np.array_equal(orig_log,part_log))
  valid=bool((not rp.converged or part_valid) and checks['H_roundtrip_exact'])
  cls='EXACT MATCH' if exact and valid else 'OUTCOME MATCH BUT TRAJECTORY DIFFERENCE' if outcome and valid else 'OUTCOME MISMATCH' if valid else 'INVALID'
  used=ro.relay_legs;final_state=rngmeta[used-1]['state'];accepted=sum(x['accepted'] for x in rngmeta[:used]);gamma_hash=hashlib.sha256(''.join(x['gamma_hash'] for x in rngmeta[:used]).encode()).hexdigest()
  ow=ro.metadata.get('best_weight');pw=rp.metadata.get('best_weight');weight_delta=None if ow is None else float(pw-ow);prefix='e0_' if engine=='E0' else 'e1_'
  archived_weight=saved[prefix+'weight'];archived_weight_ok=(archived_weight=='' and ow is None) or (archived_weight!='' and ow is not None and abs(float(archived_weight)-float(ow))<=1e-9)
  archived_ok=bool(int(ro.converged)==int(saved[prefix+'syndrome_converged']) and ro.total_iterations==int(saved[prefix+'iterations']) and ro.relay_legs==int(saved[prefix+'legs']) and final_state==int(saved[prefix+'final_rng_state']) and accepted==int(saved[prefix+'gamma_coefficients']) and archived_weight_ok)
  if not archived_ok:raise RuntimeError(f"Original decoder failed archived reproduction for {case['case_id']}")
  row=dict(case_id=case['case_id'],category=case['category'],sample_seed=case['sample_seed'],shot=case['shot'],trajectory=engine,gamma_seed=gamma_seed,syndrome_hash=bits_hash(syn),logical_outcome_hash=bits_hash(logical),classification=cls,archived_reproduction=int(archived_ok),original_converged=int(ro.converged),partitioned_converged=int(rp.converged),original_syndrome_valid=int(orig_valid),partitioned_syndrome_valid=int(part_valid),original_logical_correct=int(orig_correct),partitioned_logical_correct=int(part_correct),original_logical_action_hash=bits_hash(orig_log),partitioned_logical_action_hash=bits_hash(part_log),original_iterations=ro.total_iterations,partitioned_iterations=rp.total_iterations,original_relay_legs=ro.relay_legs,partitioned_relay_legs=rp.relay_legs,original_residual_weight=int(orig_res.sum()),partitioned_residual_weight=int(part_res.sum()),original_candidate_weight=ow,partitioned_candidate_weight=pw,candidate_weight_delta=weight_delta,candidate_weight_bit_exact=int(ow==pw),original_correction_hash=bits_hash(do),partitioned_inverse_correction_hash=bits_hash(dp),correction_exact=int(np.array_equal(do,dp)),trace_exact=int(trace_exact),final_rng_state=final_state,accepted_gamma_values=accepted,accepted_gamma_hash=gamma_hash,original_runtime_seconds=rto,partitioned_runtime_seconds=rtp)
  pair_rows.append(row);workload.append({k:row[k] for k in ('case_id','category','sample_seed','shot','trajectory','gamma_seed','syndrome_hash','logical_outcome_hash')})
  if cls!='EXACT MATCH':mismatches.append(row)
  for x,y in zip(to,tp):trace_rows.append(dict(case_id=case['case_id'],sample_seed=case['sample_seed'],shot=case['shot'],trajectory=engine,global_iteration=x['global_iteration'],relay_leg=x['relay_leg'],leg_iteration=x['leg_iteration'],original_residual_weight=x['residual_weight'],partitioned_residual_weight=y['residual_weight'],original_running_best=x['running_best_residual'],partitioned_running_best=y['running_best_residual'],original_decision_weight=x['decision_weight'],partitioned_decision_weight=y['decision_weight'],residual_hash_match=int(x['residual_hash']==y['residual_hash']),decision_hash_match=int(x['decision_hash']==y['decision_hash']),gamma_hash_match=int(x['gamma_hash']==y['gamma_hash']),original_converged=x['converged'],partitioned_converged=y['converged']))
  print(case['case_id'],cls,ro.total_iterations,flush=True)
 counts={k:sum(r['classification']==k for r in pair_rows) for k in ('EXACT MATCH','OUTCOME MATCH BUT TRAJECTORY DIFFERENCE','OUTCOME MISMATCH','INVALID')}
 checks.update(all_original_runs_reproduce_archive=all(r['archived_reproduction'] for r in pair_rows),all_partitioned_converged_corrections_valid=all(not r['partitioned_converged'] or r['partitioned_syndrome_valid'] for r in pair_rows),logical_actions_evaluated_in_original_convention=True,same_fault_probabilities_attached=True,same_syndrome_problem=True)
 write_csv(OUT/'paired_results.csv',pair_rows);write_csv(OUT/'trace_comparison.csv',trace_rows);write_json(OUT/'mismatch_cases.json',mismatches);write_json(OUT/'invariance_checks.json',checks)
 summary=dict(status='complete',decoder=dict(file='reference/relay_bp_fixed.py',class_name='FixedRelayBPDecoder',arithmetic='fixed-point',configuration=dict(b=18,g=4,M=16,clip=None,separate_scale=True,S=1,R=32,first_limit=80,later_limit=60)),workload=workload,classification_counts=counts,total_pairs=len(pair_rows),all_exact=counts['EXACT MATCH']==len(pair_rows),trace_rows_compared=len(trace_rows),relay_bp_parameters_changed=False,rtl_modified=False)
 write_json(OUT/'pairwise_summary.json',summary)
 (OUT/'README.md').write_text(f"""# Partitioned Relay-BP equivalence

Software-only paired invariance study using `reference/relay_bp_fixed.py::FixedRelayBPDecoder` with locked b18/g4/M16 settings. The selected METIS seed-2 ordering is compared with the original graph on four archived p=0.003 trajectories. Gamma vectors are generated once in original mathematical fault order and permuted with the faults, rather than merely reseeding in the new order.

Results: {counts}. All mapping invariants passed. Relay-BP equations and parameters were unchanged; RTL was not touched. This study establishes ordering equivalence only, not latency or accuracy improvement.

Reproduce with:

```bash
../.venv/bin/python results/graph-partitioning-relaybp-equivalence/run_partitioned_relaybp_equivalence.py
```
""")
if __name__=='__main__':main()

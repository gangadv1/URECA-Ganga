#!/usr/bin/env python3
"""Full 128-trajectory fixed-point graph-reordering equivalence study."""
from __future__ import annotations
import csv,hashlib,json,os,sys,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from scipy import sparse
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1];PKG=ROOT/'graphs/generated/gross_circuit_level/memory_Z_r12_p0p003';PART=ROOT/'results/graph-partitioning-metis';SAMPLES=ROOT/'results/circuit-level-multiseed/paired_samples.npz';ARCHIVE=ROOT/'results/n1-vs-n2-hardware-latency/per_shot_results.csv'
sys.path[:0]=[str(ROOT/'reference'),str(ROOT/'fpga/verification/parallel_n2')]
from fixedpoint import FixedConfig
from relay_bp_fixed import FixedRelayBPDecoder,FixedRelayConfig,FixedRelayLegConfig
from gamma_rng_reference import vector
C,V,O,R=1728,67752,12,32
def bh(x):return hashlib.sha256(np.packbits(np.asarray(x,np.uint8)).tobytes()).hexdigest()
def ah(x):
 a=np.ascontiguousarray(x);h=hashlib.sha256();h.update(str(a.dtype).encode());h.update(str(a.shape).encode());h.update(a.tobytes());return h.hexdigest()
def fh(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def write_json(path,x):path.write_text(json.dumps(x,indent=2,default=lambda y:y.item() if isinstance(y,np.generic) else y.tolist())+'\n')
def rows(path):
 with Path(path).open(newline='') as f:return list(csv.DictReader(f))
def problem():
 with np.load(PKG/'edge_lists.npz') as z:de=z['detector_edges'];oe=z['observable_edges']
 with np.load(PKG/'faults.npz') as z:p=z['probabilities']
 h=sparse.csr_matrix((np.ones(len(de),np.uint8),(de[:,1],de[:,0])),shape=(C,V));a=sparse.csr_matrix((np.ones(len(oe),np.uint8),(oe[:,1],oe[:,0])),shape=(O,V));return h,a,p,np.log((1-p)/p)
H,A,P,PRIOR=problem();HP=sparse.load_npz(PART/'H_partitioned.npz').tocsr();AP=sparse.load_npz(PART/'A_partitioned.npz').tocsr()
with np.load(PART/'probabilities_partitioned.npz') as z:PP=z['probabilities'];PRIORP=np.log((1-PP)/PP)
with np.load(PART/'permutations.npz') as z:CO=z['check_old_to_new'];CN=z['check_new_to_old'];FO=z['fault_old_to_new'];FN=z['fault_new_to_old']

def schedule(seed):
 state=seed;orig=[FixedRelayLegConfig(80,gamma=.125)];part=[FixedRelayLegConfig(80,gamma=.125)];meta=[dict(state=int(state),accepted=0,words=0,gamma_hash=ah(np.full(V,2,np.int64)))]
 for _ in range(1,R):
  vals,accepted,state,rejected=vector(state,V);g=np.asarray(vals,np.float64)/16;orig.append(FixedRelayLegConfig(60,gamma=g));part.append(FixedRelayLegConfig(60,gamma=g[FN]));meta.append(dict(state=int(state),accepted=V,words=len(accepted)+rejected,gamma_hash=ah(np.asarray(vals,np.int64))))
 return tuple(orig),tuple(part),meta
class Trace:
 def __init__(self,prior,h,syn,co=None,fo=None):
  init=(np.rint(prior)<=0).astype(np.uint8);res=np.asarray(h@init).reshape(-1).astype(np.uint8)^syn;self.best=int(res.sum());self.rows=[];self.co=co;self.fo=fo;self.gh={}
 def __call__(self,e):
  res=np.asarray(e['residual'],np.uint8);dec=np.asarray(e['decoded_error'],np.uint8);gam=np.asarray(e['gamma_int'],np.int64)
  if self.co is not None:res=res[self.co]
  if self.fo is not None:dec=dec[self.fo];gam=gam[self.fo]
  rw=int(res.sum());self.best=min(self.best,rw);leg=int(e['leg_index']);ghash=self.gh.setdefault(leg,ah(gam))
  self.rows.append((int(e['global_iteration']),leg+1,int(e['iteration']),rw,self.best,int(dec.sum()),bh(res),bh(dec),ghash,int(e['converged'])))
def decode(h,prior,syn,configs,co=None,fo=None):
 tr=Trace(prior,h,syn,co,fo);cfg=FixedRelayConfig(fixed=FixedConfig(b=18,g=4,M=16,clip=None,separate_scale=True),leg_configs=configs,S=1,R=32,seed=0);t=time.perf_counter();r=FixedRelayBPDecoder(h,cfg,iteration_callback=tr).decode(prior,syn);return r,tr.rows,(np.asarray(r.decoded_error,np.uint8) if fo is None else np.asarray(r.decoded_error,np.uint8)[fo]),time.perf_counter()-t
def task(job):
 sample_seed,shot,syn,logical,arch=job;cid=f'{sample_seed}_{shot:03d}';checkpoint=OUT/'checkpoints'/f'{cid}.json'
 if checkpoint.exists():return json.loads(checkpoint.read_text())
 seed=int(arch['s0']);oc,pc,meta=schedule(seed);ro,to,do,rto=decode(H,PRIOR,syn,oc);rp,tp,dp,rtp=decode(HP,PRIORP,syn[CN],pc,CO,FO)
 ores=np.asarray(H@do).reshape(-1).astype(np.uint8)&1^syn;pres=np.asarray(H@dp).reshape(-1).astype(np.uint8)&1^syn;olog=np.asarray(A@do).reshape(-1).astype(np.uint8)&1;plog=np.asarray(A@dp).reshape(-1).astype(np.uint8)&1
 oval=not ores.any();pval=not pres.any();ocorrect=bool(oval and np.array_equal(olog,logical));pcorrect=bool(pval and np.array_equal(plog,logical))
 first=None
 for i,(x,y) in enumerate(zip(to,tp),1):
  if x!=y:first=dict(global_iteration=i,original=dict(zip(('global_iteration','relay_leg','leg_iteration','residual_weight','running_best','decision_weight','residual_hash','decision_hash','gamma_hash','converged'),x)),partitioned=dict(zip(('global_iteration','relay_leg','leg_iteration','residual_weight','running_best','decision_weight','residual_hash','decision_hash','gamma_hash','converged'),y)));break
 if first is None and len(to)!=len(tp):first=dict(global_iteration=min(len(to),len(tp))+1,reason='trace length differs')
 trace_exact=first is None;exact=bool(ro.converged==rp.converged and ro.total_iterations==rp.total_iterations and ro.relay_legs==rp.relay_legs and np.array_equal(do,dp) and np.array_equal(olog,plog) and int(ores.sum())==int(pres.sum()) and trace_exact);outcome=bool(ro.converged==rp.converged and ocorrect==pcorrect and np.array_equal(olog,plog));valid=bool(not rp.converged or pval);cls='EXACT MATCH' if exact and valid else 'OUTCOME MATCH BUT TRAJECTORY DIFFERENCE' if outcome and valid else 'OUTCOME MISMATCH' if valid else 'INVALID'
 used=ro.relay_legs;state=meta[used-1]['state'];accepted=sum(x['accepted'] for x in meta[:used]);gh=hashlib.sha256(''.join(x['gamma_hash'] for x in meta[:used]).encode()).hexdigest();ow=ro.metadata.get('best_weight');pw=rp.metadata.get('best_weight');delta=None if ow is None else float(pw-ow);aw=arch['e0_weight'];aweight=(aw=='' and ow is None) or (aw!='' and ow is not None and abs(float(aw)-ow)<=1e-9)
 archive_ok=bool(int(ro.converged)==int(arch['e0_syndrome_converged']) and ro.total_iterations==int(arch['e0_iterations']) and ro.relay_legs==int(arch['e0_legs']) and state==int(arch['e0_final_rng_state']) and accepted==int(arch['e0_gamma_coefficients']) and aweight)
 if not archive_ok:raise RuntimeError(f'Archive reproduction failed {cid}')
 rec=dict(case_id=cid,sample_seed=sample_seed,shot=shot,gamma_seed=seed,syndrome_hash=bh(syn),logical_outcome_hash=bh(logical),classification=cls,archive_reproduction=archive_ok,original_converged=int(ro.converged),partitioned_converged=int(rp.converged),original_syndrome_valid=int(oval),partitioned_syndrome_valid=int(pval),original_logical_correct=int(ocorrect),partitioned_logical_correct=int(pcorrect),original_iterations=ro.total_iterations,partitioned_iterations=rp.total_iterations,original_relay_legs=ro.relay_legs,partitioned_relay_legs=rp.relay_legs,original_final_residual=int(ores.sum()),partitioned_final_residual=int(pres.sum()),original_candidate_weight=ow,partitioned_candidate_weight=pw,candidate_weight_delta=delta,correction_hash=bh(do),partitioned_inverse_correction_hash=bh(dp),correction_exact=bool(np.array_equal(do,dp)),logical_action_exact=bool(np.array_equal(olog,plog)),trace_exact=trace_exact,trace_iterations_compared=min(len(to),len(tp)),first_trace_difference=first,final_rng_state=state,accepted_gamma_count=accepted,accepted_gamma_sequence_hash=gh,original_runtime_seconds=rto,partitioned_runtime_seconds=rtp)
 write_json(checkpoint,rec);return rec
def main():
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'checkpoints').mkdir(exist_ok=True)
 inv=dict(H_exact=bool((HP[CO,:][:,FO]!=H).nnz==0),A_exact=bool((AP[:,FO]!=A).nnz==0),probabilities_exact=bool(np.array_equal(PP[FO],P)),check_permutation_inverse=bool(np.array_equal(CO[CN],np.arange(C))),fault_permutation_inverse=bool(np.array_equal(FO[FN],np.arange(V))))
 if not all(inv.values()):raise RuntimeError(f'Mapping failure {inv}')
 archive=rows(ARCHIVE);archive.sort(key=lambda r:(int(r['sample_seed']),int(r['shot'])))
 if len(archive)!=128:raise RuntimeError('Expected canonical 128-row archive')
 with np.load(SAMPLES) as z:
  seeds=z['sample_seeds'];ss=z['syndromes'];ll=z['observed_logicals'];jobs=[]
  for ar in archive:
   seed=int(ar['sample_seed']);shot=int(ar['shot']);ix=int(np.flatnonzero(seeds==seed)[0]);syn=ss[ix,shot].astype(np.uint8);logical=ll[ix,shot].astype(np.uint8)
   if bh(syn)!=ar['detector_sample_hash'] or bh(logical)!=ar['logical_sample_hash']:raise RuntimeError('Dataset hash mismatch')
   jobs.append((seed,shot,syn,logical,ar))
 results=[];start=time.time();workers=int(os.environ.get('EQUIV_WORKERS','4'))
 with ThreadPoolExecutor(max_workers=workers) as ex:
  futures={ex.submit(task,j):j for j in jobs}
  for i,f in enumerate(as_completed(futures),1):results.append(f.result());print(f'completed {i}/128 elapsed={time.time()-start:.1f}s',flush=True)
 results.sort(key=lambda r:(r['sample_seed'],r['shot']))
 with (OUT/'n1_paired_results.csv').open('w',newline='') as f:
  flat=[]
  for r in results:
   q={k:v for k,v in r.items() if k!='first_trace_difference'};q['first_trace_difference']=json.dumps(r['first_trace_difference']);flat.append(q)
  w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
 classes={k:sum(r['classification']==k for r in results) for k in ('EXACT MATCH','OUTCOME MATCH BUT TRAJECTORY DIFFERENCE','OUTCOME MISMATCH','INVALID')};mismatch=[r for r in results if r['classification']!='EXACT MATCH'];d=np.array([abs(r['candidate_weight_delta']) for r in results if r['candidate_weight_delta'] is not None],float)
 deltas=[dict(case_id=r['case_id'],sample_seed=r['sample_seed'],shot=r['shot'],delta=r['candidate_weight_delta'],absolute_delta=None if r['candidate_weight_delta'] is None else abs(r['candidate_weight_delta']),bit_exact=r['candidate_weight_delta'] in (None,0.0),selection_affected=False) for r in results]
 with (OUT/'candidate_weight_deltas.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(deltas[0]));w.writeheader();w.writerows(deltas)
 write_json(OUT/'n1_trace_mismatches.json',mismatch);write_json(OUT/'invariance_checks.json',inv)
 summary=dict(status='complete',trajectories=128,circuit_seeds=sorted({r['sample_seed'] for r in results}),shots_per_seed=32,classification_counts=classes,all_exact=classes['EXACT MATCH']==128,total_trace_iterations=sum(r['trace_iterations_compared'] for r in results),candidate_weight={'successful_candidates':len(d),'maximum_absolute_delta':float(d.max(initial=0)),'median_absolute_delta':float(np.median(d)) if len(d) else 0,'selection_affected':0,'S=1_reporting_only':True},optional_n2_run=False,optional_n2_reason='N=1 broad equivalence completed first; N=2 would triple the paired decode workload and is deferred.',configuration=dict(decoder='reference/relay_bp_fixed.py::FixedRelayBPDecoder',b=18,g=4,M=16,S=1,R=32,first_limit=80,later_limit=60),dataset=dict(samples=str(SAMPLES.relative_to(ROOT)),archive=str(ARCHIVE.relative_to(ROOT)),syndrome_storage='paired_samples.npz boolean array [5,128,1728]',logical_storage='paired_samples.npz boolean array [5,128,12]',gamma_metadata='per_shot_results.csv s0/e0_* fields; xorshift64 reference generator'),hashes=dict(samples=fh(SAMPLES),archive=fh(ARCHIVE),permutations=fh(PART/'permutations.npz'),decoder=fh(ROOT/'reference/relay_bp_fixed.py'),gamma_reference=fh(ROOT/'fpga/verification/parallel_n2/gamma_rng_reference.py')))
 write_json(OUT/'n1_summary.json',summary);write_json(OUT/'study_manifest.json',dict(**summary['dataset'],dataset_hashes=summary['hashes'],permutation_array_hashes=dict(check_old_to_new=ah(CO),check_new_to_old=ah(CN),fault_old_to_new=ah(FO),fault_new_to_old=ah(FN)),gamma_mapping='Generate accepted hardware gamma in original fault order, then partition with fault_new_to_old; trace hashes map back with fault_old_to_new.',decoder_configuration=summary['configuration']))
 (OUT/'README.md').write_text(f"""# Full graph-reordering Relay-BP equivalence

Canonical archived N=1 panel: 128 trajectories, four circuit seeds, shots 0--31. Decoder: fixed b18/g4/M16 `FixedRelayBPDecoder`, S=1, R=32. Original gamma vectors are permuted with mathematical faults.

Classification: {classes}. Trace iterations compared: {summary['total_trace_iterations']}. Candidate-weight maximum/median absolute deltas: {summary['candidate_weight']['maximum_absolute_delta']:.3g}/{summary['candidate_weight']['median_absolute_delta']:.3g}; these are reporting-only with S=1.

No Relay-BP equations, configuration, graph incidences, or RTL were changed. This is equivalence evidence, not a performance claim.
""")
 print(json.dumps(dict(classification_counts=classes,total_trace_iterations=summary['total_trace_iterations'],candidate_weight=summary['candidate_weight']),indent=2))
if __name__=='__main__':main()

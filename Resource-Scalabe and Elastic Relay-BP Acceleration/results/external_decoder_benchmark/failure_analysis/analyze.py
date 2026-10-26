"""Read-only archive audit plus one bounded, unchanged-config OSD0 repeat."""
from pathlib import Path
import csv, json, hashlib, sys, multiprocessing as mp, importlib.util
import numpy as np
BASE=Path(__file__).resolve().parents[1]; ROOT=BASE.parents[1]; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
import run_benchmark as bench
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(name,data): (OUT/name).write_text(json.dumps(data,indent=2)+'\n')
def main():
 before={str(p.relative_to(ROOT)):sha(p) for p in BASE.rglob('*') if p.is_file() and OUT not in p.parents}
 protected=json.loads((BASE/'protected_hashes.json').read_text())
 assert all(sha(ROOT/p)==v for p,v in protected.items())
 _,_,_,_,h,a,_=bench.tb.load_problem(bench.tb.Config(code='144_12_12',physical_p=.003,shots=1))
 pkg=ROOT/'graphs/generated/gross_circuit_level/memory_Z_r12_p0p003'
 with np.load(pkg/'faults.npz') as d: prob=d['probabilities'].copy()
 canonical=bench.readcsv(ROOT/'results/n-scaling-canonical/per_shot_results.csv')
 with np.load(ROOT/'results/circuit-level-multiseed/paired_samples.npz') as d:
  ss=d['syndromes'].copy(); ll=d['observed_logicals'].copy(); seeds=d['sample_seeds'].copy()
 inputs={}
 for i in json.loads((BASE/'paired_indices.json').read_text()):
  r=canonical[i]; j=int(np.flatnonzero(seeds==int(r['sample_seed']))[0]); s=ss[j,int(r['shot'])].astype(np.uint8); l=ll[j,int(r['shot'])].astype(np.uint8)
  assert hashlib.sha256(np.packbits(s).tobytes()).hexdigest()==r['detector_sample_hash']
  assert hashlib.sha256(np.packbits(l).tobytes()).hexdigest()==r['logical_sample_hash']
  inputs[i]=(s,l)
 external={m:{r['index']:r for r in json.loads((BASE/f'{m}_results.json').read_text())} for m in ('BP','BP_OSD0')}
 relay={(r['N'],r['index']):r for r in json.loads((BASE/'Relay_archived_records.json').read_text())}
 for m in external:
  with np.load(BASE/f'{m}_predictions.npz') as d:
   for i,e in zip(d['canonical_indices'],d['predicted_faults']):
    r=external[m][int(i)]; score=bench.tb.score(h,a,e,*inputs[int(i)])
    assert all(score[k]==r[k] for k in score)
    assert hashlib.sha256(e.tobytes()).hexdigest()==r['decision_sha256']
    if m=='BP_OSD0' and i==36: old=e.copy()
 rows=[]; syndromes=[]
 for i,(s,l) in inputs.items():
  r=canonical[i]; row=dict(canonical_index=i,sample_seed=int(r['sample_seed']),shot=int(r['shot']),syndrome_detector_count=len(s),syndrome_weight=int(s.sum()),syndrome_sha256=r['detector_sample_hash'],syndrome_one_indices=json.dumps(np.flatnonzero(s).tolist()))
  failed=[]
  for m in external:
   x=external[m][i]; category='nonconvergence' if x['nonconvergence'] else 'syndrome-valid logical error' if x['syndrome_valid_logical_error'] else 'success'
   row.update({m+'_outcome':category,m+'_bp_iterations':x['bp_iterations'],m+'_bp_converged':x['bp_converged'],m+'_osd_fallback':x['osd_fallback']})
   if x['total_failure']: failed.append(m)
  for n in (1,2,4,8):
   x=relay[n,i]; category='nonconvergence' if x['nonconvergence'] else 'syndrome-valid logical error' if x['syndrome_valid_logical_error'] else 'success'
   row.update({f'Relay_N{n}_outcome':category,f'Relay_N{n}_per_engine_iterations':json.dumps(x['iterations']),f'Relay_N{n}_per_engine_legs':json.dumps(x['legs']),f'Relay_N{n}_winner':x['winner']})
   if not x['logical_correct']: failed.append(f'Relay_N{n}')
  row['failed_decoders']=';'.join(failed); row['multiple_final_failures']=len(failed)>1; rows.append(row)
 with (OUT/'sample_comparison.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 dump('sample_comparison.json',rows)
 # Only index 36 is decoded. Labels and logical matrix stay in the parent.
 ctx=mp.get_context('spawn'); parent,child=ctx.Pipe(); process=ctx.Process(target=bench.worker,args=(child,h,prob,'BP_OSD0'));process.start();child.close()
 try:
  if not parent.poll(10): raise TimeoutError('10s initialization cap')
  ready=parent.recv(); assert ready.get('ready'),ready
  parent.send(inputs[36][0])
  if not parent.poll(10): raise TimeoutError('10s single decode cap')
  result=parent.recv(); assert 'decision' in result,result
  e=result.pop('decision'); score=bench.tb.score(h,a,e,*inputs[36]); expected=external['BP_OSD0'][36]
  result.update(score); result.update(canonical_index=36,sample_seed=20260810,shot=4,configuration_changes=[],fresh_decoder_instance=True,decision_identical_to_archive=bool(np.array_equal(e,old)),decision_sha256=hashlib.sha256(e.tobytes()).hexdigest(),syndrome_residual_weight=int(((np.asarray(h@e).ravel()&1)^inputs[36][0]).sum()),observed_logicals=inputs[36][1].tolist(),predicted_logicals=(np.asarray(a@e).ravel()&1).tolist(),logical_mismatch_indices=np.flatnonzero((np.asarray(a@e).ravel()&1)^inputs[36][1]).tolist(),initialization=ready)
  assert result['decision_identical_to_archive'] and result['bp_iterations']==expected['bp_iterations'] and result['syndrome_valid_logical_error']==1
  dump('single_sample_reproduction.json',result)
 finally:
  if process.is_alive():process.terminate()
  process.join(5);parent.close()
 assert all(sha(ROOT/p)==v for p,v in before.items())
 assert all(sha(ROOT/p)==v for p,v in protected.items())
 dump('validation.json',dict(status='PASS',paired_samples=58,external_predictions_rescored=116,canonical_sample_hashes_checked=58,single_sample_reproduction_index=36,existing_benchmark_files_unchanged=len(before),protected_archive_files_unchanged=len(protected),Relay_rerun=False))
 dump('provenance.json',dict(command='OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ../.venv/bin/python -B results/external_decoder_benchmark/failure_analysis/analyze.py',analysis_sha256=sha(__file__),existing_benchmark_hashes=before,protected_archive_hashes=protected,dependency_versions=json.loads((BASE/'provenance.json').read_text())['versions'],limits=dict(initialization_seconds=10,single_decode_seconds=10),configuration_changes=[]))
 print(json.dumps(result,indent=2));print('PASS: all 58 paired samples audited; only OSD0 sample 36 rerun.')
if __name__=='__main__':main()

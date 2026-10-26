"""Paired external decoding only; canonical Relay-BP results are read, never rerun."""
from pathlib import Path
import csv,json,hashlib,time,sys,os,platform,multiprocessing as mp,importlib.metadata as metadata
import numpy as np
from scipy import sparse
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"simulations/configurable_testbench"))
import testbench as tb
MAX_ITER=1940;METHODS=("BP","BP_OSD0")
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,default=lambda v:v.tolist() if isinstance(v,np.ndarray) else v.item())+"\n")
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def readcsv(p):
 with Path(p).open() as f:return list(csv.DictReader(f))
def worker(pipe,h,probabilities,method):
 import ldpc
 try:
  start=time.perf_counter()
  kw=dict(error_channel=probabilities.tolist(),max_iter=MAX_ITER,bp_method="minimum_sum",ms_scaling_factor=1.,schedule="parallel",omp_thread_count=1,random_schedule_seed=1,random_serial_schedule=False,input_vector_type="syndrome")
  if method=="BP_OSD0":
   kw.pop("random_serial_schedule") # BpOsd constructor rejects this keyword; inherited default is False.
   kw.update(osd_method="OSD_0",osd_order=0)
  cls=ldpc.BpDecoder if method=="BP" else ldpc.BpOsdDecoder
  decoder=cls(h,**kw)
  if not np.array_equal(np.asarray(decoder.error_channel),probabilities):raise ValueError("Channel probability mismatch")
  pipe.send(dict(ready=True,initialization_seconds=time.perf_counter()-start,configuration=kw|{"error_channel":"exact package fault probabilities"}))
  while True:
   syndrome=pipe.recv()
   if syndrome is None:break
   before=time.perf_counter();decision=np.asarray(decoder.decode(syndrome.copy()),np.uint8).copy();elapsed=time.perf_counter()-before
   pipe.send(dict(decision=decision,decode_seconds=elapsed,bp_iterations=int(decoder.iter),bp_converged=bool(decoder.converge),osd_fallback=bool(method=="BP_OSD0" and not decoder.converge)))
 except Exception as e:
  pipe.send(dict(error=type(e).__name__,reason=str(e)))
 finally:pipe.close()
def main():
 if (OUT/"validation.json").exists():raise FileExistsError("Use a fresh benchmark output directory")
 protected=[ROOT/"graphs",ROOT/"reference",ROOT/"results/n-scaling-canonical",ROOT/"results/n-scaling-canonical-n8-complete",ROOT/"results/circuit-level-multiseed",ROOT/"simulations/configurable_testbench"]
 before={str(p.relative_to(ROOT)):sha(p) for d in protected for p in d.rglob("*") if p.is_file()}
 dump(OUT/"protected_hashes.json",before)
 manifest=json.loads((ROOT/"results/n-scaling-canonical/manifest.json").read_text())
 pkgdir,pkg,pmanifest,circuit,h,action,priors=tb.load_problem(tb.Config(code="144_12_12",physical_p=.003,shots=1))
 assert pkg["rounds"]==12 and pkg["memory_basis"]=="Z"
 samplefile=ROOT/"results/circuit-level-multiseed/paired_samples.npz"
 assert sha(samplefile)==manifest["hashes"]["samples"] and sha(pkgdir/"manifest.json")==manifest["hashes"]["package_manifest"]
 with np.load(pkgdir/"faults.npz") as d:probabilities=d["probabilities"].copy()
 with np.load(samplefile) as d:
  source_syndromes=d["syndromes"].copy();source_logicals=d["observed_logicals"].copy();source_seeds=d["sample_seeds"].copy()
  assert np.array_equal(d["probabilities"],probabilities)
 canonical=readcsv(ROOT/"results/n-scaling-canonical/per_shot_results.csv");assert len(canonical)==128
 syndromes=[];logicals=[];keys=set()
 for r in canonical:
  seed,shot=int(r["sample_seed"]),int(r["shot"]);index=np.flatnonzero(source_seeds==seed);assert len(index)==1
  s=source_syndromes[index[0],shot].astype(np.uint8);l=source_logicals[index[0],shot].astype(np.uint8)
  assert hashlib.sha256(np.packbits(s).tobytes()).hexdigest()==r["detector_sample_hash"]
  assert hashlib.sha256(np.packbits(l).tobytes()).hexdigest()==r["logical_sample_hash"]
  assert (seed,shot) not in keys;keys.add((seed,shot));syndromes.append(s);logicals.append(l)
 # Reconstruct every DEM column in-memory; never sample again or write packages.
 builder=tb.module("external_dem_validator",ROOT/"graphs/build_circuit_level.py")
 import stim
 dem=stim.DetectorErrorModel.from_file(str(pkgdir/"detector_error_model.dem"))
 assert str(circuit.detector_error_model(decompose_errors=False,flatten_loops=True))==str(dem)
 text_p,dr,lr,separators=builder.extract_faults(dem)
 fresh_dem=circuit.detector_error_model(decompose_errors=False,flatten_loops=True)
 p,fresh_dr,fresh_lr,_=builder.extract_faults(fresh_dem)
 assert fresh_dr==dr and fresh_lr==lr
 dump(OUT/"DEM_roundtrip_diagnostic.json",dict(serialized_probability_max_abs_difference=float(np.max(np.abs(text_p-probabilities))),serialized_probability_mismatch_count=int(np.count_nonzero(text_p!=probabilities)),source_in_memory_probabilities_binary_exact=bool(np.array_equal(p,probabilities)),decoder_priors="Original canonical faults.npz probabilities, not rounded DEM text"))
 def incidence(rows,count):
  cols=np.repeat(np.arange(len(rows)),[len(x) for x in rows]);rr=np.concatenate([np.asarray(x,int) for x in rows])
  return sparse.csr_matrix((np.ones(len(cols),np.uint8),(rr,cols)),shape=(count,len(rows)))
 assert np.array_equal(p,probabilities) and (incidence(dr,h.shape[0])!=h).nnz==0 and (incidence(lr,action.shape[0])!=action).nnz==0
 dump(OUT/"preflight.json",dict(status="PASS",dimensions=dict(detectors=h.shape[0],faults=h.shape[1],observables=action.shape[0],edges=h.nnz),canonical_unique_samples=128,seeds=sorted({int(r["sample_seed"]) for r in canonical}),shots_by_seed={str(s):sum(int(r["sample_seed"])==s for r in canonical) for s in sorted({int(r["sample_seed"]) for r in canonical})},all_sample_hashes_exact=True,DEM_H_A_probability_column_order_exact=True,source_circuit_matches_DEM=True,no_fault_merging_or_permutation=True,labels_only_used_for_scoring=True))
 print("PREFLIGHT PASS: 128 exact canonical samples and full DEM/H/A priors",flush=True)
 # Tiny API regression: non-square sparse syndrome interface, known parity solution.
 import ldpc
 toy=sparse.csr_matrix(np.array([[1,1,0],[0,1,1]],np.uint8))
 for cls in (ldpc.BpDecoder,ldpc.BpOsdDecoder):
  kw=dict(error_channel=[.01,.1,.01],max_iter=10,bp_method="minimum_sum",schedule="parallel",input_vector_type="syndrome")
  if cls==ldpc.BpOsdDecoder:kw.update(osd_method="OSD_0",osd_order=0)
  obj=cls(toy,**kw);pred=obj.decode(np.array([1,1],np.uint8));assert np.array_equal(np.asarray(toy@pred)&1,[1,1])
 ctx=mp.get_context("spawn");campaign_start=time.monotonic();all_results={};timing={};smoke={};commands=[]
 stress=int(np.argmax([int(r["e0_iterations"]) for r in canonical]));smoke_indices=[0,stress] if stress!=0 else [0,1]
 for method in METHODS:
  if method=="BP" and (OUT/"BP_results.json").exists():
   all_results[method]=json.loads((OUT/"BP_results.json").read_text())
   timing=json.loads((OUT/"timing.json").read_text())
   print("Reusing",len(all_results[method]),"cached BP samples; no BP rerun",flush=True)
   continue
  start=time.monotonic();parent,child=ctx.Pipe();process=ctx.Process(target=worker,args=(child,h,probabilities,method));process.start();child.close()
  records={};decisions={};status="COMPLETE";reason=None
  try:
   if not parent.poll(10):raise TimeoutError("10-second decoder initialization cap")
   ready=parent.recv()
   if "error" in ready:raise ValueError(ready)
   def request(index):
    remaining=min(10.,90-(time.monotonic()-start),180-(time.monotonic()-campaign_start))
    if remaining<=0:raise TimeoutError("90-second method / 180-second global cap")
    parent.send(syndromes[index])
    if not parent.poll(remaining):raise TimeoutError("10-second decode or campaign cap")
    result=parent.recv()
    if "error" in result:raise ValueError(result)
    decision=result.pop("decision");assert decision.shape==(h.shape[1],) and np.all((decision==0)|(decision==1))
    t=time.perf_counter();score=tb.score(h,action,decision,syndromes[index],logicals[index]);score_seconds=time.perf_counter()-t
    syndrome_valid=not score["nonconvergence"]
    if method=="BP" and syndrome_valid!=result["bp_converged"]:raise ValueError("BP flag and syndrome disagree")
    r=canonical[index];records[index]=dict(index=index,sample_seed=int(r["sample_seed"]),shot=int(r["shot"]),**result,**score,syndrome_valid=syndrome_valid,score_seconds=score_seconds,decision_sha256=hashlib.sha256(decision.tobytes()).hexdigest(),observable_prediction=(np.asarray(action@decision).ravel()&1).tolist())
    decisions[index]=decision
    with (OUT/f"{method}_progress.jsonl").open("a") as f:f.write(json.dumps(records[index])+"\n")
   for index in smoke_indices:request(index)
   smoke[method]=[records[i] for i in smoke_indices];dump(OUT/"smoke.json",smoke)
   projected=np.mean([records[i]["decode_seconds"] for i in smoke_indices])*128
   print(method,"smoke PASS; projected decode seconds",round(projected,2),flush=True)
   # Runtime-based scope reduction; no adjustment of decoder math or iteration budget.
   limit=min(128,max(2,int(75/max(np.mean([records[i]["decode_seconds"] for i in smoke_indices]),.001))))
   allowed=sorted(r["index"] for r in all_results["BP"]) if method=="BP_OSD0" else list(range(limit))
   for index in allowed:
    if index not in records:request(index)
   if limit<128:status="RUNTIME_SCOPE_REDUCED";reason=f"Smoke projection {projected:.2f}s exceeds reserved decoding budget; prefix limit {limit}, plus stress smoke"
   timing[method]=dict(**ready,smoke_projection_seconds=projected,requested_prefix_shots=limit,status=status,reason=reason)
  except TimeoutError as e:
   status="RUNTIME_CAPPED";reason=str(e);timing[method]=dict(status=status,reason=reason)
  finally:
   if process.is_alive():process.terminate()
   process.join(5);parent.close()
  ordered=[records[i] for i in sorted(records)];all_results[method]=ordered
  dump(OUT/f"{method}_results.json",ordered)
  if decisions:np.savez_compressed(OUT/f"{method}_predictions.npz",canonical_indices=np.array(sorted(decisions)),predicted_faults=np.stack([decisions[i] for i in sorted(decisions)]))
  timing[method].update(completed_unique_samples=len(ordered),method_elapsed_seconds=time.monotonic()-start,sum_decode_seconds=sum(r["decode_seconds"] for r in ordered))
  dump(OUT/"timing.json",timing);print(method,status,len(ordered),"samples",flush=True)
 # Strictly paired comparison on intersection, even if a decoder hit its runtime cap.
 paired_indices=sorted(set(r["index"] for r in all_results["BP"])&set(r["index"] for r in all_results["BP_OSD0"]))
 if not paired_indices:raise RuntimeError("No common successfully executed external samples")
 summaries=[];per_shot=[]
 for method in METHODS:
  rows=[r for r in all_results[method] if r["index"] in paired_indices]
  summaries.append(dict(decoder=method,shots=len(rows),logical_success=sum(not r["total_failure"] for r in rows),total_failure=sum(r["total_failure"] for r in rows),nonconvergence=sum(r["nonconvergence"] for r in rows),syndrome_valid_logical_error=sum(r["syndrome_valid_logical_error"] for r in rows),bp_nonconvergence_before_OSD=sum(not r["bp_converged"] for r in rows),osd_calls=sum(r["osd_fallback"] for r in rows),mean_iterations=float(np.mean([r["bp_iterations"] for r in rows])),max_iterations=max(r["bp_iterations"] for r in rows),decode_wall_seconds=sum(r["decode_seconds"] for r in rows),mean_software_decode_seconds=float(np.mean([r["decode_seconds"] for r in rows])),p99_software_decode_seconds=float(np.percentile([r["decode_seconds"] for r in rows],99)),mean_modeled_cycles=None,p99_modeled_cycles=None,failure_stats=tb.rate(sum(r["total_failure"] for r in rows),len(rows))))
  for r in rows:per_shot.append(dict(decoder=method,**r))
 for n in (1,2,4,8):
  rows=[canonical[i] for i in paired_indices]
  failures=sum(not int(r[f"n{n}_logical_correct"]) for r in rows)
  summaries.append(dict(decoder=f"Relay_N{n}",shots=len(rows),logical_success=len(rows)-failures,total_failure=failures,nonconvergence=sum(int(r[f"n{n}_non_convergence"]) for r in rows),syndrome_valid_logical_error=sum(int(r[f"n{n}_syndrome_valid_logical_error"]) for r in rows),bp_nonconvergence_before_OSD=None,osd_calls=None,mean_iterations=float(np.mean([int(r[f"e{int(r[f'n{n}_winner'])}_iterations"]) if int(r[f"n{n}_winner"])>=0 else max(int(r[f"e{i}_iterations"]) for i in range(n)) for r in rows])),max_iterations=None,decode_wall_seconds=None,mean_software_decode_seconds=None,p99_software_decode_seconds=None,mean_modeled_cycles=float(np.mean([int(r[f"n{n}_cycles"]) for r in rows])),p99_modeled_cycles=float(np.percentile([int(r[f"n{n}_cycles"]) for r in rows],99)),failure_stats=tb.rate(failures,len(rows))))
 dump(OUT/"comparison.json",summaries);dump(OUT/"paired_indices.json",paired_indices);dump(OUT/"per_shot_external.json",per_shot)
 with (OUT/"comparison.csv").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(summaries[0]));w.writeheader();w.writerows(summaries)
 assert all(sha(ROOT/p)==hash for p,hash in before.items())
 dump(OUT/"validation.json",dict(status="PASS",paired_samples=len(paired_indices),preflight_sample_count=128,api_smoke_pass=True,real_smoke_indices=smoke_indices,no_Relay_decoding_rerun=True,BP_results_reused_on_resume=True,Relay_scores_reused_not_raw_predictions=True,labels_decoder_inaccessible=True,archived_files_hash_identical=len(before),external_budget_max_iterations=MAX_ITER,global_wall_seconds=time.monotonic()-campaign_start))
 dump(OUT/"provenance.json",dict(versions={p:metadata.version(p) for p in ("ldpc","numpy","scipy","stim")},python=sys.version,platform=platform.platform(),processor=platform.processor(),machine=platform.machine(),hardware_timing_measured=False,implementation_sha256=sha(Path(__file__)),ldpc_source_hashes={str(p):sha(p) for p in Path(ldpc.__file__).parent.rglob("*.pyx")},input_hashes={str(p.relative_to(ROOT)):sha(p) for p in (samplefile,pkgdir/"faults.npz",pkgdir/"edge_lists.npz",pkgdir/"circuit.stim",pkgdir/"detector_error_model.dem",ROOT/"results/n-scaling-canonical/per_shot_results.csv")},sample_seeds=sorted({int(r["sample_seed"]) for r in canonical}),trajectory_seeds="Relay canonical CSV s0..s7 unchanged; external BP deterministic parallel, random schedule disabled",command="MPLCONFIGDIR=/private/tmp/relay-external-matplotlib OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 ../.venv/bin/python -B results/external_decoder_benchmark/run_benchmark.py"))
 print(json.dumps(summaries,indent=2),flush=True)
if __name__=="__main__":
 try:main()
 except Exception as e:dump(OUT/"STOPPED.json",dict(error=type(e).__name__,reason=str(e)));raise

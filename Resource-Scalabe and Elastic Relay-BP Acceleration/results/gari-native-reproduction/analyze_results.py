"""Account for every native batch and generate the reproduction report.
Run with /tmp/gari-native-py311/bin/python3 after native process completion.
"""
from pathlib import Path
import csv,json,hashlib,math,shutil,subprocess,collections
import numpy as np
import sinter
OUT=Path(__file__).resolve().parent
RUN=OUT/'python311'
REPO=Path('/tmp/gari-native-6380d52')

def dump(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2)+'\n')
def csvwrite(name,rows):
 with (OUT/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def wilson(e,n):
 z=1.959963984540054;p=e/n;den=1+z*z/n;mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
 return [mid-half,mid+half]
completion=json.loads((RUN/'completion.json').read_text())
env=json.loads((OUT/'environment.json').read_text())
ref=json.loads((OUT/'official_reference.json').read_text())[0]
records=[json.loads(x) for x in (RUN/'chunks.jsonl').read_text().splitlines()]
raw_file=REPO/'data/BB_etB_corr_400_0.96875_1_0_2_et1_d12_None.csv'
with raw_file.open() as f: raw=list(csv.DictReader(f,skipinitialspace=True))
assert len(raw)==len(records)
metrics=[];its=[];errors=[];hist=collections.Counter();offset=0
for i,(rec,row) in enumerate(zip(records,raw)):
 with np.load(RUN/f'chunk_{i:04d}.npz') as a:
  it=a['iterations']; pred=a['predicted_observables']; obs=a['observed_observables']; err=np.any((pred+obs)%2,axis=1);nc=it==400
  assert len(it)==16384 and pred.shape==obs.shape==(16384,12)
  assert np.isin(pred,[0,1]).all() and np.isin(obs,[0,1]).all()
  assert ((it>=0)&(it<=400)).all()
  assert int(err.sum())==int(row['errors'])==rec['logical_errors']
  assert int(row['shots'])==rec['shots']==len(it)
  assert int(row['discards'])==0
  assert row['strong_id']==ref['row']['strong_id'] and row['decoder']==ref['row']['decoder']
  assert json.loads(row['json_metadata'])==json.loads(ref['row']['json_metadata'])
  assert int((~nc).sum())==rec['native_converged']
  assert rec['llr_finite'] and rec['llr_ab_finite']
  its.append(it.copy());errors.append(err.copy());hist.update(map(int,it))
  metrics.append(dict(chunk=i,first_shot_index=offset,shots=len(it),logical_errors=int(err.sum()),native_converged=int((~nc).sum()),native_nonconverged=int(nc.sum()),nonconverged_logical_errors=int((nc&err).sum()),nonconverged_without_logical_error=int((nc&~err).sum()),logical_or_nonconvergence=int((nc|err).sum()),iteration_index_mean=float(it.mean()),iteration_index_min=int(it.min()),iteration_index_max=int(it.max()),iteration_index_median=float(np.median(it)),iteration_index_p95=float(np.percentile(it,95)),decoder_seconds=rec['decoder_seconds'],csv_rounded_seconds=float(row['seconds']),csv_rounded_iteration_mean=json.loads(row['custom_counts'])['avg_itr']))
  offset+=len(it)
it=np.concatenate(its);err=np.concatenate(errors);nc=it==400;n=len(it);e=int(err.sum());rn=int(ref['row']['shots']);re=int(ref['row']['errors']);rate=e/n;rr=(e/n)/(re/rn)
se=math.sqrt(1/e+1/re);rci=[math.exp(math.log(rr)-1.96*se),math.exp(math.log(rr)+1.96*se)]
compatible=rci[0]<=1<=rci[1]
stdout=(RUN/'run_stdout.txt').read_text();stderr=(RUN/'run_stderr.txt').read_text()
unexpected=[x for x in stdout.splitlines() if 'ERROR:' in x and not ('errors now, printing stats' in x)]
complete=completion['exit_code']==0 and e>=100 and not unexpected and 'logical error rate per round =' in stdout
assert all(x['logical_errors']>=0 for x in metrics)
assert sum(x['logical_errors'] for x in metrics[:-1])<100
assert n==len(raw)*16384
assert all(x['matches_commit'] for x in json.loads((OUT/'source_verification.json').read_text()).values())
# Freeze every generated file except __pycache__; practical caches are copied too.
manifest=[]
for p in REPO.rglob('*'):
 if not p.is_file() or '__pycache__' in str(p):continue
 rel=str(p.relative_to(REPO))
 manifest.append(dict(path=rel,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 if p.suffix=='.pkl' or p==raw_file or rel=='my_decoders/hbplib_v2.so':
  dest=OUT/'raw/native_generated'/rel;dest.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(p,dest)
dump('native_file_manifest.json',manifest)
# Prior run was already active at task entry. Archive only after its time footer exists.
prior=OUT/'prior_python313';prior.mkdir(exist_ok=True)
prior_logs=prior if (prior/'run_stderr.txt').exists() else OUT
old_stderr=(prior_logs/'run_stderr.txt').read_text()
if old_stderr.startswith('real ') or '\nreal ' in old_stderr:
 if prior_logs==OUT:
  for name in ['run_stdout.txt','run_stderr.txt']:shutil.copy2(OUT/name,prior/name)
 oldraw=Path('/tmp/gari-nms-audit/data')/raw_file.name
 shutil.copy2(oldraw,prior/oldraw.name)
 with oldraw.open() as f: oldrows=list(csv.DictReader(f,skipinitialspace=True))
 prior_summary=dict(shots=sum(int(r['shots']) for r in oldrows),logical_errors=sum(int(r['errors']) for r in oldrows),discards=sum(int(r['discards']) for r in oldrows),csv_decoder_seconds=sum(float(r['seconds']) for r in oldrows),python='3.13.6',stim='1.15.0',status='Supplementary prior run; does not meet official Python 3.11 requirement',native_completion_footer=old_stderr,convergence='Not emitted',per_shot='Not captured')
 dump('prior_python313/summary.json',prior_summary)
 for name in ['run_stdout.txt','run_stderr.txt']:shutil.copy2(RUN/name,OUT/name)
else:
 raise RuntimeError('Prior run has not completed; preserve its live logs before promoting primary logs')
rounded_itr=sum(json.loads(r['custom_counts'])['avg_itr'] for r in raw)/sum(json.loads(r['custom_counts'])['base'] for r in raw)
ref_custom=json.loads(ref['row']['custom_counts']); ref_itr=ref_custom['avg_itr']/ref_custom['base']
seconds=sum(r['decoder_seconds'] for r in records);csv_seconds=sum(float(r['seconds']) for r in raw)
ler=sinter.shot_error_rate_to_piece_error_rate(rate,pieces=12,values=12);rler=sinter.shot_error_rate_to_piece_error_rate(re/rn,pieces=12,values=12)
status='PASS_WITH_WARNINGS' if complete and compatible else 'FAIL'
summary=dict(status=status,ready_for_same_stim_adapter=status=='PASS_WITH_WARNINGS',gari_commit=env['gari_commit'],ureca_commit=env['ureca_commit'],circuit=env['circuit'],command=(OUT/'command.txt').read_text().strip(),completion=completion,shots_processed=n,completed_batches=len(records),discarded_shots=0,incomplete_shots=0 if complete else None,logical_errors=e,shot_logical_failure_rate=rate,shot_rate_wilson95=wilson(e,n),sinter_per_round_any_observable_rate=ler,native_converged=int((~nc).sum()),native_nonconverged=int(nc.sum()),nonconverged_logical_errors=int((nc&err).sum()),nonconverged_without_logical_error=int((nc&~err).sum()),logical_or_nonconvergence=int((nc|err).sum()),iterations=dict(meaning='zero-based sweep index for accepted native convergence; 400 sentinel for rejected outcome',mean=float(it.mean()),median=float(np.median(it)),p95=float(np.percentile(it,95)),p99=float(np.percentile(it,99)),min=int(it.min()),max=int(it.max()),accepted_convergence_mean=float(it[~nc].mean()),csv_rounded_batch_mean=rounded_itr),ensemble_size=1,graph_dimensions={k:records[0][k] for k in ['dem_shape','expanded_shape','dx_shape','dz_shape']},decoder_seconds=seconds,csv_rounded_decoder_seconds=csv_seconds,official_reference=ref,rate_ratio=rr,approximate_rate_ratio_ci95=rci,statistical_compatibility=compatible,information_boundary='PASS: no hidden-information path found in executed configuration',unexpected_errors=unexpected,stderr=stderr,limitations=['Official dependency versions, hardware, Stim seed and circuit hash absent from reference row','Native convergence is B/dz-block convergence only','400 is native rejection sentinel; zero correction may nevertheless score as logically correct','Iteration index is zero-based; CSV averages are rounded per batch','Passive trace dispatch adds Python overhead; post-call NPZ writes excluded from native timer; concurrent prior attempt overlaps setup; official runtime is not a hardware-matched target','General multi-member iteration selection caveat documented; ensemble=1 only validated','Rate-ratio interval is approximate rare-event compatibility check; outcome-based stopping is not an exact fixed-n equivalence test'])
dump('reproduction_summary.json',summary)
csvwrite('native_metrics.csv',metrics)
csvwrite('iteration_histogram.csv',[dict(native_iteration_index=k,shots=v,meaning='rejection sentinel' if k==400 else f'{k+1} sweeps') for k,v in sorted(hist.items())])
rows=[]
def compare(metric,official,reproduced,diff,interpretation):rows.append(dict(metric=metric,official_checkin_value=official,reproduced_value=reproduced,difference=diff,interpretation=interpretation))
compare('ensemble_size',1,1,0,'Decoder name without en suffix and CLI ens=0 map to one member')
compare('requested_iteration_limit',400,400,0,'Unchanged; zero-based inclusive C-loop semantics documented separately')
compare('normalization_alpha',0.96875,0.96875,0,'Exact decoder-name/configuration match')
compare('shots',rn,n,n-rn,'Outcome-stopped experiment; total shots need not match')
compare('logical_errors',re,e,e-re,'Stop at >=100 errors after a complete 16384-shot batch; overshoot retained')
compare('discards',0,0,0,'Every completed shot retained, including native nonconvergence')
compare('shot_logical_failure_rate',re/rn,rate,rate-re/rn,'Compatible under approximate rare-event rate-ratio 95% interval' if compatible else 'Rate difference requires diagnosis')
compare('sinter_per_round_any_observable_rate',rler,ler,ler-rler,'Same Sinter transformation: pieces=12, values=12; per-round failure of any observable under its independent-piece model')
compare('avg_itr_div_base_rounded_batch_means',ref_itr,rounded_itr,rounded_itr-ref_itr,'Comparable coarse statistic; official raw avg_itr=48 and base=16; batch sizes not proven identical')
compare('exact_iteration_index_mean','not available',float(it.mean()),'not identifiable','Preserved from native per-shot return arrays')
compare('native_converged','not available',int((~nc).sum()),'not identifiable','Native selected B/dz block acceptance only')
compare('native_nonconverged','not available',int(nc.sum()),'not identifiable','400 sentinel, includes index-400 convergence rejected by batch wrapper')
compare('logical_or_nonconvergence','not available',int((nc|err).sum()),'not identifiable','Supplementary accounting; does not replace official logical scoring')
compare('software_decoder_seconds_csv',float(ref['row']['seconds']),csv_seconds,csv_seconds-float(ref['row']['seconds']),'Hardware/environment not matched; different shot count and batch-level rounding; no performance equality requirement')
compare('software_decoder_seconds_high_precision','not available',seconds,'not identifiable','Native driver timed interval; passive post-call capture excluded')
compare('software_total_wall_seconds','not available',completion['wall_seconds'],'not identifiable','Includes graph setup, sampling, passive capture and process startup; concurrent prior run overlaps')
csvwrite('official_vs_reproduced.csv',rows)
# Verify prior audit has not changed during this task.
audit=OUT.parent/'gari-relaybp-matched-audit';before=json.loads((OUT/'prior_audit_manifest.json').read_text());after={str(p.relative_to(audit)):hashlib.sha256(p.read_bytes()).hexdigest() for p in audit.rglob('*') if p.is_file()}
assert before==after
report=f'''# Official GARI native reproduction — {status}

## Decision

**{'YES' if summary['ready_for_same_stim_adapter'] else 'NO'} — {'the unchanged single-member native implementation completed the official experiment in Python 3.11, passed input-boundary inspection, and produced a statistically compatible logical rate. Proceeding to an adapter is justified with the native semantics below preserved.' if summary['ready_for_same_stim_adapter'] else 'the native completion or statistical compatibility check did not pass; see summary and raw evidence.'}**

This report validates only the audited native configuration. No same-STIM adapter or matched benchmark was created. Relay-BP was not changed or run. The prior matched-audit file manifest is unchanged.

## Frozen implementation and environment

- URECA commit: `{env['ureca_commit']}` (current committed tree; existing untracked audit/run artifacts retained).
- Official GARI commit: `{env['gari_commit']}` from https://github.com/astra-decoders/gari-nms.git.
- Python: {env['python']}; Stim {env['stim']}.
- Runtime imports: {', '.join(k+' '+v for k,v in env['dependencies'].items())}. README explicitly requests Python 3.11 and `pip install ldpc stim sinter`; transitive/runtime imports and full freeze are recorded.
- Native `my_decoders/hbp_decoder_v2.c` built by unchanged Makefile with Apple Clang and Homebrew libomp. Exit 0; six unused-code warnings retained in build_stderr.txt. Checked-in shared binary was rebuilt for this machine.
- Sources and circuit match the pinned commit byte-for-byte (source_verification.json). No GARI parameter or source was changed.
- Prior dependency/build/redirection failures and the pre-existing Python 3.13 attempt are retained in dependency_and_attempt_history.md and prior_python313/. The prior attempt processed {prior_summary['shots']:,} shots with {prior_summary['logical_errors']} logical errors; it is supplementary because it used Python 3.13.

## Exact circuit

`{env['circuit']['path']}`

SHA256: `{env['circuit']['sha256']}`

[[144,12,12]] BB memory-Z experiment; 288 circuit qubits (144 data plus ancillas), 1,728 detectors, 12 observables, 12 rounds, p=0.002. CL both-basis noise: p1=p2=p3=p4=p (after Clifford depolarization, reset flips, pre-measurement flips, before-round data depolarization). The checked-in circuit contains an initial round followed by `REPEAT 11`; the command loads this exact existing file, so fallback generation is not needed. Flattened noise instructions have argument 0.002.

## Execution

```sh
{summary['command']}
```

Working directory `/tmp/gari-native-6380d52`; `/tmp/gari-native-py311/bin` prepended to PATH. Four OpenMP threads, schedule seed 1, normalized min-sum alpha 0.96875, schedule 2, prior type 0, iteration limit 400, CLI ens=0 maps to one member. Stim sampling seed is unspecified, as in the official driver. No outcome-driven parameter changes or repeated search for a successful run.

`observer/sitecustomize.py` is a read-only Python trace: saves already-returned iterations and predicted/observed logical bits after each decoder timing interval. It does not alter decoder inputs, control flow, RNG, or outputs. Total wall time includes trace-dispatch and output-capture overhead; native timed intervals exclude NPZ writes but include any trace-dispatch overhead in the Python wrapper. The C decoder is unchanged and uninstrumented. Both official source and observer are available for inspection.

- Exit: {completion['exit_code']}; completed {len(records)} batches, **{n:,} shots**.
- **{e} logical errors**, rate **{rate:.10g}** per shot; Sinter pieces=12/values=12 rate {ler:.10g}.
- **{int((~nc).sum()):,} native converged; {int(nc.sum()):,} native nonconverged/rejected**.
- Nonconverged with logical error: {int((nc&err).sum())}; nonconverged without logical error: {int((nc&~err).sum())}; union (logical error or native rejection): {int((nc|err).sum())}.
- Discards: 0. Incomplete shots: {summary['incomplete_shots']}. Every complete batch and rejection retained. Stop condition >=100 logical errors evaluated only after a full batch.
- Returned iteration-index mean **{it.mean():.8f}**, median {np.median(it):g}, p95 {np.percentile(it,95):g}, p99 {np.percentile(it,99):g}, range {it.min()}–{it.max()}. Mean among native accepted shots {it[~nc].mean():.8f}. CSV rounded-batch-mean statistic {rounded_itr:g}.
- Native decoder timed intervals total **{seconds:.6f} seconds**; generated CSV rounded sum {csv_seconds:g} seconds; full process wall time **{completion['wall_seconds']:.6f} seconds**.
- Raw stdout and stderr are preserved verbatim. The driver's final `ERROR: ... has ... errors now, printing stats` is its normal error-target termination message, not a runtime failure.

## Cross-environment diagnostic

The Python 3.11 / Stim 1.16 run and preserved Python 3.13 / Stim 1.15 attempt produce identical DEM text hashes (`bf04909de351a8198bc8a2e7a6b5ae1a9b93377132dd6600084d3c2bafdea13d`) and equal values in every generated static matrix/adjacency field. Their rebuilt C libraries are also byte-identical. See cross_environment_static_graph_comparison.json and each attempt's dem_fingerprint.json. This check uses no sampling or decoding and does not substitute the prior attempt for the primary result.

## Official comparison

Exact matching decoder name and strong_id found in `{ref['file']}` line {ref['line']}: **1,048,576 shots, 100 errors, 0 discards, 567 seconds**, custom_counts `avg_itr=48, base=16` ⇒ rounded batch-mean statistic **3**. Full source CSV and extracted row preserved. This is the closest checked-in configuration match; the row does not encode circuit hash, dependency versions, hardware, thread count, or sampling seed, so exact historical provenance cannot be proved from it alone.

| metric | official/check-in value | reproduced value | difference | interpretation |
|---|---:|---:|---:|---|
'''
for r in rows:report+='| '+' | '.join(str(r[k]) for k in ['metric','official_checkin_value','reproduced_value','difference','interpretation'])+' |\n'
report+=f'''
Logical-rate ratio reproduced/official = **{rr:.6f}**, approximate 95% interval **[{rci[0]:.6f}, {rci[1]:.6f}]**; compatibility = {compatible}. We use a rare-event log-rate-ratio interval (SE sqrt(1/e_reproduced+1/e_official)) as a descriptive check. Because each experiment stops on error counts at batch boundaries, this is not an exact fixed-shot equivalence test. The Sinter per-round value is a model-based conversion for failure of any of the 12 observables, not a directly measured per-round event rate or a per-observable rate. No bit-identical stochastic outcome is required: the official Stim sampler has no fixed seed. Matching rounded iteration summaries is weak precision evidence, not exact work equivalence. Runtime differences are reported without using them as fidelity failures or comparing to FPGA nanoseconds/Relay-BP cycles.

## Information boundary and iteration semantics

**PASS: no sampled physical-error or true logical-label input to decoding was found.** Detector/syndrome bits, circuit-derived graph/prior information, and static logical operators are the decoder inputs. Actual observable labels are used only after decoding for scoring and aggregate stopping. See information_boundary.md for source locations and complete limitations.

A sweep visits all expanded-graph check rows serially, in bottom/A/B order with separate A/B schedule permutations, updates normalized min-sum messages and variable LLRs, then checks the B/dz syndrome block. Native returned k<400 is a zero-based sweep index (k+1 completed sweeps). The inclusive loop permits up to 401 sweeps. The batched wrapper maps all nonaccepted outcomes to 400, including convergence at index 400; 400 is a rejection sentinel. Therefore native convergence is not a proof that every expanded constraint is satisfied, and the integer is not an exact universal work count. **It must not automatically be equated with one Relay-BP iteration. No GARI cycle count is invented.**

Native nonconvergence returns zero logical correction. Such shots can match the observed logical bits and be absent from the official logical-error count (none did in this run); the separate counts above expose this instead of discarding or relabeling them. General multi-member iteration selection also has a source caveat documented in information_boundary.md; it is inactive for this one-member reproduction.

## Status rationale

{status}: {'native build/import/run and batch accounting passed; no hidden-information path found; observed logical-rate difference is compatible with sampling variation. Warnings remain for unpinned official environment/provenance, coarse reference iteration metrics, native selected-block/sentinel semantics, passive capture overhead, and overlapping prior-run runtime.' if status=='PASS_WITH_WARNINGS' else 'One or more required checks failed; inspect reproduction_summary.json and raw logs before further work.'}

## Saved artifacts

Required files: README.md, environment.json, command.txt, run_stdout.txt, run_stderr.txt, reproduction_summary.json, official_vs_reproduced.csv, native_metrics.csv.

Additional evidence: build logs, dependency history, requirements-freeze.txt, official_source/, source_verification.json, official_reference.json, raw circuit and checked-in results, raw/native_generated/ (CSV, native matrix caches, rebuilt C library), python311/chunk_*.npz (every shot's returned iteration index and predicted/observed observables), chunks.jsonl (batch metrics), completion.json, iteration_histogram.csv, observer source, launch/analysis scripts, prior_python313/ logs and CSV, and prior-audit hash manifest. Shot indices are zero-based and ordered by batch then NPZ row. Per-shot runtime is not emitted; only batch decoder timing is available. No physical error vector is captured. The temporary venv/checkout are not required to interpret the saved raw results.
'''
(OUT/'README.md').write_text(report)
print(json.dumps(summary,indent=2))

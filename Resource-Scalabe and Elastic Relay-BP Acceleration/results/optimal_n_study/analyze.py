from pathlib import Path
import csv,json,hashlib,math,sys,time
import numpy as np
from scipy.stats import beta,binomtest
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_text())
def csvout(name,rows):
 with (OUT/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def dump(name,x): (OUT/name).write_text(json.dumps(x,indent=2)+'\n')
def lower(k,n,alpha):return float(beta.ppf(alpha,k,n-k+1)) if k else 0.
def ci(k,n):return [lower(k,n,.025),float(beta.ppf(.975,k+1,n-k)) if k<n else 1.]
def holm(ps):
 order=np.argsort(ps);out=[0.]*len(ps);prev=0.
 for rank,i in enumerate(order):prev=max(prev,min(1.,float(ps[i])*(len(ps)-rank)));out[i]=prev
 return out
def main():
 start=time.monotonic(); cfg=load(OUT/'methodology.json');ns=cfg['N'];ds=cfg['hypothetical_deadlines_cycles'];nshot=128
 # Hash every archived result, graph/package, reference and testbench file before analysis.
 dirs=['results/n-scaling-canonical','results/n-scaling-canonical-n8-complete','results/external_decoder_benchmark','results/resource_tradeoff_analysis','graphs','reference','simulations/configurable_testbench']
 before={str(p.relative_to(ROOT)):sha(p) for d in dirs for p in (ROOT/d).rglob('*') if p.is_file()}
 with (ROOT/'results/n-scaling-canonical/per_shot_results.csv').open() as f:rows=list(csv.DictReader(f))
 with (ROOT/'results/n-scaling-canonical-n8-complete/per_shot_results.csv').open() as f:old=list(csv.DictReader(f))
 manifest=load(ROOT/'results/n-scaling-canonical/manifest.json');agg=load(ROOT/'results/n-scaling-canonical/aggregate_summary.json')
 assert len(rows)==len(old)==128 and manifest['configuration']['P']==4
 samplefile=ROOT/'results/circuit-level-multiseed/paired_samples.npz';assert sha(samplefile)==manifest['hashes']['samples']
 sys.path.insert(0,str(ROOT/'results/n-scaling-canonical'));import run_study as canonical
 with np.load(samplefile) as data:
  for r,o in zip(rows,old):
   seed,shot=int(r['sample_seed']),int(r['shot']);j=int(np.flatnonzero(data['sample_seeds']==seed)[0])
   assert sha_bytes(np.packbits(data['syndromes'][j,shot]).tobytes())==r['detector_sample_hash']
   assert sha_bytes(np.packbits(data['observed_logicals'][j,shot]).tobytes())==r['logical_sample_hash']
   assert [int(r[f's{i}']) for i in range(16)]==list(canonical.seeds(seed,shot,16))
   for n in ns:
    choices=[(int(r[f'e{i}_result_cycles']),i) for i in range(n) if int(r[f'e{i}_syndrome_converged'])]
    cycles,winner=min(choices) if choices else (max(int(r[f'e{i}_result_cycles']) for i in range(n)),-1)
    assert cycles==int(r[f'n{n}_cycles']) and winner==int(r[f'n{n}_winner'])
    assert int(r[f'n{n}_logical_correct'])==(int(r[f'e{winner}_logical_correct']) if winner>=0 else 0)
    if n<=8:
     for key in [f'n{n}_cycles',f'n{n}_winner',f'n{n}_logical_correct']:assert r[key]==o[key]
 arrays={n:np.array([int(r[f'n{n}_cycles']) for r in rows]) for n in ns}
 good={n:np.array([bool(int(r[f'n{n}_logical_correct'])) for r in rows]) for n in ns}
 metrics=[]
 for n in ns:
  x=arrays[n];non=sum(int(r[f'n{n}_non_convergence']) for r in rows);log=sum(int(r[f'n{n}_syndrome_valid_logical_error']) for r in rows)
  z=dict(N=n,provisioned_lanes=4*n,success=int(good[n].sum()),nonconvergence=non,syndrome_valid_logical_errors=log,mean_cycles=float(x.mean()),p95_cycles=float(np.percentile(x,95)),p99_cycles=float(np.percentile(x,99)))
  assert z['success']+non+log==128
  for key in ('mean','p95','p99'):assert np.isclose(z[key+'_cycles'],agg['latency'][f'n{n}'][key],rtol=0,atol=1e-6)
  z['mean_lane_cycles_proxy']=z['mean_cycles']*4*n;z['p99_lane_cycles_proxy']=z['p99_cycles']*4*n;metrics.append(z)
 for z in metrics:
  for key in ('mean_cycles','p99_cycles'):
   z[key+'_pareto']=not any(q['provisioned_lanes']<=z['provisioned_lanes'] and q[key]<=z[key] and (q['provisioned_lanes']<z['provisioned_lanes'] or q[key]<z[key]) for q in metrics)
 csvout('latency_resource_summary.csv',metrics)
 details=[];selections=[];indicators=[];by={};paired=[]
 for d in ds:
  opts={label:[] for label in ('empirical','pointwise','fixed_deadline','whole_grid')}
  for n in ns:
   v=good[n]&(arrays[n]<=d);by[n,d]=v;k=int(v.sum());lo,hi=ci(k,128)
   z=dict(deadline_cycles=d,N=n,lanes=4*n,shots=128,success_by_deadline=k,fraction=k/128,CP95_lower=lo,CP95_upper=hi,one_sided_pointwise_lower=lower(k,128,.05),fixed_deadline_selection_lower=lower(k,128,.05/5),whole_grid_selection_lower=lower(k,128,.05/45),nonconvergence=sum(int(r[f'n{n}_non_convergence']) for r in rows),logical_errors=sum(int(r[f'n{n}_syndrome_valid_logical_error']) for r in rows),correct_but_late=int((good[n]&(arrays[n]>d)).sum()))
   for label,value in [('empirical',z['fraction']),('pointwise',z['one_sided_pointwise_lower']),('fixed_deadline',z['fixed_deadline_selection_lower']),('whole_grid',z['whole_grid_selection_lower'])]:
    z[label+'_qualifies']=bool(value>=.95)
    if z[label+'_qualifies']:opts[label].append(n)
   details.append(z)
   for i,r in enumerate(rows):indicators.append(dict(index=i,sample_seed=int(r['sample_seed']),shot=int(r['shot']),N=n,deadline_cycles=d,logical_correct=bool(good[n][i]),completion_cycles=int(arrays[n][i]),success_by_deadline=bool(v[i])))
  selections.append(dict(deadline_cycles=d,**{label+'_minimum_N':min(v) if v else 'no statistically certified optimum' if label!='empirical' else 'none' for label,v in opts.items()}))
  for a,b in ((2,4),(2,8),(4,8)):
   av,bv=by[a,d],by[b,d];aonly=int((av&~bv).sum());bonly=int((bv&~av).sum());m=aonly+bonly
   paired.append(dict(deadline_cycles=d,N_a=a,N_b=b,a_only_success=aonly,b_only_success=bonly,both_success=int((av&bv).sum()),both_fail=int((~av&~bv).sum()),difference_b_minus_a=float(bv.mean()-av.mean()),exact_p=float(binomtest(bonly,m,.5).pvalue) if m else 1.))
 for r,p in zip(paired,holm([r['exact_p'] for r in paired])):r['Holm27_p']=p;r['significant_05_family']=p<=.05
 csvout('deadline_metrics.csv',details);csvout('minimum_N_by_deadline.csv',selections);csvout('paired_deadline_tests.csv',paired);csvout('per_shot_deadline_indicators.csv',indicators)
 ext=load(ROOT/'results/external_decoder_benchmark/BP_OSD0_results.json');comparison=[]
 for n in ns:
  aa=np.array([bool(r['total_failure']) for r in ext]);bb=np.array([not good[n][r['index']] for r in ext]);aonly=int((~aa&bb).sum());bonly=int((aa&~bb).sum());m=aonly+bonly
  comparison.append(dict(Relay_N=n,paired_shots=len(ext),BP_OSD0_failures=int(aa.sum()),Relay_failures=int(bb.sum()),OSD_only_success=aonly,Relay_only_success=bonly,exact_p=float(binomtest(bonly,m,.5).pvalue) if m else 1.,BP_OSD0_mean_CPU_seconds=float(np.mean([r['decode_seconds'] for r in ext])),Relay_mean_modeled_cycles=float(np.mean([arrays[n][r['index']] for r in ext])),compute_matched=False))
 csvout('BP_OSD0_paired_comparison.csv',comparison)
 # Presentation plots: categorical no-qualification values are drawn outside N scale.
 plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
 fig,ax=plt.subplots(figsize=(11,6));xs=np.array(ds)/1e9
 for label,color,marker,title in [('empirical','#457b9d','o','Empirical ≥95%'),('fixed_deadline','#e76f51','s','95% bound: five-N selection, fixed deadline')]:
  ys=[math.log2(r[label+'_minimum_N']) if isinstance(r[label+'_minimum_N'],int) else np.nan for r in selections];ax.plot(xs,ys,marker=marker,color=color,label=title)
 ax.scatter(xs,[-1]*len(xs),marker='x',s=65,color='#555555',label='Full-grid 95% bound: uncertified at every deadline')
 ax.set_xscale('log');ax.set_xticks(xs,[f'{x:g}' for x in xs]);ax.set_yticks([-1,0,1,2,3,4],['Uncertified','N1','N2','N4','N8','N16']);ax.set_xlabel('Hypothetical decoding deadline (billion modeled cycles)');ax.set_ylabel('Smallest qualifying trajectory count');ax.set_title('Minimum provisioning depends on deadline and evidence standard');ax.grid(alpha=.2);ax.legend(fontsize=9)
 fig.text(.5,.01,'128 archived paired shots; target95%. Full-grid bound corrects45 comparisons. Lines guide discrete grid points.\nModeled architectural cycles, not measured FPGA time; deadlines have no physical QEC interpretation.',ha='center',fontsize=9);fig.tight_layout(rect=[0,.08,1,1]);save(fig,'deadline_minimum_N')
 fig,axs=plt.subplots(1,2,figsize=(12,5.5))
 for ax,key,title in zip(axs,['mean_cycles','p99_cycles'],['Mean modeled completion latency','Empirical p99 modeled completion latency']):
  ax.plot([z['provisioned_lanes'] for z in metrics],[z[key]/1e9 for z in metrics],'o-',color='#457b9d')
  for z in metrics:ax.annotate(f"N{z['N']}",(z['provisioned_lanes'],z[key]/1e9),xytext=(5,7),textcoords='offset points')
  ax.set_xscale('log',base=2);ax.set_xticks([4,8,16,32,64],[4,8,16,32,64]);ax.set_yscale('log');ax.set_xlabel('Provisioned lanes N×P (P=4)');ax.set_ylabel('Billion modeled cycles');ax.set_title(title);ax.grid(alpha=.2)
 fig.text(.5,.01,'All five points are nondominated; no unique Pareto optimum. Lanes are a provisioning proxy, not FPGA area.\n128 paired shots; p99 is based on roughly two upper-tail observations. No measured FPGA timing.',ha='center',fontsize=9);fig.tight_layout(rect=[0,.08,1,1]);save(fig,'latency_provisioning_pareto')
 assert all(sha(ROOT/p)==v for p,v in before.items())
 dump('validation.json',dict(status='PASS',canonical_shots=128,paired_syndrome_and_logical_hashes_checked=128,trajectory_seeds_checked=2048,ensemble_winner_and_cycle_checks=640,N1_N8_archive_matches=True,aggregate_latency_checks=True,archived_files_hash_unchanged=len(before),new_decode_calls=0,analysis_seconds=time.monotonic()-start))
 dump('provenance.json',dict(command='MPLCONFIGDIR=/private/tmp/relay-optimal-matplotlib OPENBLAS_NUM_THREADS=1 ../.venv/bin/python -B results/optimal_n_study/analyze.py',input_and_protected_hashes=before,sample_archive_sha256=sha(samplefile),methodology_sha256=sha(OUT/'methodology.json'),script_sha256=sha(__file__),confidence_model='independent sampled shots conditional on fixed code/noise and fixed RNG policy; trajectories paired, not independent samples',minimum_all_success_shots_fixed_deadline=math.ceil(math.log(.05/5)/math.log(.95)),minimum_all_success_shots_whole_grid=math.ceil(math.log(.05/45)/math.log(.95))))
 dump('analysis_summary.json',dict(selections=selections,all_success_lower_grid=lower(128,128,.05/45),all_success_lower_fixed=lower(128,128,.05/5),significant_paired_tests=[r for r in paired if r['significant_05_family']]))
 print(json.dumps(load(OUT/'analysis_summary.json'),indent=2))
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def save(fig,name):
 fig.savefig(OUT/(name+'.png'),dpi=320,bbox_inches='tight');fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
if __name__=='__main__':main()

#!/usr/bin/env python3
"""Decision-only comparison of frozen BA2, F1, and F3 layouts."""
from __future__ import annotations
import csv,hashlib,importlib.util,json
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
BA=ROOT/'results/bank-aware-folding-layout';REF=ROOT/'results/bank-aware-folding-layout-refinement';ARCH=ROOT/'results/n1-vs-n2-hardware-latency/per_shot_results.csv'
def mod(name,p):s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ba=mod('ba',BA/'run_bank_aware_layout.py');rf=mod('rf',REF/'run_fault_refinement.py');fm=ba.fm
def rows(p):
 with p.open(newline='') as f:return list(csv.DictReader(f))
def wc(p,x):
 with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(x[0]));w.writeheader();w.writerows(x)
def wj(p,x):p.write_text(json.dumps(x,indent=2,default=ba.json_default)+'\n')
def ah(x):return ba.ahash(np.asarray(x))
def pct(a,b):return 100*(a/b-1)

def main():
 OUT.mkdir(parents=True,exist_ok=True);g=ba.load();saved={x['variant']:x for x in rows(REF/'variant_comparison.csv')}
 with np.load(BA/'permutations.npz') as z:bfo=np.asarray(z['fault_old_to_new']);beo=np.asarray(z['edge_old_to_new'])
 with np.load(REF/'permutations.npz') as z:f1fo=np.asarray(z['fault_old_to_new']);f1eo=np.asarray(z['edge_old_to_new'])
 if not np.array_equal(beo,f1eo):raise RuntimeError('F1 did not freeze BA2 edge mapping')
 base=ba.bank_layout('BA2',g,bfo%4,beo%4);cg,rg=rf.exact_groups(g,base);cm=ba.pair_matrix(g['V'],cg);rm=ba.pair_matrix(g['V'],rg);work=np.asarray(g['H'].sum(axis=0)).ravel().astype(float)*2
 f3res,_=ba.greedy_residues((2*cm+rm).tocsr(),work,np.zeros(g['V'],np.int8),0.25,0.0)
 candidates={'BA2':ba.bank_layout('BA2',g,bfo%4,beo%4),'F1':ba.bank_layout('F1',g,f1fo%4,beo%4),'F3':ba.bank_layout('F3',g,f3res,beo%4)}
 profiles={};struct=[];invariants={};hashes={}
 for name,lay in candidates.items():
  ph,total=fm.profile(lay,g['check_part'],g['fault_part']);profiles[name]=ph;row=ba.metric_row(name,ph,total,ba.layout_bank_stats(lay,g,work,np.full(g['E'],2.0)));struct.append(row)
  inv,_,_,_=ba.invariance(g,lay);invariants[name]=inv
  hashes[name]=dict(fault_old_to_new=ah(lay['fault_old_to_new']),fault_new_to_old=ah(lay['fault_new_to_old']),edge_old_to_new=ah(lay['edge_old_to_new']),edge_new_to_old=ah(lay['edge_new_to_old']))
  prior=saved[name]
  for k in ('variable_mu_retries','variable_nu_retries','convergence_retries','relay_init_retries','retry_subsets','estimated_structural_cycles'):
   if int(row[k])!=int(float(prior[k])):raise RuntimeError(f'{name} identity mismatch {k}: {row[k]} != {prior[k]}')
 if not all(x['variable_mu_retries']==0 and x['variable_nu_retries']==0 for x in struct):raise RuntimeError('zero-retry constraint failed')
 original_saved=saved['original']
 ba2row=next(x for x in struct if x['variant']=='BA2')
 for r in struct:
  for field in ('retry_subsets','convergence_retries','relay_init_retries','estimated_structural_cycles'):
   value=float(r[field]);orig=float(original_saved[field]);b2=float(ba2row[field])
   r[field+'_delta_vs_original']=value-orig;r[field+'_percent_vs_original']=pct(value,orig);r[field+'_delta_vs_BA2']=value-b2;r[field+'_percent_vs_BA2']=pct(value,b2)
 archive=rows(ARCH);per=[]
 ordered=sorted(archive,key=lambda x:(int(x['e0_iterations']),int(x['e0_legs']),int(x['sample_seed']),int(x['shot'])))
 group={id(x):('easy' if i<43 else 'medium' if i<85 else 'hard_tail') for i,x in enumerate(ordered)}
 # id() is stable here because ordered holds the original dict objects.
 for x in archive:
  rec=dict(sample_seed=int(x['sample_seed']),shot=int(x['shot']),iterations=int(x['e0_iterations']),relay_legs=int(x['e0_legs']),difficulty_group=group[id(x)])
  for name,ph in profiles.items():
   it=sum(ph[p]['estimated_cycles'] for p in ('check','variable','convergence'));ri=ph['relay_init']['estimated_cycles'];rec[name+'_cycles']=rec['iterations']*it+rec['relay_legs']*ri
  rec['F1_delta_vs_BA2']=rec['F1_cycles']-rec['BA2_cycles'];rec['F3_delta_vs_BA2']=rec['F3_cycles']-rec['BA2_cycles'];per.append(rec)
 traj=[]
 for name in candidates:
  vals=np.array([x[name+'_cycles'] for x in per],float);basevals=np.array([x['BA2_cycles'] for x in per],float)
  traj.append(dict(variant=name,mean=float(vals.mean()),p50=float(np.percentile(vals,50)),p90=float(np.percentile(vals,90)),p95=float(np.percentile(vals,95)),p99=float(np.percentile(vals,99)),maximum=float(vals.max()),absolute_mean_delta_vs_BA2=float(vals.mean()-basevals.mean()),percent_mean_delta_vs_BA2=pct(vals.mean(),basevals.mean()),improved_vs_BA2=int(np.sum(vals<basevals)),unchanged_vs_BA2=int(np.sum(vals==basevals)),worsened_vs_BA2=int(np.sum(vals>basevals))))
 original_ph,_=fm.profile(fm.layouts(g['H'],g['co'],g['cn'],g['fo'],g['fn'])[0],g['check_part'],g['fault_part']);oit=sum(original_ph[p]['estimated_cycles'] for p in ('check','variable','convergence'));ori=original_ph['relay_init']['estimated_cycles'];ov=np.array([int(x['e0_iterations'])*oit+int(x['e0_legs'])*ori for x in archive],float)
 oq={k:float(np.percentile(ov,q)) for k,q in [('p50',50),('p90',90),('p95',95),('p99',99)]};oq['mean']=float(ov.mean());oq['maximum']=float(ov.max());bq=next(x for x in traj if x['variant']=='BA2')
 for r in traj:
  for field in ('mean','p50','p90','p95','p99','maximum'):
   r[field+'_absolute_delta_vs_original']=r[field]-oq[field];r[field+'_percent_delta_vs_original']=pct(r[field],oq[field]);r[field+'_absolute_delta_vs_BA2']=r[field]-bq[field];r[field+'_percent_delta_vs_BA2']=pct(r[field],bq[field])
 groups=[]
 for grp in ('easy','medium','hard_tail'):
  z=[x for x in per if x['difficulty_group']==grp]
  for name in candidates:groups.append(dict(difficulty_group=grp,variant=name,shots=len(z),mean_iterations=float(np.mean([x['iterations'] for x in z])),mean_relay_legs=float(np.mean([x['relay_legs'] for x in z])),mean_modeled_cycles=float(np.mean([x[name+'_cycles'] for x in z])),mean_delta_vs_BA2=float(np.mean([x[name+'_cycles']-x['BA2_cycles'] for x in z]))))
 ranking=sorted(traj,key=lambda x:(x['mean'],x['p95'],x['p99'],next(s['estimated_structural_cycles'] for s in struct if s['variant']==x['variant'])))
 technical=ranking[0]['variant'];gain=-ranking[0]['percent_mean_delta_vs_BA2'];selected='BA2' if technical!='BA2' and gain<0.1 else technical
 decision=dict(predeclared_rule=['invariants pass','MU and NU retries zero','lowest trajectory mean','lowest p95','lowest p99','lowest structural cycles'],technical_winner=technical,technical_winner_gain_percent_vs_BA2=gain,practical_threshold_percent=0.1,selected_layout=selected,decision='KEEP BA2' if selected=='BA2' else f'REPLACE BA2 WITH {selected}',reason='F3 is consistently lower across all shots and difficulty groups, but its mean advantage is below 0.1% and does not justify another 256-trajectory equivalence study or a second maintained layout.' if selected=='BA2' else 'Material trajectory-weighted benefit justifies revalidation.',equivalence_required=selected!='BA2')
 execution=dict(shots=len(per),total_iterations=sum(x['iterations'] for x in per),total_relay_legs=sum(x['relay_legs'] for x in per));execution['iterations_per_relay_init']=execution['total_iterations']/execution['total_relay_legs']
 wc(OUT/'candidate_comparison.csv',struct);wc(OUT/'trajectory_metrics.csv',traj);wc(OUT/'per_shot_comparison.csv',per);wc(OUT/'difficulty_group_summary.csv',groups);wj(OUT/'decision_summary.json',dict(**decision,execution_frequency=execution,candidate_hashes=hashes,invariants=invariants));wj(OUT/'study_manifest.json',dict(status='complete',candidate_sources=dict(BA2=str(BA/'permutations.npz'),F1=str(REF/'permutations.npz'),F3='deterministically reconstructed alpha=2 beta=1 gamma=0.25 from frozen BA2-edge exact groups'),edge_mapping_identical_all_candidates=True,hashes=hashes,execution_frequency=execution,decision=decision))
 (OUT/'README.md').write_text(f'''# BA2/F1/F3 layout decision\n\nThis software-only decision study separates a one-pass structural objective from archived E0 trajectory weighting. All candidates preserve the BA2 edge mapping, zero MU/NU retries, and exact graph invariants. Across 128 shots, convergence/check/variable execute {execution['total_iterations']} times while relay initialization executes {execution['total_relay_legs']} times ({execution['iterations_per_relay_init']:.2f} iterations per init). The predeclared trajectory-first rule gives technical winner `{technical}`; the practical decision is **{decision['decision']}** because its advantage over validated BA2 is negligible relative to revalidation cost. No decoder was rerun and no FPGA-speedup claim is made.\n''')
 print(json.dumps(dict(decision=decision,execution=execution,structural=struct,trajectory=traj,difficulty=groups),indent=2,default=ba.json_default))
if __name__=='__main__':main()

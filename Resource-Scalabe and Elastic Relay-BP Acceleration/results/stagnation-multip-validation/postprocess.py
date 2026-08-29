#!/usr/bin/env python3
"""Cross-p tables, running-best strata, late escapes, and validation plots."""
import csv,json
from collections import defaultdict
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1];A5=ROOT/'results/full-dataset-stagnation-analysis';ARCH=ROOT/'results/n1-vs-n2-hardware-latency/per_shot_results.csv'
def write(path,rows):
 with path.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def binbest(x):return '1' if x==1 else '2-3' if x<=3 else '4-8' if x<=8 else '>8'
def main():
 shots=pd.read_csv(OUT/'per_shot_results.csv');legs=pd.read_csv(OUT/'per_leg_summary.csv');validation=json.loads((OUT/'validation_metrics.json').read_text())
 # Running-best interaction and target-3 false-positive risk.
 best={}
 for p in (.002,.004):
  z=legs[(legs.p==p)&(legs.converged==0)&(legs.target3_eligible==1)&(legs.iterations_since_best_at_end>=120)].copy();z['best_bin']=z.global_best_after.map(binbest)
  best[str(p)]={}
  for b in ('1','2-3','4-8','>8'):
   q=z[z.best_bin==b];best[str(p)][b]={'eligible':len(q),'future_unproductive':int(q.target3.sum()),'future_unproductive_rate':None if len(q)==0 else float(q.target3.mean()),'late_escape_within_3_rate':None if len(q)==0 else float(1-q.target3.mean())}
 validation['running_best_interaction']=best
 # Late escape events: a productive leg following a boundary already stagnant >=120.
 late=[]
 for (p,seed,shot),g in legs.sort_values('relay_leg').groupby(['p','sample_seed','shot']):
  g=list(g.to_dict('records'));sr=shots[(shots.p==p)&(shots.sample_seed==seed)&(shots.shot==shot)].iloc[0]
  for i in range(1,len(g)):
   prev,cur=g[i-1],g[i]
   if prev['iterations_since_best_at_end']>=120 and cur['global_best_improvement']>0:
    n=0
    for x in reversed(g[:i]):
     if x['category']=='productive':break
     n+=1
    late.append({'p':p,'sample_seed':int(seed),'shot':int(shot),'stagnation_duration_before_escape':int(prev['iterations_since_best_at_end']),'running_best_before_escape':int(prev['global_best_after']),'unproductive_legs_before_escape':n,'escape_relay_leg':int(cur['relay_leg']),'residual_improvement_at_escape':int(cur['global_best_improvement']),'escape_converged':int(cur['converged']),'final_outcome':'logical_success' if sr.logical_success else 'logical_error' if sr.logical_error else 'non_convergence'})
 write(OUT/'late_escape_cases.csv',late if late else [{'p':'','sample_seed':'','shot':'','stagnation_duration_before_escape':'','running_best_before_escape':'','unproductive_legs_before_escape':'','escape_relay_leg':'','residual_improvement_at_escape':'','escape_converged':'','final_outcome':''}])
 validation['late_escape_events']={str(p):int(sum(x['p']==p for x in late)) for p in (.002,.004)}
 validation['target3_false_positive_boundaries']={str(p):int(len(legs[(legs.p==p)&(legs.converged==0)&(legs.target3_eligible==1)&(legs.iterations_since_best_at_end>=120)&(legs.target3==0)])) for p in (.002,.004)}
 (OUT/'validation_metrics.json').write_text(json.dumps(validation,indent=2)+'\n')
 # Cross-p table; p=.003 is reused, not replayed.
 a3=pd.read_csv(ARCH);l3=pd.read_csv(A5/'per_leg_summary.csv');t3=pd.read_csv(A5/'threshold_analysis.csv')
 cross=[]
 for p,s,l in ((.002,shots[shots.p==.002],legs[legs.p==.002]),(.003,a3,l3),(.004,shots[shots.p==.004],legs[legs.p==.004])):
  if p==.003:
   mult=float((s.e0_legs>1).mean());fail=float(s.e0_non_convergence.mean());logical=float(s.e0_syndrome_valid_logical_error.mean());convcol='e0_syndrome_converged'
  else:
   mult=float((s.relay_legs>1).mean());fail=float(s.non_convergence.mean());logical=float(s.logical_error.mean());convcol='converged'
  risk=l[l.converged==0] if 'converged' in l else l
  stagn=risk.iterations_since_best_at_end.to_numpy(float)
  for target in (1,2,3,4):
   if p==.003:
    m=t3[(t3.observation_type=='leg_boundary')&(t3.stratum=='all')&(t3.target==target)&(t3.stagnation_threshold==120)].iloc[0]
    vals={k:m[k] for k in ('eligible','positives','precision','recall','specificity','balanced_accuracy')};fp=int(m.fp)
   else:
    m=validation[str(p)]['frozen_120']['all_multi_leg'][str(target)];vals={'eligible':m['eligible_boundaries'],'positives':m['positives'],'precision':m['precision'],'recall':m['recall'],'specificity':m['specificity'],'balanced_accuracy':m['balanced_accuracy']};fp=m['fp']
   cross.append({'p':p,'target':target,'shots':len(s),'fraction_trajectories_multi_leg':mult,'unproductive_leg_fraction':float((l.category!='productive').mean()),'stagnation_boundary_median':float(np.median(stagn)),'stagnation_boundary_p90':float(np.percentile(stagn,90)),'stagnation_boundary_max':float(np.max(stagn)),'eligible_boundaries':vals['eligible'],'target_positives':vals['positives'],'frozen_precision':vals['precision'],'frozen_recall':vals['recall'],'frozen_specificity':vals['specificity'],'frozen_balanced_accuracy':vals['balanced_accuracy'],'late_escape_false_positive_boundaries':fp,'failure_rate':fail,'logical_error_rate':logical})
 write(OUT/'cross_p_comparison.csv',cross)
 # Few high-value plots.
 c=pd.DataFrame(cross);z=c[c.target==3]
 x=np.arange(3);w=.34
 plt.bar(x-w/2,z.frozen_precision,w,label='precision');plt.bar(x+w/2,z.frozen_recall,w,label='recall');plt.xticks(x,[f'{v:.3f}' for v in z.p]);plt.ylim(0,1);plt.xlabel('p');plt.legend();plt.tight_layout();plt.savefig(OUT/'frozen_precision_recall_by_p.png',dpi=170);plt.close()
 plt.bar([str(x) for x in z.p],z.unproductive_leg_fraction);plt.ylim(0,1);plt.xlabel('p');plt.ylabel('Unproductive-leg fraction');plt.tight_layout();plt.savefig(OUT/'unproductive_legs_by_p.png',dpi=170);plt.close()
 data=[];labels=[]
 for p in (.002,.003,.004):
  q=l3.iterations_since_best_at_end if p==.003 else legs[legs.p==p].iterations_since_best_at_end;data.append(q);labels.append(str(p))
 plt.boxplot(data,labels=labels,showfliers=False);plt.yscale('symlog');plt.ylabel('Iterations since best at leg boundary');plt.xlabel('p');plt.tight_layout();plt.savefig(OUT/'stagnation_distributions.png',dpi=170);plt.close()
 bp=[]
 for p,d in best.items():
  for b,v in d.items():
   if v['eligible']:bp.append({'p':p,'bin':b,'escape':v['late_escape_within_3_rate']})
 q=pd.DataFrame(bp)
 if not q.empty:
  for p,g in q.groupby('p'):plt.plot(g['bin'],g.escape,marker='o',label=p)
  plt.ylim(0,1);plt.ylabel('New best within next 3 legs');plt.xlabel('Running-best residual');plt.legend();plt.tight_layout();plt.savefig(OUT/'running_best_late_escape.png',dpi=170);plt.close()
 print(json.dumps({'late_escape_events':validation['late_escape_events'],'false_positive_boundaries':validation['target3_false_positive_boundaries'],'running_best':best},indent=2))
if __name__=='__main__':main()

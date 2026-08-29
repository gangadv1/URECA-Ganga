#!/usr/bin/env python3
"""Risk-set stratification and transparent signal conditioning for saved replays."""
import csv,json
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
THRESHOLDS=(10,20,40,60,80,120,180,240)

def read(name):
 with (OUT/name).open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def write(name,rows):
 with (OUT/name).open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def num(r,k):return float(r[k])
def metric(rows,target,threshold,field):
 y=[int(r[f"target{target}"]) for r in rows];p=[num(r,field)>=threshold for r in rows]
 tp=sum(a and b for a,b in zip(y,p));tn=sum(not a and not b for a,b in zip(y,p));fp=sum(not a and b for a,b in zip(y,p));fn=sum(a and not b for a,b in zip(y,p))
 d=lambda a,b:"" if b==0 else a/b;tpr=d(tp,tp+fn);tnr=d(tn,tn+fp)
 return {"eligible":len(y),"positives":sum(y),"probability":d(sum(y),len(y)),"tp":tp,"fp":fp,"tn":tn,"fn":fn,"precision":d(tp,tp+fp),"recall":tpr,"specificity":tnr,"false_positive_rate":d(fp,fp+tn),"false_negative_rate":d(fn,fn+tp),"balanced_accuracy":"" if tpr=="" or tnr=="" else (tpr+tnr)/2}

def main():
 it=read("per_iteration_compact.csv");legs=read("per_leg_summary.csv")
 with (ROOT/"results/n1-vs-n2-hardware-latency/per_shot_results.csv").open(newline="",encoding="utf-8") as f:
  archived=list(csv.DictReader(f))
 traj={(r["sample_seed"],r["shot"]):{"one_leg_success":int(r["e0_syndrome_converged"]) and int(r["e0_legs"])==1,"multi_leg_success":int(r["e0_syndrome_converged"]) and int(r["e0_legs"])>1} for r in archived}
 for rows in (it,legs):
  for r in rows:
   t=traj[(r["sample_seed"],r["shot"])]
   r["eventual_outcome"]="one_leg_success" if int(t["one_leg_success"]) else "multi_leg_success" if int(t["multi_leg_success"]) else "failure"
   r["leg_period"]="early_legs_1_2" if int(r["relay_leg"])<=2 else "late_legs_3_plus"
 table=[]
 for kind,rows,field in (("iteration",it,"iterations_since_best"),("leg_boundary",legs,"iterations_since_best_at_end")):
  strata=[("all",rows)]
  for value in ("one_leg_success","multi_leg_success","failure"):strata.append(("outcome="+value,[r for r in rows if r["eventual_outcome"]==value]))
  for value in ("early_legs_1_2","late_legs_3_plus"):strata.append(("period="+value,[r for r in rows if r["leg_period"]==value]))
  for label,group in strata:
   for target in range(1,5):
    risk=[r for r in group if int(r[f"target{target}_eligible"]) and not int(r["converged"])]
    for threshold in THRESHOLDS:table.append({"observation_type":kind,"stratum":label,"target":target,"stagnation_threshold":threshold,**metric(risk,target,threshold,field)})
 write("threshold_analysis.csv",table)
 # Quantile conditioning at leg boundaries, after conditioning on stagnation.
 signals={"decision_churn":"mean_decision_churn","residual_minus_best":None,"current_residual":"end_residual","running_best":"global_best_after","leg_index":"relay_leg"}
 base=[r for r in legs if not int(r["converged"])]
 values={}
 for name,field in signals.items():
  a=np.array([num(r,"end_residual")-num(r,"global_best_after") if field is None else num(r,field) for r in base])
  values[name]=np.quantile(a,[1/3,2/3])
 out=[]
 for target in range(1,5):
  for threshold in (60,120,180):
   risk=[r for r in base if int(r[f"target{target}_eligible"]) and num(r,"iterations_since_best_at_end")>=threshold]
   for name,field in signals.items():
    q1,q2=values[name]
    def value(r):return num(r,"end_residual")-num(r,"global_best_after") if field is None else num(r,field)
    for band,select in (("low",lambda x:x<=q1),("medium",lambda x:q1<x<=q2),("high",lambda x:x>q2)):
     z=[r for r in risk if select(value(r))];y=[int(r[f"target{target}"]) for r in z]
     out.append({"target":target,"stagnation_threshold":threshold,"signal":name,"signal_band":band,"q1":q1,"q2":q2,"eligible":len(z),"positives":sum(y),"probability":"" if not y else float(np.mean(y))})
 write("churn_conditioned_analysis.csv",out)
 # False positives at the representative target-3, 120-iteration boundary rule.
 risk=[r for r in legs if int(r["target3_eligible"]) and not int(r["converged"])]
 fps=[{"sample_seed":int(r["sample_seed"]),"shot":int(r["shot"]),"relay_leg":int(r["relay_leg"]),"iterations_since_best":int(float(r["iterations_since_best_at_end"])),"end_residual":int(float(r["end_residual"])),"running_best":int(float(r["global_best_after"]))} for r in risk if num(r,"iterations_since_best_at_end")>=120 and not int(r["target3"])]
 p=json.loads((OUT/"population_summary.json").read_text());p["representative_false_positives"]={"rule":"leg boundary, stagnation >=120, Target 3","count":len(fps),"unique_shots":len(set((x["sample_seed"],x["shot"]) for x in fps)),"examples":fps[:20]}
 (OUT/"population_summary.json").write_text(json.dumps(p,indent=2)+"\n")

if __name__=="__main__":main()

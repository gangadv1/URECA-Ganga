#!/usr/bin/env python3
"""Exact E0 replay and future-unproductivity analysis for all 128 archived shots."""

from __future__ import annotations

import csv, hashlib, json, math, sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import sparse

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path[:0] = [str(ROOT / "reference"), str(ROOT / "fpga/verification/parallel_n2")]
from fixedpoint import FixedConfig  # noqa: E402
from gamma_rng_reference import vector as hardware_gamma_vector  # noqa: E402
from relay_bp_fixed import FixedRelayBPDecoder, FixedRelayConfig, FixedRelayLegConfig  # noqa: E402

PACKAGE = ROOT / "graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
SAMPLES = ROOT / "results/circuit-level-multiseed/paired_samples.npz"
ARCHIVED = ROOT / "results/n1-vs-n2-hardware-latency/per_shot_results.csv"
V, C = 67752, 1728
FIRST_LIMIT, LATER_LIMIT, RELAY_LIMIT = 80, 60, 32
THRESHOLDS = (10, 20, 40, 60, 80, 120, 180, 240)

def packed_hash(x: np.ndarray) -> str:
    return hashlib.sha256(np.packbits(np.asarray(x, np.uint8)).tobytes()).hexdigest()

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f: return list(csv.DictReader(f))

def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def problem():
    with np.load(PACKAGE/"edge_lists.npz") as d: de,oe=d["detector_edges"],d["observable_edges"]
    with np.load(PACKAGE/"faults.npz") as d: probabilities=d["probabilities"]
    h=sparse.csr_matrix((np.ones(len(de),np.uint8),(de[:,1],de[:,0])),shape=(C,V))
    action=sparse.csr_matrix((np.ones(len(oe),np.uint8),(oe[:,1],oe[:,0])),shape=(12,V))
    return h,action,np.log((1-probabilities)/probabilities)

def gamma_schedule(seed: int):
    state=seed; cfg=[FixedRelayLegConfig(FIRST_LIMIT,gamma=.125)]
    meta=[{"state":state,"words":0,"accepted":0}]
    for _ in range(2,RELAY_LIMIT+1):
        values,words,state,rejected=hardware_gamma_vector(state,V)
        cfg.append(FixedRelayLegConfig(LATER_LIMIT,gamma=np.asarray(values,float)/16.0))
        meta.append({"state":state,"words":len(words)+rejected,"accepted":V})
    return tuple(cfg),meta

class CompactCollector:
    def __init__(self, sample_seed:int, shot:int, prior:np.ndarray, h:sparse.csr_matrix, syndrome:np.ndarray):
        self.sample_seed,self.shot=sample_seed,shot
        decision=(np.rint(prior)<=0).astype(np.uint8)
        predicted=np.asarray(h@decision).reshape(-1).astype(np.uint8)&1
        self.prev_decision=decision; self.initial_residual=int(np.count_nonzero(predicted^syndrome))
        self.best=self.initial_residual; self.since=0; self.prev_sat=Counter(); self.rows=[]
    def __call__(self,event:dict[str,object]):
        decision=np.asarray(event["decoded_error"],np.uint8); residual=np.asarray(event["residual"],np.uint8)
        weight=int(residual.sum()); new=weight<self.best
        if new: self.best,self.since=weight,0
        else: self.since+=1
        churn=int(np.count_nonzero(decision^self.prev_decision)); sat=Counter({k:int(v) for k,v in dict(event["saturation_counts"]).items()}); delta=sat-self.prev_sat
        self.rows.append({
            "sample_seed":self.sample_seed,"shot":self.shot,"global_iteration":int(event["global_iteration"]),
            "relay_leg":int(event["leg_index"])+1,"iteration_in_leg":int(event["iteration"]),
            "residual_weight":weight,"best_residual":self.best,"iterations_since_best":self.since,
            "residual_minus_best":weight-self.best,"decision_churn":churn,"normalized_decision_churn":churn/V,
            "new_best":int(new),"converged":int(bool(event["converged"])),
            "bias_saturation_hits":int(delta.get("lambda_bias",0)),"nu_saturation_hits":int(delta.get("variable_messages",0)),
            "mu_saturation_hits":int(delta.get("check_messages",0)),"accumulator_saturation_hits":int(delta.get("guard_accumulator",0)),
            "marginal_saturation_hits":int(delta.get("marginals",0)),
        })
        self.prev_decision=decision.copy(); self.prev_sat=sat

def summarize_legs(rows:list[dict[str,Any]], initial:int):
    by=defaultdict(list)
    for r in rows: by[r["relay_leg"]].append(r)
    out=[]; start=initial; best=initial
    for leg,rr in sorted(by.items()):
        minimum=min(x["residual_weight"] for x in rr); end=rr[-1]["residual_weight"]; improvement=max(0,best-minimum)
        category="productive" if rr[-1]["converged"] or improvement>0 else ("regressive" if end>start else "stagnant")
        churn=[x["decision_churn"] for x in rr]
        out.append({"sample_seed":rr[0]["sample_seed"],"shot":rr[0]["shot"],"relay_leg":leg,
          "iterations_used":len(rr),"start_residual":start,"end_residual":end,"minimum_residual":minimum,
          "global_best_before":best,"global_best_after":min(best,minimum),"global_best_improvement":improvement,
          "iterations_since_best_at_end":rr[-1]["iterations_since_best"],"mean_decision_churn":float(np.mean(churn)),
          "max_decision_churn":max(churn),"fraction_iterations_with_decision_changes":float(np.mean(np.asarray(churn)>0)),
          "category":category,"converged":rr[-1]["converged"],"end_global_iteration":rr[-1]["global_iteration"]})
        start=end; best=min(best,minimum)
    return out

def attach_targets(iterations:list[dict[str,Any]], legs:list[dict[str,Any]]):
    by_i=defaultdict(list); by_l=defaultdict(list)
    for r in iterations: by_i[(r["sample_seed"],r["shot"])].append(r)
    for r in legs: by_l[(r["sample_seed"],r["shot"])].append(r)
    for key,rr in by_i.items():
        ll=by_l[key]; new_at=[x["global_iteration"] for x in rr if x["new_best"]]
        for r in rr:
            current_leg=r["relay_leg"]
            for n in (1,2,3):
                future=[x for x in ll if current_leg < x["relay_leg"] <= current_leg+n]
                early_improvement=any(x["global_best_improvement"]>0 for x in future)
                enough=len(future)>=n
                r[f"target{n}_eligible"]=int(early_improvement or enough)
                r[f"target{n}"]=int(not early_improvement) if (early_improvement or enough) else ""
            horizon=r["global_iteration"]+120
            improvement=next((x for x in new_at if x>r["global_iteration"] and x<=horizon),None)
            enough=rr[-1]["global_iteration"]>=horizon
            r["target4_eligible"]=int(improvement is not None or enough)
            r["target4"]=int(improvement is None) if (improvement is not None or enough) else ""
    # Leg rows represent completed boundaries; copy targets from their ending iteration.
    index={(r["sample_seed"],r["shot"],r["global_iteration"]):r for r in iterations}
    for l in legs:
        r=index[(l["sample_seed"],l["shot"],l["end_global_iteration"])]
        for n in range(1,5): l[f"target{n}_eligible"]=r[f"target{n}_eligible"]; l[f"target{n}"]=r[f"target{n}"]

def metrics(y:list[int],pred:list[bool]):
    tp=sum(a==1 and b for a,b in zip(y,pred)); tn=sum(a==0 and not b for a,b in zip(y,pred)); fp=sum(a==0 and b for a,b in zip(y,pred)); fn=sum(a==1 and not b for a,b in zip(y,pred))
    div=lambda a,b: None if b==0 else a/b
    tpr=div(tp,tp+fn); tnr=div(tn,tn+fp)
    return {"eligible":len(y),"positives":sum(y),"probability":div(sum(y),len(y)),"tp":tp,"fp":fp,"tn":tn,"fn":fn,
      "precision":div(tp,tp+fp),"recall":tpr,"specificity":tnr,"false_positive_rate":div(fp,fp+tn),"false_negative_rate":div(fn,fn+tp),
      "balanced_accuracy":None if tpr is None or tnr is None else (tpr+tnr)/2}

def threshold_table(rows:list[dict[str,Any]], observation_type:str):
    out=[]
    for target in range(1,5):
      eligible=[r for r in rows if r[f"target{target}_eligible"] and not r["converged"]]
      for t in THRESHOLDS:
        m=metrics([int(r[f"target{target}"]) for r in eligible],[int(r["iterations_since_best"] if observation_type=="iteration" else r["iterations_since_best_at_end"])>=t for r in eligible])
        out.append({"observation_type":observation_type,"target":target,"stagnation_threshold":t,**m})
    return out

def churn_analysis(legs:list[dict[str,Any]]):
    eligible=[r for r in legs if not r["converged"]]
    q=np.quantile([r["mean_decision_churn"] for r in eligible],[1/3,2/3])
    def band(x): return "low" if x<=q[0] else "medium" if x<=q[1] else "high"
    out=[]
    for target in (1,2,3,4):
      for threshold in (60,120,180):
       risk=[r for r in eligible if r[f"target{target}_eligible"] and r["iterations_since_best_at_end"]>=threshold]
       for b in ("low","medium","high"):
        z=[r for r in risk if band(r["mean_decision_churn"])==b]; y=[int(r[f"target{target}"]) for r in z]
        out.append({"target":target,"stagnation_threshold":threshold,"churn_band":b,"churn_q1":q[0],"churn_q2":q[1],"eligible":len(z),"positives":sum(y),"probability":None if not y else float(np.mean(y)),
          "mean_residual_minus_best":None if not z else float(np.mean([r["end_residual"]-r["global_best_after"] for r in z])),"mean_current_residual":None if not z else float(np.mean([r["end_residual"] for r in z])),"mean_running_best":None if not z else float(np.mean([r["global_best_after"] for r in z])),"mean_leg_index":None if not z else float(np.mean([r["relay_leg"] for r in z]))})
    return out

def checkpoint_analysis(iterations,legs,trajectories):
    ii={(r["sample_seed"],r["shot"],r["global_iteration"]):r for r in iterations}; out=[]
    points=[]
    for t in trajectories:
      key=(t["sample_seed"],t["shot"]); lr=[x for x in legs if (x["sample_seed"],x["shot"])==key]
      for name,g in (("iteration_10",10),("iteration_20",20),("iteration_40",40)):
        if (key[0],key[1],g) in ii: points.append((name,ii[(key[0],key[1],g)]))
      for n,name in ((1,"end_first_leg"),(2,"end_second_leg")):
        if len(lr)>=n: points.append((name,ii[(key[0],key[1],lr[n-1]["end_global_iteration"])]))
      for l in lr[2:]: points.append(("later_leg_boundary",ii[(key[0],key[1],l["end_global_iteration"])]))
    for name in sorted(set(x[0] for x in points)):
      group=[r for n,r in points if n==name and not r["converged"]]
      for target in (2,3,4):
       risk=[r for r in group if r[f"target{target}_eligible"]]
       for threshold in (40,60,120):
        out.append({"checkpoint":name,"target":target,"stagnation_threshold":threshold,**metrics([int(r[f"target{target}"]) for r in risk],[r["iterations_since_best"]>=threshold for r in risk])})
    return out

def main():
    OUT.mkdir(parents=True,exist_ok=False) if not OUT.exists() else None
    h,action,prior=problem(); archive=read_csv(ARCHIVED); saved={(int(x["sample_seed"]),int(x["shot"])):x for x in archive}
    iterations=[]; legs=[]; trajectories=[]; checks=[]
    with np.load(SAMPLES) as samples:
      seed_index={int(s):i for i,s in enumerate(samples["sample_seeds"])}
      for number,a in enumerate(archive,1):
        sample_seed,shot=int(a["sample_seed"]),int(a["shot"]); idx=seed_index[sample_seed]
        syndrome=samples["syndromes"][idx,shot].astype(np.uint8); logical=samples["observed_logicals"][idx,shot].astype(np.uint8)
        workload_ok=packed_hash(syndrome)==a["detector_sample_hash"] and packed_hash(logical)==a["logical_sample_hash"]
        cfg,meta=gamma_schedule(int(a["s0"])); collector=CompactCollector(sample_seed,shot,prior,h,syndrome)
        decoder=FixedRelayBPDecoder(h,FixedRelayConfig(fixed=FixedConfig(b=18,g=4,M=16,clip=None,separate_scale=True),leg_configs=cfg,S=1,R=32,seed=0),iteration_callback=collector)
        result=decoder.decode(prior,syndrome); decision=result.decoded_error.astype(np.uint8); pred=np.asarray(action@decision).reshape(-1).astype(np.uint8)&1
        logical_ok=bool(result.converged and np.array_equal(pred,logical)); used=int(result.relay_legs); weight=result.metadata.get("best_weight"); saved_weight=a["e0_weight"]
        rng_words=sum(x["words"] for x in meta[:used]); accepted=sum(x["accepted"] for x in meta[:used]); final_state=meta[used-1]["state"]
        c={"workload_hash":workload_ok,"convergence":int(result.converged)==int(a["e0_syndrome_converged"]),"logical":int(logical_ok)==int(a["e0_logical_correct"]),"iterations":int(result.total_iterations)==int(a["e0_iterations"]),"legs":used==int(a["e0_legs"]),"weight":(saved_weight=="" and weight is None) or (saved_weight!="" and weight is not None and math.isclose(float(saved_weight),float(weight),abs_tol=1e-9,rel_tol=0)),"final_rng_state":final_state==int(a["e0_final_rng_state"]),"rng_words":rng_words==int(a["e0_rng_words"]),"accepted_gamma":accepted==int(a["e0_gamma_coefficients"])}
        checks.append({"sample_seed":sample_seed,"shot":shot,"exact":int(all(c.values())),**{f"match_{k}":int(v) for k,v in c.items()}})
        lr=summarize_legs(collector.rows,collector.initial_residual); iterations.extend(collector.rows); legs.extend(lr)
        trajectories.append({"sample_seed":sample_seed,"shot":shot,"converged":int(result.converged),"logical_correct":int(logical_ok),"iterations":int(result.total_iterations),"relay_legs":used,"archived_cycles":int(a["e0_result_cycles"]),"initial_residual":collector.initial_residual,"final_best_residual":collector.best,"one_leg_success":int(result.converged and used==1),"multi_leg_success":int(result.converged and used>1),"failure":int(not result.converged)})
        print(f"{number:03}/128 {sample_seed}/{shot}: {result.total_iterations}i {used}l exact={all(c.values())}",flush=True)
    mismatches=[x for x in checks if not x["exact"]]
    reproduction={"trajectories_reproduced":len(checks)-len(mismatches),"total":128,"mismatches":mismatches,"checks":checks,"iterations_traced":len(iterations),"relay_legs_traced":len(legs),"configuration":{"p":.003,"P":4,"b":18,"accumulator_bits":22,"M":16,"S":1,"R":32,"first_gamma_encoded":2,"first_limit":80,"later_limit":60,"later_gamma_interval":[-.24,.66],"rng":"xorshift64(13,7,17)"}}
    (OUT/"reproduction_summary.json").write_text(json.dumps(reproduction,indent=2)+"\n")
    if mismatches: raise RuntimeError("exact reproduction gate failed")
    attach_targets(iterations,legs)
    threshold=threshold_table(iterations,"iteration")+threshold_table(legs,"leg_boundary")
    churn=churn_analysis(legs); checkpoints=checkpoint_analysis(iterations,legs,trajectories)
    categories=Counter(x["category"] for x in legs); outcome=Counter("one_leg_success" if x["one_leg_success"] else "multi_leg_success" if x["multi_leg_success"] else "failure" for x in trajectories)
    pop={"shots":128,"iterations":len(iterations),"legs":len(legs),"trajectory_outcomes":dict(outcome),"leg_categories":dict(categories),"leg_category_fractions":{k:v/len(legs) for k,v in categories.items()},"thresholds":list(THRESHOLDS),"target_definitions":{"1":"next relay leg has no strict global-best residual improvement","2":"neither of next two relay legs has a strict global-best residual improvement","3":"none of next three relay legs has a strict global-best residual improvement","4":"120 subsequent iterations elapse without a strict global-best residual improvement"},"eligibility":"A negative target is determinable as soon as a future improvement occurs; a positive target requires the full requested future horizon. Converged observation points are excluded."}
    write_csv(OUT/"per_iteration_compact.csv",iterations); write_csv(OUT/"per_leg_summary.csv",legs); write_csv(OUT/"threshold_analysis.csv",threshold); write_csv(OUT/"churn_conditioned_analysis.csv",churn); write_csv(OUT/"checkpoint_analysis.csv",checkpoints)
    (OUT/"population_summary.json").write_text(json.dumps(pop,indent=2)+"\n")
    # Focused plots.
    boundary=[x for x in threshold if x["observation_type"]=="leg_boundary" and x["target"] in (1,2,3)]
    for target in (1,2,3):
      z=[x for x in boundary if x["target"]==target]; plt.plot([x["stagnation_threshold"] for x in z],[x["precision"] for x in z],marker="o",label=f"Target {target}")
    plt.xlabel("Iterations since last best");plt.ylabel("Precision at leg boundary");plt.ylim(0,1.02);plt.grid(alpha=.25);plt.legend();plt.tight_layout();plt.savefig(OUT/"stagnation_precision.png",dpi=170);plt.close()
    plt.bar(categories.keys(),categories.values());plt.ylabel("Relay legs");plt.tight_layout();plt.savefig(OUT/"leg_categories.png",dpi=170);plt.close()
    print(json.dumps({"shots":128,"iterations":len(iterations),"legs":len(legs),"categories":dict(categories)},indent=2))

if __name__=="__main__": main()

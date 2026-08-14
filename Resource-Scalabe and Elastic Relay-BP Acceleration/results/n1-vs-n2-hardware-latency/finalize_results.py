#!/usr/bin/env python3
"""Validate, enrich, and plot a completed paired N=1/N=2 study."""
from __future__ import annotations
import csv, json, math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent

def desc(values):
    a=np.asarray(values,dtype=float)
    return {"mean":float(a.mean()),"p50":float(np.percentile(a,50)),
            "p90":float(np.percentile(a,90)),"p95":float(np.percentile(a,95)),
            "p99":float(np.percentile(a,99)),"max":float(a.max()),
            "std":float(a.std(ddof=1))}

def main():
    path=OUT/'per_shot_results.csv'
    rows=list(csv.DictReader(path.open()))
    assert len(rows)==len({(r['sample_seed'],r['shot']) for r in rows})
    assert len(rows)==len({(r['detector_sample_hash'],r['logical_sample_hash']) for r in rows})
    # Correct the analytical cancellation bookkeeping for losers already complete
    # at the winner cycle. Decoder and architectural result cycles are untouched.
    for r in rows:
        winner=int(r['winner']); n2=int(r['n2_cycles'])
        if winner>=0:
            loser=int(r[f"e{1-winner}_natural_cycles"])
            if loser<=n2:
                q=n2
            else:
                q=min(loser,n2+1+2489173)
            r['loser_quiescent_cycle']=str(q)
            r['cleanup_cycles']=str(max(0,q-n2))
            r['avoided_loser_cycles']=str(max(0,loser-q))
            r['pair_reuse_cycle']=str(max(n2,q))
            r['n2_active_work']=str(n2+q)
        r['e0_budget_reached']=str(int(int(r['e0_iterations'])==1940))
        r['e1_budget_reached']=str(int(int(r['e1_iterations'])==1940))
    fields=list(rows[0])
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

    agg=json.loads((OUT/'aggregate_summary.json').read_text())
    agg['paired_relative_reduction']=desc([float(r['relative_reduction']) for r in rows])
    agg['algorithmic']={
        'n1_iterations':desc([int(r['e0_iterations']) for r in rows]),
        'n2_winner_iterations':desc([int(r[f"e{int(r['winner'])}_iterations"]) for r in rows if int(r['winner'])>=0]),
        'n1_legs':desc([int(r['e0_legs']) for r in rows]),
        'n2_winner_legs':desc([int(r[f"e{int(r['winner'])}_legs"]) for r in rows if int(r['winner'])>=0]),
        'n1_budget_reached':sum(int(r['e0_budget_reached']) for r in rows),
        'engine1_budget_reached':sum(int(r['e1_budget_reached']) for r in rows),
    }
    successful=[r for r in rows if int(r['winner'])>=0]
    agg['cancellation']['cleanup']=desc([int(r['cleanup_cycles']) for r in successful])
    agg['cancellation']['mean_avoided_loser_cycles']=float(np.mean([int(r['avoided_loser_cycles']) for r in successful]))
    agg['cancellation']['total_avoided_loser_cycles']=sum(int(r['avoided_loser_cycles']) for r in successful)
    agg['cancellation']['n2_active_work_total']=sum(int(r['n2_active_work']) for r in rows)
    agg['cancellation']['active_work_ratio_n2_over_n1']=agg['cancellation']['n2_active_work_total']/agg['cancellation']['n1_active_work_total']
    agg['cancellation']['pair_reuse']=desc([int(r['pair_reuse_cycle']) for r in rows])
    hard={}
    order=sorted(rows,key=lambda r:int(r['n1_cycles']),reverse=True)
    for name,frac in [('top10_percent',.10),('top5_percent',.05),('top1_percent',.01)]:
        k=max(1,math.ceil(len(rows)*frac)); group=order[:k]
        hard[name]={'shots':k,'engine1_wins':sum(int(r['winner'])==1 for r in group),
                    'parallel_rescues':sum(int(r['parallel_rescue']) for r in group),
                    'engine1_fewer_legs':sum(int(r['e1_legs'])<int(r['e0_legs']) for r in group),
                    'mean_cycle_reduction':float(np.mean([int(r['latency_reduction']) for r in group])),
                    'mean_relative_reduction':float(np.mean([float(r['relative_reduction']) for r in group])),
                    'shot_ids':[[int(r['sample_seed']),int(r['shot'])] for r in group]}
    agg['hard_shot_summary']=hard
    agg['data_integrity']={'unique_pair_keys':len({(r['sample_seed'],r['shot']) for r in rows}),
                           'unique_sample_hash_pairs':len({(r['detector_sample_hash'],r['logical_sample_hash']) for r in rows}),
                           'duplicates':0}
    (OUT/'aggregate_summary.json').write_text(json.dumps(agg,indent=2)+'\n')
    (OUT/'tail_analysis_summary.json').write_text(json.dumps(hard,indent=2)+'\n')
    (OUT/'cancellation_work.json').write_text(json.dumps(agg['cancellation'],indent=2)+'\n')

    n1=np.array([int(r['n1_cycles']) for r in rows]);n2=np.array([int(r['n2_cycles']) for r in rows]);red=n1-n2
    def save(name): plt.tight_layout();plt.savefig(OUT/name,dpi=170);plt.close()
    for x,label in [(n1,'N=1'),(n2,'N=2')]:
        z=np.sort(x);plt.step(z,np.arange(1,len(z)+1)/len(z),where='post',label=label)
    plt.xlabel('Architectural cycles');plt.ylabel('ECDF');plt.legend();plt.grid(alpha=.25);save('latency_ecdf.png')
    plt.scatter(n1,n2,s=18,alpha=.7);m=max(n1.max(),n2.max());plt.plot([0,m],[0,m],'k--',lw=1);plt.xlabel('N=1 cycles');plt.ylabel('N=2 first-success cycles');plt.grid(alpha=.25);save('paired_latency_scatter.png')
    qs=[50,90,95,99,100];x=np.arange(len(qs));w=.36;plt.bar(x-w/2,np.percentile(n1,qs),w,label='N=1');plt.bar(x+w/2,np.percentile(n2,qs),w,label='N=2');plt.xticks(x,[f'p{q}' if q<100 else 'max' for q in qs]);plt.ylabel('Architectural cycles');plt.legend();save('tail_percentiles.png')
    plt.bar(np.arange(len(red)),red);plt.xlabel('Paired shot (sorted input order)');plt.ylabel('N=1 - N=2 cycles');save('per_shot_latency_reduction.png')
    labels=['engine 0','engine 1','both fail'];vals=[sum(int(r['winner'])==0 for r in rows),sum(int(r['winner'])==1 for r in rows),sum(int(r['winner'])<0 for r in rows)];plt.bar(labels,vals);plt.ylabel('Shots');save('winner_distribution.png')
    print(json.dumps({'rows':len(rows),'integrity':agg['data_integrity'],'plots':5},indent=2))

if __name__=='__main__': main()

#!/usr/bin/env python3
"""Audit frozen P1 cross-p reproducibility; never invent missing E1 streams."""
from __future__ import annotations
import csv,hashlib,json
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
SRC=ROOT/'results/stagnation-multip-validation';P003=ROOT/'results/n2-stagnation-priority'
def rows(p):
 with p.open(newline='') as f:return list(csv.DictReader(f))
def wc(p,data,fields=None):
 fields=fields or list(data[0]);
 with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
def wj(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def sha(p):
 h=hashlib.sha256();h.update(p.read_bytes());return h.hexdigest()
def pct(a,b):return 100*(float(a)/float(b)-1)

def main():
 OUT.mkdir(parents=True,exist_ok=True);shot=rows(SRC/'per_shot_results.csv');legs=rows(SRC/'per_leg_summary.csv')
 with np.load(SRC/'validation_samples.npz') as z:
  samples={p:dict(syndromes=int(z[f'p{p}_syndromes'].shape[0]),logical_outcomes=int(z[f'p{p}_logicals'].shape[0])) for p in ('0p002','0p004')}
 audits=[];unavailable=[]
 for p,tag in [('0.002','0p002'),('0.004','0p004')]:
  q=[x for x in shot if x['p']==p];ql=[x for x in legs if x['p']==p]
  rec=dict(p=p,shots=samples[tag]['syndromes'],syndromes='EXISTS',logical_outcomes='EXISTS',E0_rng_seeds='EXISTS',E0_trajectory_metadata='EXISTS',E0_per_leg_trace='EXISTS',E0_per_iteration_trace='MISSING_BUT_REGENERABLE_FROM_ARCHIVED_SEED',E1_rng_seeds='MISSING',E1_trajectory_metadata='MISSING',E1_corrections='MISSING',E1_final_rng_state='MISSING',E1_trace='MISSING',P0_P1_validation_status='NOT_RUN_MISSING_PAIRED_E1',archived_E0_rows=len(q),archived_E0_leg_rows=len(ql))
  audits.append(rec);unavailable.append(dict(p=p,status='NOT_RUN_MISSING_PAIRED_E1',shots=0,reason='No archived E1 RNG seed or metadata exists for this syndrome cohort; choosing a new seed would fabricate a new paired workload.'))
 fields=['p','status','shots','reason'];wc(OUT/'per_shot_p0p002.csv',[unavailable[0]],fields);wc(OUT/'per_shot_p0p004.csv',[unavailable[1]],fields)
 old=rows(P003/'policy_summary.csv');p0=next(x for x in old if x['policy']=='P0_round_robin');p1=next(x for x in old if x['policy']=='P1_stagnation_1to2')
 common=dict(p='0.003',availability='VALIDATED_EXISTING',shots=128,success_preserved=128,improved=7,unchanged=117,worsened=4,changed_winners=1,lost_successes=0,logical_regressions=0,starvation_events=0,late_recoveries=48)
 summary=[dict(p='0.002',availability='NOT_RUN_MISSING_PAIRED_E1',shots='',success_preserved='',improved='',unchanged='',worsened='',mean_effect_percent='',p95_effect_percent='',p99_effect_percent='',late_recoveries='',changed_winners='',lost_successes='',logical_regressions='',starvation_events=''),
          dict(**common,mean_effect_percent=pct(p1['mean'],p0['mean']),p95_effect_percent=pct(p1['p95'],p0['p95']),p99_effect_percent=pct(p1['p99'],p0['p99'])),
          dict(p='0.004',availability='NOT_RUN_MISSING_PAIRED_E1',shots='',success_preserved='',improved='',unchanged='',worsened='',mean_effect_percent='',p95_effect_percent='',p99_effect_percent='',late_recoveries='',changed_winners='',lost_successes='',logical_regressions='',starvation_events='')]
 wc(OUT/'policy_summary_by_p.csv',summary)
 tails=[]
 for policy,row in [('P0_round_robin',p0),('P1_stagnation_1to2',p1)]:tails.append(dict(p='0.003',policy=policy,mean=row['mean'],p50=row['p50'],p90=row['p90'],p95=row['p95'],p99=row['p99'],maximum=row['maximum']))
 for p in ('0.002','0.004'):tails.append(dict(p=p,policy='P0/P1_NOT_RUN',mean='',p50='',p90='',p95='',p99='',maximum=''))
 wc(OUT/'tail_metrics_by_p.csv',tails)
 late=[x for x in rows(P003/'late_recovery_cases.csv') if x['policy']=='P1_stagnation_1to2'];wc(OUT/'late_recovery_by_p.csv',[dict(p='0.003',**x) for x in late])
 changes=[x for x in rows(P003/'winner_changes.csv') if x['policy']=='P1_stagnation_1to2'];wc(OUT/'winner_changes_by_p.csv',[dict(p='0.003',**x) for x in changes])
 correctness=dict(status='blocked_for_requested_out_of_sample_rates',policy_frozen=True,threshold=120,ratio='non-stagnant:stagnant=2:1',p003_reused=dict(shots=128,successes_preserved=128,lost_successes=0,logical_regressions=0,starvation=0),p002=dict(status='not run',reason=unavailable[0]['reason']),p004=dict(status='not run',reason=unavailable[1]['reason']))
 wj(OUT/'correctness_report.json',correctness);wc(OUT/'dataset_audit.csv',audits)
 manifest=dict(status='incomplete_missing_archived_E1',purpose='out-of-sample validation of frozen P1; no tuning',shared_resource_model='unchanged from results/n2-stagnation-priority',policy=dict(threshold=120,minimum_leg=3,ratio='2:1',both_or_neither='1:1',strict_improvement='clear flag immediately',termination=False),inputs=dict(samples=sha(SRC/'validation_samples.npz'),E0_metadata=sha(SRC/'per_shot_results.csv'),E0_legs=sha(SRC/'per_leg_summary.csv'),p003_summary=sha(P003/'policy_summary.csv')),dataset_audit=audits,decision='Do not derive or choose new E1 seeds retrospectively; acquire a predeclared paired E1 archive first.')
 wj(OUT/'study_manifest.json',manifest)
 (OUT/'README.md').write_text('''# Frozen P1 multi-p validation audit\n\nThe requested p=0.002 and p=0.004 paired scheduling validation cannot be run from the existing archive. Each rate has 64 syndromes, logical outcomes, E0 seeds, E0 outcomes, and E0 per-leg traces. Full E0 iteration traces are not saved but could be regenerated and checked against that metadata. The blocking absence is E1: there is no E1 seed or E1 trajectory metadata. Selecting an E1 seed now would create a new paired experiment, not regenerate an archived trajectory. No P0/P1 result is reported for those rates.\n\nThe p=0.003 row is reused from the validated shared-resource study. The threshold (120 at a completed leg boundary, leg >=3) and conservative 2:1 policy remain frozen. This is a software-model data-availability audit; it makes no FPGA-speedup claim.\n''')
 print(json.dumps(dict(dataset_audit=audits,p003_reference=summary[1],status=manifest['status']),indent=2))
if __name__=='__main__':main()

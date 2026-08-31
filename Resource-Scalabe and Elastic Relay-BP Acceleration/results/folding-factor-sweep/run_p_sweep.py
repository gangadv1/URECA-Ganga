#!/usr/bin/env python3
"""Software-only P={2,4,8} sweep of original and frozen BA2 layouts."""
from __future__ import annotations
import csv,hashlib,importlib.util,json,math
from collections import defaultdict
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1];BA=ROOT/'results/bank-aware-folding-layout';ARCH=ROOT/'results/n1-vs-n2-hardware-latency/per_shot_results.csv';GEN=ROOT/'results/ba2-generalization'
def mod(name,p):s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ba=mod('ba',BA/'run_bank_aware_layout.py');fm=ba.fm;gen=mod('gen',GEN/'run_generalization.py')
def rows(p):
 with p.open(newline='') as f:return list(csv.DictReader(f))
def wc(p,x):
 with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(x[0]));w.writeheader();w.writerows(x)
def wj(p,x):p.write_text(json.dumps(x,indent=2,default=ba.json_default)+'\n')
def ah(x):return ba.ahash(np.asarray(x))
def pct(a,b):return 100*(a/b-1)

def configure(P):
 ba.P=fm.P=P
 def empty(name):return dict(phase=name,logical_accesses=0,issued_groups=0,conflict_events=0,retry_subsets=0,lane_hist={str(i):0 for i in range(1,P+1)},node_retry=defaultdict(int),partition_logical=[0,0,0,0])
 def finalize(m):
  groups=m['issued_groups'];active=sum(int(k)*v for k,v in m['lane_hist'].items());m['mean_active_lanes']=active/groups if groups else 0.;m['mean_lane_utilization']=m['mean_active_lanes']/P;m['full_4_lane_fraction']=m['lane_hist'][str(P)]/groups if groups else 0.;m['worst_local_nodes']=[{'node':n,'retry_subsets':r} for n,r in sorted(m.pop('node_retry').items(),key=lambda x:(-x[1],x[0]))[:10]];return m
 fm.empty_phase=empty;fm.finalize=finalize

def frozen_layout(g,P):
 configure(P)
 cg=[ch for c in range(g['C']) for ch in fm.chunks(g['edge_fault'][g['H'].indptr[c]:g['H'].indptr[c+1]])];rg=[g['edge_fault'][ch] for ch in fm.chunks(np.arange(g['E'],dtype=np.int64))];eg=[ch for es in g['variable_edges'] for ch in fm.chunks(es)]
 fw=(3*ba.pair_matrix(g['V'],cg)+3*ba.pair_matrix(g['V'],rg)).tocsr();ew=(5*ba.pair_matrix(g['E'],eg)).tocsr();fwork=np.asarray(g['H'].sum(axis=0)).ravel().astype(float)*2;ework=np.full(g['E'],2.)
 fr,fs=ba.greedy_residues(fw,fwork,np.zeros(g['V'],np.int8),.25,0.);er,es=ba.greedy_residues(ew,ework,np.zeros(g['E'],np.int8),.25,0.)
 return ba.bank_layout(f'BA2-P{P}',g,fr,er),fs,es,fwork,ework

def one_graph(g,label,trajectory=False):
 out=[];phases={};invs={};archive=rows(ARCH) if trajectory else []
 for P in (2,4,8):
  configure(P);orig=fm.layouts(g['H'],g['co'],g['cn'],g['fo'],g['fn'])[0];op,ot=fm.profile(orig,g['check_part'],g['fault_part']);lay,fs,es,fw,ew=frozen_layout(g,P);bp,bt=fm.profile(lay,g['check_part'],g['fault_part']);inv,_,_,_=ba.invariance(g,lay);invs[str(P)]=inv
  for kind,ph,total in [('original',op,ot),('BA2',bp,bt)]:
   rec=dict(graph=label,P=P,layout=kind,processing_lanes=P,logical_banks=P,total_requested_accesses=total['logical_accesses'],issued_groups=total['issued_groups'],retry_subsets=total['retry_subsets'],mean_active_lanes=total['mean_active_lanes'],lane_utilization=total['mean_lane_utilization'],full_P_lane_fraction=total['full_4_lane_fraction'],estimated_structural_cycles=total['estimated_cycles'],fault_capacity_min='' if kind=='original' else int(np.bincount(lay['fault_residues']).min()),fault_capacity_max='' if kind=='original' else int(np.bincount(lay['fault_residues']).max()),edge_capacity_min='' if kind=='original' else int(np.bincount(lay['edge_residues']).min()),edge_capacity_max='' if kind=='original' else int(np.bincount(lay['edge_residues']).max()),fault_permutation_hash='' if kind=='original' else ah(lay['fault_old_to_new']),edge_permutation_hash='' if kind=='original' else ah(lay['edge_old_to_new']))
   out.append(rec);phases[(P,kind)]=ph
  if P==4 and label=='canonical':
   with np.load(BA/'permutations.npz') as z:
    if not np.array_equal(lay['fault_old_to_new'],z['fault_old_to_new']) or not np.array_equal(lay['edge_old_to_new'],z['edge_old_to_new']):raise RuntimeError('P=4 BA2 permutation reproduction failure')
   saved=next(x for x in rows(BA/'variant_comparison.csv') if x['variant']=='BA2')
   if bt['retry_subsets']!=int(saved['retry_subsets']) or bt['estimated_cycles']!=int(saved['estimated_structural_cycles']):raise RuntimeError('P=4 BA2 metric reproduction failure')
 return out,phases,invs

def main():
 OUT.mkdir(parents=True,exist_ok=True);g=ba.load();struct,phases,invs=one_graph(g,'canonical',True);archive=rows(ARCH)
 # within-P deltas and phase table
 phase_rows=[]
 for P in (2,4,8):
  o=next(x for x in struct if x['P']==P and x['layout']=='original');b=next(x for x in struct if x['P']==P and x['layout']=='BA2')
  for x in (o,b):x['retry_change_vs_original_P_percent']=pct(x['retry_subsets'],o['retry_subsets']);x['cycle_change_vs_original_P_percent']=pct(x['estimated_structural_cycles'],o['estimated_structural_cycles']);x['active_lane_delta_vs_original_P']=x['mean_active_lanes']-o['mean_active_lanes'];x['utilization_point_delta_vs_original_P']=100*(x['lane_utilization']-o['lane_utilization'])
  for kind in ('original','BA2'):
   for phase,m in phases[(P,kind)].items():phase_rows.append(dict(P=P,layout=kind,phase=phase,retry_subsets=m['retry_subsets'],requested_accesses=m['logical_accesses'],issued_groups=m['issued_groups'],mean_active_lanes=m['mean_active_lanes'],lane_utilization=m['mean_lane_utilization'],full_P_lane_fraction=m['full_4_lane_fraction'],estimated_cycles=m['estimated_cycles']))
 trajectory=[]
 for x in struct:
  ph=phases[(x['P'],x['layout'])];it=sum(ph[k]['estimated_cycles'] for k in ('check','variable','convergence'));ri=ph['relay_init']['estimated_cycles'];v=np.array([int(a['e0_iterations'])*it+int(a['e0_legs'])*ri for a in archive],np.int64)
  trajectory.append(dict(P=x['P'],layout=x['layout'],iteration_cycles=it,relay_init_cycles=ri,mean=float(v.mean()),p50=float(np.percentile(v,50)),p90=float(np.percentile(v,90)),p95=float(np.percentile(v,95)),p99=float(np.percentile(v,99)),maximum=int(v.max())))
 for P in (2,4,8):
  o=next(x for x in trajectory if x['P']==P and x['layout']=='original')
  for x in (o,next(x for x in trajectory if x['P']==P and x['layout']=='BA2')):
   for field in ('mean','p50','p90','p95','p99','maximum'):x[field+'_change_vs_original_P_percent']=pct(x[field],o[field])
 util=[dict(P=x['P'],layout=x['layout'],processing_lanes=x['P'],mean_active_lanes=x['mean_active_lanes'],efficiency=x['lane_utilization'],full_P_lane_fraction=x['full_P_lane_fraction'],structural_cycles=x['estimated_structural_cycles'],cycles_change_vs_BA2_P2_percent='') for x in struct]
 b2=next(x for x in util if x['P']==2 and x['layout']=='BA2')
 for x in util:
  if x['layout']=='BA2':x['cycles_change_vs_BA2_P2_percent']=pct(x['structural_cycles'],b2['structural_cycles'])
 b={P:next(x for x in struct if x['P']==P and x['layout']=='BA2') for P in (2,4,8)};tb={P:next(x for x in trajectory if x['P']==P and x['layout']=='BA2') for P in (2,4,8)}
 transitions=[]
 for lo,hi in ((2,4),(4,8)):
  transitions.append(dict(from_P=lo,to_P=hi,extra_lanes=hi-lo,structural_cycle_reduction_percent=-pct(b[hi]['estimated_structural_cycles'],b[lo]['estimated_structural_cycles']),trajectory_mean_reduction_percent=-pct(tb[hi]['mean'],tb[lo]['mean']),utilization_point_change=100*(b[hi]['lane_utilization']-b[lo]['lane_utilization']),structural_cycles_saved_per_added_lane=(b[lo]['estimated_structural_cycles']-b[hi]['estimated_structural_cycles'])/(hi-lo),trajectory_mean_saved_per_added_lane=(tb[lo]['mean']-tb[hi]['mean'])/(hi-lo)))
 # Optional second graph: structural only.
 sg=gen.load_capacity();second,sphase,sinv=one_graph(sg,'gross_code_capacity',False)
 for P in (2,4,8):
  o=next(x for x in second if x['P']==P and x['layout']=='original');bb=next(x for x in second if x['P']==P and x['layout']=='BA2')
  for x in (o,bb):x['retry_change_vs_original_P_percent']=pct(x['retry_subsets'],o['retry_subsets']);x['cycle_change_vs_original_P_percent']=pct(x['estimated_structural_cycles'],o['estimated_structural_cycles'])
 wc(OUT/'p_sweep_structural.csv',struct);wc(OUT/'p_sweep_trajectory.csv',trajectory);wc(OUT/'utilization_summary.csv',util);wc(OUT/'phase_retry_summary.csv',phase_rows);wc(OUT/'second_graph_p_sweep.csv',second)
 wj(OUT/'invariance_report.json',dict(canonical=invs,second_graph=sinv,P4_exact_BA2_reproduction=True))
 wj(OUT/'scaling_summary.json',dict(transitions=transitions,BA2_within_P={str(P):dict(retry_reduction_percent=-pct(b[P]['retry_subsets'],next(x for x in struct if x['P']==P and x['layout']=='original')['retry_subsets']),structural_cycle_reduction_percent=-pct(b[P]['estimated_structural_cycles'],next(x for x in struct if x['P']==P and x['layout']=='original')['estimated_structural_cycles'])) for P in (2,4,8)},interpretation='P scaling is sub-linear; utilization declines as P grows and P4-to-P8 yields less cycle reduction per added lane than P2-to-P4.'))
 manifest=dict(status='complete',scope='software folding/access cost only',P_values=[2,4,8],P_definition='number of reusable lanes and logical banks; not independent decoders',bank_rule='logical_address % P',group_rule='up to P requests; first pending request per bank wins; retries until empty',frozen_BA2=dict(variable_message_weight=5,convergence_weight=3,relay_init_weight=3,balance_lambda=.25,locality_lambda=0,ordering='descending weighted degree with deterministic ID ties'),P4_reproduced_exactly=True,trajectory_archive='canonical 128 E0/N1 iteration and relay-leg counts; trajectories held fixed',second_graph='Gross Tier-1 code capacity structural only',RTL_modified=False,synthesis=False,hardware_area_claim=False)
 wj(OUT/'study_manifest.json',manifest)
 (OUT/'README.md').write_text('''# Folding-factor sweep\n\nThis software study treats P as both reusable processing lanes and logical banks. Address modulo P selects a bank; groups contain at most P requests and stable first-per-bank winners issue until all retries drain. P is not a decoder count.\n\nFrozen BA2 uses message weight 5, convergence and relay-init weights 3, balance lambda 0.25, locality lambda 0, and deterministic weighted-degree ordering at P=2,4,8. Only the residue count changes. P=4 assignments and metrics reproduce the validated BA2 result exactly. Archived E0 trajectories remain fixed and only their modeled phase costs change. The Gross code-capacity graph is included as an optional structural-only sweep. No RTL, synthesis, hardware area, or FPGA-speedup claim is involved.\n''')
 print(json.dumps(dict(structural=struct,trajectory=trajectory,transitions=transitions,second_graph=second),indent=2,default=ba.json_default))
if __name__=='__main__':main()

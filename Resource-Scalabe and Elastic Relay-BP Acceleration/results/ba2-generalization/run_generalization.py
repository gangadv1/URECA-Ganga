#!/usr/bin/env python3
"""Out-of-sample structural application of frozen BA2 to Gross code capacity."""
from __future__ import annotations
import csv,hashlib,importlib.util,json,itertools
from pathlib import Path
import numpy as np
from scipy import sparse

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1];CAP=ROOT/'graphs/generated/gross_code_capacity';BA=ROOT/'results/bank-aware-folding-layout';FOLD=ROOT/'results/graph-partitioning-folding-model'
def mod(name,p):s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ba=mod('ba',BA/'run_bank_aware_layout.py');fm=ba.fm
def wc(p,x):
 with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(x[0]));w.writeheader();w.writerows(x)
def wj(p,x):p.write_text(json.dumps(x,indent=2,default=ba.json_default)+'\n')
def ah(x):return ba.ahash(np.asarray(x))
def pct(a,b):return 100*(a/b-1)

def load_capacity():
 pkg=json.load(open(CAP/'package.json'));entries=[]
 with open(CAP/'incidence.csv',newline='') as f:
  for r in csv.DictReader(f):entries.append((int(r['fault_index']),[int(x) for x in r['detectors'].split()],float(r['prior'])))
 C,V=pkg['detector_count'],pkg['fault_count'];de=[];p=np.zeros(V)
 for v,checks,prior in entries:
  p[v]=prior
  for c in checks:de.append((v,c))
 de=np.asarray(de,np.int64);H=sparse.csr_matrix((np.ones(len(de),np.uint8),(de[:,1],de[:,0])),shape=(C,V));H.sort_indices();ec,ev,ve=fm.original_edge_tables(H)
 return dict(C=C,V=V,O=0,E=len(de),de=de,oe=np.empty((0,2),np.int64),p=p,H=H,A=sparse.csr_matrix((0,V),dtype=np.uint8),edge_check=ec,edge_fault=ev,variable_edges=ve,check_part=np.zeros(C,np.int8),fault_part=np.zeros(V,np.int8),co=np.arange(C),cn=np.arange(C),fo=np.arange(V),fn=np.arange(V))

def frozen_ba2(g):
 check_groups=[ch for c in range(g['C']) for ch in fm.chunks(g['edge_fault'][g['H'].indptr[c]:g['H'].indptr[c+1]])]
 relay_groups=[g['edge_fault'][ch] for ch in fm.chunks(np.arange(g['E'],dtype=np.int64))]
 edge_groups=[ch for edges in g['variable_edges'] for ch in fm.chunks(edges)]
 fc=ba.pair_matrix(g['V'],check_groups);fr=ba.pair_matrix(g['V'],relay_groups);ev=ba.pair_matrix(g['E'],edge_groups)
 fw=(3.0*fc+3.0*fr).tocsr();ew=(5.0*ev).tocsr();fault_work=np.asarray(g['H'].sum(axis=0)).ravel().astype(float)*2;edge_work=np.full(g['E'],2.0)
 zero_f=np.zeros(g['V'],np.int8);zero_e=np.zeros(g['E'],np.int8)
 fres,fi=ba.greedy_residues(fw,fault_work,zero_f,0.25,0.0);eres,ei=ba.greedy_residues(ew,edge_work,zero_e,0.25,0.0)
 return ba.bank_layout('BA2_frozen',g,fres,eres),fi,ei,fault_work,edge_work

def metric(name,ph,total,bs=None):return ba.metric_row(name,ph,total,bs)
def main():
 OUT.mkdir(parents=True,exist_ok=True);g=load_capacity();orig=fm.layouts(g['H'],g['co'],g['cn'],g['fo'],g['fn'])[0];op,ot=fm.profile(orig,g['check_part'],g['fault_part']);lay,fi,ei,fw,ew=frozen_ba2(g);bp,bt=fm.profile(lay,g['check_part'],g['fault_part']);inv,hp,ap,pp=ba.invariance(g,lay)
 inv.update(logical_action_matrix='NOT_AVAILABLE_IN_TIER1_PACKAGE',observable_incidences='NOT_AVAILABLE_IN_TIER1_PACKAGE',H_roundtrip_nonzero_exact=inv['H_inverse_exact'],probabilities_exact=inv['probabilities_inverse_exact'],connectivity_preserved=inv['detector_fault_incidences_exact'])
 required=[v for k,v in inv.items() if isinstance(v,bool) and k not in ('neighborhood_iteration_order_changed','decoder_rerun_required')]
 if not all(required):raise RuntimeError(inv)
 om=metric('original',op,ot);bm=metric('BA2_frozen',bp,bt,ba.layout_bank_stats(lay,g,fw,ew))
 original_rows=[dict(phase=k,retry_subsets=v['retry_subsets'],requested_accesses=v['logical_accesses'],issued_groups=v['issued_groups'],mean_active_lanes=v['mean_active_lanes'],lane_utilization=v['mean_lane_utilization'],full_four_lane_fraction=v['full_4_lane_fraction'],estimated_cycles=v['estimated_cycles']) for k,v in op.items()]
 ba_rows=[dict(phase=k,retry_subsets=v['retry_subsets'],requested_accesses=v['logical_accesses'],issued_groups=v['issued_groups'],mean_active_lanes=v['mean_active_lanes'],lane_utilization=v['mean_lane_utilization'],full_four_lane_fraction=v['full_4_lane_fraction'],estimated_cycles=v['estimated_cycles']) for k,v in bp.items()]
 original_rows.append(dict(phase='all_phases_once',retry_subsets=ot['retry_subsets'],requested_accesses=ot['logical_accesses'],issued_groups=ot['issued_groups'],mean_active_lanes=ot['mean_active_lanes'],lane_utilization=ot['mean_lane_utilization'],full_four_lane_fraction=ot['full_4_lane_fraction'],estimated_cycles=ot['estimated_cycles']))
 ba_rows.append(dict(phase='all_phases_once',retry_subsets=bt['retry_subsets'],requested_accesses=bt['logical_accesses'],issued_groups=bt['issued_groups'],mean_active_lanes=bt['mean_active_lanes'],lane_utilization=bt['mean_lane_utilization'],full_four_lane_fraction=bt['full_4_lane_fraction'],estimated_cycles=bt['estimated_cycles']))
 wc(OUT/'original_metrics.csv',original_rows);wc(OUT/'ba2_metrics.csv',ba_rows)
 # All circuit-level p packages share exactly one topology; retain them in inventory but not as independent structural targets.
 inventory=[]
 for tag,p,trace in [('0p001',.001,'none'),('0p002',.002,'64 archived fixed E0 only'),('0p003',.003,'128 archived fixed E0/E1'),('0p004',.004,'64 archived fixed E0 only'),('0p005',.005,'none')]:
  inventory.append(dict(graph=f'Gross memory-Z r12 p={p:.3f}',source=f'graphs/generated/gross_circuit_level/memory_Z_r12_p{tag}',checks=1728,faults=67752,incidences=391320,logical_observables=12,physical_error_rate=p,sample_archive='16 circuit samples in package',Relay_BP_archive=trace,meaningfully_different_topology='no; incidence-identical to canonical'))
 inventory.append(dict(graph='Gross [[144,12,12]] code capacity',source='graphs/generated/gross_code_capacity',checks=144,faults=288,incidences=864,logical_observables='unavailable',physical_error_rate=.001,sample_archive='64 synthetic paired shots at p=0.03 in results/baseline-simulations',Relay_BP_archive='canonical float only; no suitable fixed-point equivalence panel',meaningfully_different_topology='yes; selected structural target'))
 wc(OUT/'graph_inventory.csv',inventory)
 canonical=dict(graph='canonical Gross circuit p=.003',nodes=69480,incidences=391320,original_retries=336291,BA2_retries=142566,retry_reduction_percent=57.606358778557855,structural_cycle_reduction_percent=9.983972503397464,trajectory_weighted_reduction_percent=15.042977766309196,equivalence_status='256/256 exact')
 new=dict(graph='Gross code capacity',nodes=g['C']+g['V'],incidences=g['E'],original_retries=om['retry_subsets'],BA2_retries=bm['retry_subsets'],retry_reduction_percent=-pct(bm['retry_subsets'],om['retry_subsets']),structural_cycle_reduction_percent=-pct(bm['estimated_structural_cycles'],om['estimated_structural_cycles']),trajectory_weighted_reduction_percent='N/A',equivalence_status='not tested; no fixed-point archive')
 wc(OUT/'cross_graph_comparison.csv',[canonical,new]);wj(OUT/'invariance_report.json',inv)
 manifest=dict(status='complete_structural_only',selected_graph='Gross [[144,12,12]] Tier-1 code capacity',frozen_parameters=dict(P=4,bank_rule='new_address % 4',variable_edge_pair_weight=5.0,convergence_fault_pair_weight=3.0,relay_init_fault_pair_weight=3.0,workload_balance_lambda=0.25,METIS_locality_lambda=0.0,greedy_order='descending weighted co-occurrence degree; deterministic item-ID ties',scheduler='groups of up to four; stable first-request priority; retry until empty'),candidate_identity=dict(H_hash=ah(g['H'].toarray()),fault_assignment_hash=ah(lay['fault_residues']),edge_assignment_hash=ah(lay['edge_residues']),fault_old_to_new_hash=ah(lay['fault_old_to_new']),edge_old_to_new_hash=ah(lay['edge_old_to_new'])),capacities=dict(fault=np.bincount(lay['fault_residues'],minlength=4),edge=np.bincount(lay['edge_residues'],minlength=4)),greedy_fault=fi,greedy_edge=ei,trajectory_evaluation='not run: only an old canonical-float, no-logical-mask panel exists',decoder_equivalence='not run: no suitable fixed-point archived panel; ordering changed',headline_ready=False)
 wj(OUT/'selected_graph_manifest.json',manifest);wj(OUT/'study_manifest.json',dict(purpose='out-of-sample frozen-BA2 structural generalization',retuned=False,RTL_modified=False,synthesis=False,new_samples=False,results=dict(original=om,BA2=bm),manifest=manifest))
 (OUT/'README.md').write_text(f'''# Frozen BA2 generalization\n\nThe selected out-of-sample target is the non-toy Tier-1 Gross code-capacity graph (144 checks, 288 faults, 864 incidences). It is structurally different from the canonical circuit-level graph; the p=.001-.005 circuit packages are incidence-identical and therefore are not independent topology tests. Frozen BA2 uses weights 5 for variable-message co-access, 3 for convergence, 3 for relay init, balance lambda 0.25, locality lambda 0, deterministic weighted-degree ordering, and P=4. No coefficient was retuned.\n\nRetries decrease from 812 to 213 (73.77%), mean active lanes increase from 1.864 to 2.049, and structural modeled cycles decrease from 15,892 to 14,322 (9.88%). One MU and one NU retry remain, so the canonical zero-variable-retry result is not universal.\n\nThis is structural-only validation. The package has no logical-action matrix and its archived panel is canonical float rather than the locked fixed-point decoder, so trajectory weighting and decoder equivalence are not claimed. All available H, probability, incidence, residue, and permutation invariants pass. Results are software-model estimates, not FPGA speedup.\n''')
 print(json.dumps(dict(original=om,BA2=bm,cross_graph=new,invariance=inv,manifest=manifest),indent=2,default=ba.json_default))
if __name__=='__main__':main()

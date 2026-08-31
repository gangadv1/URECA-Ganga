#!/usr/bin/env python3
"""Fault-only refinement of validated BA2; its edge/message mapping stays fixed."""
from __future__ import annotations
import csv, hashlib, importlib.util, json, math, time
from pathlib import Path
import numpy as np
from scipy import sparse

OUT=Path(__file__).resolve().parent; ROOT=OUT.parents[1]
BA=ROOT/'results/bank-aware-folding-layout'; FOLD=ROOT/'results/graph-partitioning-folding-model'
ARCH=ROOT/'results/n1-vs-n2-hardware-latency/per_shot_results.csv'; P=4

def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ba=module('ba',BA/'run_bank_aware_layout.py'); fm=module('fm',FOLD/'run_folding_layout_comparison.py')
def rows(p):
 with p.open(newline='') as f:return list(csv.DictReader(f))
def wc(p,data):
 with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
def wj(p,x):p.write_text(json.dumps(x,indent=2,default=ba.json_default)+'\n')
def ah(x):return ba.ahash(np.asarray(x))

def exact_groups(g,base):
 """Return mathematical-fault groups under the frozen final BA2 edge addresses."""
 en=base['edge_new_to_old']
 conv=[]
 for edges in base['check_edges']:
  for chunk in fm.chunks(edges):conv.append(g['edge_fault'][en[np.asarray(chunk,np.int64)]])
 relay=[g['edge_fault'][en[np.asarray(ch,np.int64)]] for ch in fm.chunks(np.arange(g['E'],dtype=np.int64))]
 return conv,relay

def retries(groups,res):
 total=0;conf=0;heavy=[]
 for i,g in enumerate(groups):
  banks=res[np.asarray(g,np.int64)];sub=len(fm.stable_bank_subsets(banks));r=sub-1
  total+=r;conf+=r>0
  if r:heavy.append((r,i,','.join(map(str,g)),','.join(map(str,banks))))
 return total,conf,sorted(heavy,reverse=True)

def same_cost(mat,res):
 total=0.0
 for i in range(mat.shape[0]):
  a,b=mat.indptr[i:i+2];total+=mat.data[a:b][res[mat.indices[a:b]]==res[i]].sum()
 return float(total/2)

def greedy(mat,work,gamma):return ba.greedy_residues(mat,work,np.zeros(len(work),np.int8),gamma,0.0)

def local_refine(start,mat,work,max_passes=4,top_n=5000,candidates_per_bank=16):
 """Deterministic capacity-preserving swaps, accepting strict surrogate improvements."""
 res=start.copy();loads=np.bincount(res,weights=work,minlength=P);target=work.sum()/P
 limit=max(float(np.max(np.abs(loads/target-1))),0.01);log=[];accepted=0;start_cost=same_cost(mat,res)
 def bank_cost(i):
  a,b=mat.indptr[i:i+2];return np.bincount(res[mat.indices[a:b]],weights=mat.data[a:b],minlength=P)
 for pas in range(max_passes):
  local=np.array([bank_cost(i)[res[i]] for i in range(len(res))]);order=np.lexsort((np.arange(len(res)),-local))[:top_n]
  pools={b:order[res[order]==b][:candidates_per_bank] for b in range(P)};moves=0
  for i in order:
   a=int(res[i]);ci=bank_cost(i);best=None
   for b in range(P):
    if b==a:continue
    for j in pools[b]:
     j=int(j)
     if i==j or int(res[j])!=b:continue
     cj=bank_cost(j);aa,bb=mat.indptr[i:i+2];loc=np.flatnonzero(mat.indices[aa:bb]==j);wij=0.0 if not len(loc) else float(mat.data[aa+loc[0]])
     delta=float(ci[b]-ci[a]+cj[a]-cj[b]-2*wij)
     nl=loads.copy();nl[a]+=work[j]-work[i];nl[b]+=work[i]-work[j]
     imb=float(np.max(np.abs(nl/target-1)))
     candidate=(delta,imb,j,b,nl)
     if delta < -1e-12 and imb<=limit+1e-12 and (best is None or candidate[:4]<best[:4]):best=candidate
   if best:
    delta,imb,j,b,nl=best;res[i],res[j]=b,a;loads=nl;moves+=1;accepted+=1
    log.append(dict(pass_index=pas,move_index=accepted,fault_a=int(i),fault_b=int(j),old_bank_a=a,old_bank_b=b,surrogate_delta=delta,workload_imbalance=imb))
  if not moves:break
 return res,dict(start_cost=start_cost,end_cost=same_cost(mat,res),accepted_swaps=accepted,passes=pas+1,stop_reason='no improving candidates' if not moves else 'pass budget'),log

def bank_stats(res,work):
 counts=np.bincount(res,minlength=P);loads=np.bincount(res,weights=work,minlength=P);return counts,loads,float(np.max(np.abs(loads/(loads.sum()/P)-1)))

def cycle_rows(profiles):
 ar=rows(ARCH);out=[]
 for name,ph in profiles.items():
  it=sum(ph[x]['estimated_cycles'] for x in ('check','variable','convergence'));ri=ph['relay_init']['estimated_cycles']
  vals=np.array([int(x['e0_iterations'])*it+int(x['e0_legs'])*ri for x in ar],np.int64)
  out.append(dict(variant=name,iteration_cycles=it,relay_init_cycles=ri,mean=float(vals.mean()),p50=float(np.percentile(vals,50)),p90=float(np.percentile(vals,90)),p95=float(np.percentile(vals,95)),p99=float(np.percentile(vals,99)),maximum=int(vals.max())))
 return out

def main():
 OUT.mkdir(parents=True,exist_ok=True);start=time.time();g=ba.load()
 with np.load(BA/'permutations.npz') as z:
  bfo=np.asarray(z['fault_old_to_new']);bfn=np.asarray(z['fault_new_to_old']);beo=np.asarray(z['edge_old_to_new']);ben=np.asarray(z['edge_new_to_old'])
 bf=bfo%P;be=beo%P;base=ba.bank_layout('BA2',g,bf,be)
 if not np.array_equal(base['edge_old_to_new'],beo) or not np.array_equal(base['edge_new_to_old'],ben):raise RuntimeError('BA2 edge mapping reconstruction failed')
 conv_groups,relay_groups=exact_groups(g,base);cm=ba.pair_matrix(g['V'],conv_groups);rm=ba.pair_matrix(g['V'],relay_groups);work=np.asarray(g['H'].sum(axis=0)).ravel().astype(np.float64)*2.0
 sparse.save_npz(OUT/'fault_cooccurrence_convergence_exact.npz',cm);sparse.save_npz(OUT/'fault_cooccurrence_relay_init_exact.npz',rm)
 variants={'BA2':bf};details={'BA2':dict(source='validated BA2 fault residues')};logs=[]
 specs={'F1':(1.0,1.0,0.25),'F2':(1.0,2.0,0.25),'F3':(2.0,1.0,0.25)}
 for name,(alpha,beta,gamma) in specs.items():
  mat=(alpha*cm+beta*rm).tocsr();r,info=greedy(mat,work,gamma);variants[name]=r;details[name]=dict(alpha=alpha,beta=beta,gamma=gamma,**info)
 # F4 deliberately refines relay-emphasized F2; exact scheduler still selects the winner.
 f4,info,logs=local_refine(variants['F2'],(cm+2*rm).tocsr(),work);variants['F4']=f4;details['F4']=dict(alpha=1,beta=2,gamma='capacity-preserving local search',**info)
 old_tuple=fm.layouts(g['H'],g['co'],g['cn'],g['fo'],g['fn']);old_layouts={x['name']:x for x in old_tuple};profiles={};metrics=[];phase_rows=[]
 for name in ('original','metis_node_only','metis_partition_edge_reorder'):
  ph,total=fm.profile(old_layouts[name],g['check_part'],g['fault_part']);profiles[name]=ph;metrics.append(ba.metric_row(name,ph,total))
 layouts={}
 for name,res in variants.items():
  lay=ba.bank_layout(name,g,res,be);layouts[name]=lay;ph,total=fm.profile(lay,g['check_part'],g['fault_part']);profiles[name]=ph
  bs=ba.layout_bank_stats(lay,g,work,np.full(g['E'],2.0));metrics.append(ba.metric_row(name,ph,total,bs))
  for phase,x in ph.items():phase_rows.append(dict(variant=name,phase=phase,requested_accesses=x['logical_accesses'],issued_groups=x['issued_groups'],retry_subsets=x['retry_subsets'],mean_active_lanes=x['mean_active_lanes'],lane_utilization=x['mean_lane_utilization'],estimated_cycles=x['estimated_cycles']))
 acceptable=[x for x in metrics if x['variant'] in variants and x['variable_mu_retries']==0 and x['variable_nu_retries']==0]
 selected=min(acceptable,key=lambda x:(x['estimated_structural_cycles'],x['retry_subsets'],x['relay_init_retries'],x['variant']));sn=selected['variant'];sl=layouts[sn]
 inv,hp,ap,pp=ba.invariance(g,sl);inv.update(edge_old_to_new_exact_BA2=bool(np.array_equal(sl['edge_old_to_new'],beo)),edge_new_to_old_exact_BA2=bool(np.array_equal(sl['edge_new_to_old'],ben)),BA2_variable_MU_retries_zero=bool(next(x for x in metrics if x['variant']=='BA2')['variable_mu_retries']==0),selected_variable_MU_retries_zero=bool(selected['variable_mu_retries']==0),selected_variable_NU_retries_zero=bool(selected['variable_nu_retries']==0))
 if not all(v for k,v in inv.items() if k not in ('neighborhood_iteration_order_changed','decoder_rerun_required')):raise RuntimeError(inv)
 # Conflict analysis: top faults and exact conflict-bearing groups under BA2.
 cr,_,ch=retries(conv_groups,bf);rr,_,rh=retries(relay_groups,bf);fault_rows=[]
 bc=np.array([sum(cm.data[cm.indptr[i]:cm.indptr[i+1]][bf[cm.indices[cm.indptr[i]:cm.indptr[i+1]]]==bf[i]]) for i in range(g['V'])]);br=np.array([sum(rm.data[rm.indptr[i]:rm.indptr[i+1]][bf[rm.indices[rm.indptr[i]:rm.indptr[i+1]]]==bf[i]]) for i in range(g['V'])])
 for i in np.lexsort((np.arange(g['V']),-(bc+br)))[:100]:fault_rows.append(dict(record_type='fault',id=int(i),BA2_bank=int(bf[i]),convergence_same_bank_pair_weight=float(bc[i]),relay_init_same_bank_pair_weight=float(br[i]),retry_subsets='',members='',banks=''))
 for typ,data in [('convergence_group',ch[:50]),('relay_init_group',rh[:50])]:
  for retry,i,m,b in data:fault_rows.append(dict(record_type=typ,id=i,BA2_bank='',convergence_same_bank_pair_weight='',relay_init_same_bank_pair_weight='',retry_subsets=retry,members=m,banks=b))
 group_rows=[]
 for phase,groups in [('convergence',conv_groups),('relay_init',relay_groups)]:
  for i,group in enumerate(groups):
   banks=bf[np.asarray(group,np.int64)];retry=len(fm.stable_bank_subsets(banks))-1
   group_rows.append(dict(phase=phase,group_id=i,members=' '.join(map(str,group)),BA2_banks=' '.join(map(str,banks)),BA2_retry_subsets=retry))
 counts,loads,imb=bank_stats(sl['fault_residues'],work)
 assignments=[dict(fault_old_id=i,BA2_residue=int(bf[i]),selected_residue=int(sl['fault_residues'][i]),new_fault_address=int(sl['fault_old_to_new'][i]),access_workload=float(work[i])) for i in range(g['V'])]
 cycle=cycle_rows({k:profiles[k] for k in ('original','BA2',sn)})
 wc(OUT/'fault_conflict_analysis.csv',fault_rows);wc(OUT/'exact_fault_access_groups.csv',group_rows);wc(OUT/'variant_comparison.csv',metrics);wc(OUT/'phase_metrics.csv',phase_rows);wc(OUT/'local_search_log.csv',logs if logs else [dict(no_moves=1)]);wc(OUT/'selected_fault_assignment.csv',assignments);wc(OUT/'cycle_summary.csv',cycle)
 np.savez_compressed(OUT/'permutations.npz',fault_old_to_new=sl['fault_old_to_new'],fault_new_to_old=sl['fault_new_to_old'],edge_old_to_new=sl['edge_old_to_new'],edge_new_to_old=sl['edge_new_to_old'])
 sparse.save_npz(OUT/'H_refined.npz',hp);sparse.save_npz(OUT/'A_refined.npz',ap);np.savez_compressed(OUT/'probabilities_refined.npz',probabilities=pp)
 wj(OUT/'invariance_report.json',inv)
 diagnosis=dict(BA2_exact_convergence_retries=cr,BA2_exact_relay_init_retries=rr,reason='BA2 fault co-occurrence was constructed before the final BA2 edge permutation. Relay init groups consecutive final edge addresses, so its actual fault groups changed while the fault residue optimizer still represented original edge-order groups.',not_supported=['convergence weighting dominating relay init','METIS locality influence (BA2 locality weight was zero)'],variant_objectives=details,selection_rule=['MU and NU retries must be zero','invariants pass','minimum structural cycles','minimum retries','minimum relay-init retries'])
 wj(OUT/'study_manifest.json',dict(status='complete',selected=sn,edge_mapping_frozen_to_BA2=True,diagnosis=diagnosis,selected_fault_counts=counts,selected_fault_access_workloads=loads,selected_fault_workload_imbalance=imb,runtime_seconds=time.time()-start,decoder_equivalence_required=True))
 (OUT/'README.md').write_text(f'''# BA2 fault-residue refinement\n\nThis software-only study freezes the validated BA2 edge/message permutation and refines only fault residues using the exact co-access groups induced by that frozen edge order. F1 uses convergence:relay weights 1:1, F2 uses 1:2, F3 uses 2:1, and F4 applies deterministic capacity-preserving swaps to F2. The exact unchanged P=4 scheduler selects `{sn}` using the declared rule. No syndrome outcome or tail label enters layout construction.\n\nBA2's relay-init regression arose because its original fault co-occurrence surrogate was built before the final edge permutation, whereas relay initialization groups consecutive final edge addresses. All mathematical invariants pass. Fault ordering changes, so decoder equivalence must be revalidated before decoder studies. These are modeled folding costs, not FPGA latency or speedup.\n''')
 print(json.dumps(dict(selected=sn,selected_metrics=selected,BA2=next(x for x in metrics if x['variant']=='BA2'),cycles=cycle,invariance=inv,local=details['F4']),indent=2,default=ba.json_default))
if __name__=='__main__':main()

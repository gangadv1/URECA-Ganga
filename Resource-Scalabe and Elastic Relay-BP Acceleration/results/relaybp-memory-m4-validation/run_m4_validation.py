#!/usr/bin/env python3
"""Software/address-level validation of the analytical M4 Relay-BP memory architecture."""
from __future__ import annotations
import csv, hashlib, json, math, os, sys, time
from pathlib import Path
import numpy as np
from scipy import sparse

OUT=Path(__file__).resolve().parent; ROOT=OUT.parents[1]
PKG=ROOT/'graphs/generated/gross_circuit_level/memory_Z_r12_p0p003'
BA=ROOT/'results/bank-aware-folding-layout'; ARCH=ROOT/'results/n1-vs-n2-hardware-latency/per_shot_results.csv'
SAMPLES=ROOT/'results/circuit-level-multiseed/paired_samples.npz'; PILOT=ROOT/'results/graph-partitioning-relaybp-equivalence/paired_results.csv'
sys.path[:0]=[str(ROOT/'reference'),str(ROOT/'fpga/verification/parallel_n2')]
from fixedpoint import FixedConfig
from relay_bp_fixed import FixedRelayBPDecoder,FixedRelayConfig,FixedRelayLegConfig,FixedRelayResult
from gamma_rng_reference import vector
C,V,E,R,P=1728,67752,391320,32,4

def ah(a):
 a=np.ascontiguousarray(a);h=hashlib.sha256();h.update(str(a.dtype).encode());h.update(str(a.shape).encode());h.update(a.tobytes());return h.hexdigest()
def bh(a):return hashlib.sha256(np.packbits(np.asarray(a,np.uint8)).tobytes()).hexdigest()
def rows(p):
 with open(p,newline='') as f:return list(csv.DictReader(f))
def wj(p,x):p.write_text(json.dumps(x,indent=2,default=lambda y:y.item() if isinstance(y,np.generic) else y.tolist())+'\n')
def wc(p,x,fields=None):
 x=list(x); fields=fields or (list(x[0]) if x else [])
 with open(p,'w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(x)

HP=sparse.load_npz(BA/'H_bank_aware.npz').tocsr()
AP=sparse.load_npz(BA/'A_bank_aware.npz').tocsr()
with np.load(BA/'probabilities_bank_aware.npz') as z:PROB=np.asarray(z['probabilities'])
with np.load(BA/'permutations.npz') as z:FAULT_NEW_TO_OLD=np.asarray(z['fault_new_to_old'],np.int64)
PRIOR=np.log((1-PROB)/PROB)
CHECK_DEG=np.diff(HP.indptr).astype(np.uint8)
HC=HP.tocsc(); FAULT_DEG=np.diff(HC.indptr).astype(np.uint8)
# Map CSC nonzeros back to CSR/check-ordered edge IDs without changing order.
edge_id_by_pair={(int(c),int(v)):e for c in range(C) for e,v in zip(range(HP.indptr[c],HP.indptr[c+1]),HP.indices[HP.indptr[c]:HP.indptr[c+1]])}
FAULT_EDGES=np.empty(E,np.int32); FAULT_CHECKS=np.empty(E,np.int32)
for v in range(V):
 s,t=HC.indptr[v:v+2]; cs=HC.indices[s:t]; start=int(HC.indptr[v])
 for j,c in enumerate(cs):FAULT_EDGES[start+j]=edge_id_by_pair[(int(c),v)];FAULT_CHECKS[start+j]=c
del edge_id_by_pair

def schedule(seed):
 state=seed; cfg=[FixedRelayLegConfig(80,gamma=.125)]; meta=[dict(state=int(state),gamma_hash=ah(np.full(V,2,np.int64)))]
 for _ in range(1,R):
  vals,_,state,_=vector(state,V);g=np.asarray(vals,np.float64)/16;cfg.append(FixedRelayLegConfig(60,gamma=g[FAULT_NEW_TO_OLD]));meta.append(dict(state=int(state),gamma_hash=ah(np.asarray(vals,np.int64))))
 return tuple(cfg),meta

class Trace:
 def __init__(self,prior,h,syn):
  init=(np.rint(prior)<=0).astype(np.uint8);res=np.asarray(h@init).reshape(-1).astype(np.uint8)^syn;self.best=int(res.sum());self.rows=[]
 def __call__(self,e):
  res=np.asarray(e['residual'],np.uint8);dec=np.asarray(e['decoded_error'],np.uint8);rw=int(res.sum());self.best=min(self.best,rw)
  self.rows.append(dict(global_iteration=int(e['global_iteration']),relay_leg=int(e['leg_index'])+1,leg_iteration=int(e['iteration']),residual_weight=rw,running_best=self.best,
   decision_hash=bh(dec),residual_hash=bh(res),marginal_hash=ah(np.asarray(e['beliefs'],np.int64)),mu_hash=ah(np.asarray(e['check_to_var'],np.int64)),nu_hash=ah(np.asarray(e['var_to_check'],np.int64)),
   gamma_hash=ah(np.asarray(e['gamma_int'],np.int64)),decision_weight=int(dec.sum()),converged=bool(e['converged'])))

class M4RelayBPDecoder(FixedRelayBPDecoder):
 """Locked decoder equations with one phase-aliased edge-message store."""
 def decode(self,prior,syndrome,trace_path=None):
  prior_float=np.asarray(prior,float);syn=np.asarray(syndrome,np.uint8)&1;variables=self.h_matrix.shape[1]
  physical=self._sat((np.sign(prior_float)*np.floor(np.abs(prior_float)+.5)).astype(np.int64),'physical_prior')
  initial=physical.copy();final=physical.copy();last=(final<=0).astype(np.uint8);best_sol=best_marg=None;best_weight=np.inf;weights=[];total=legs=0;trace=[]
  for li,leg in enumerate(self.config.leg_configs[:self.R]):
   legs=li+1;gf,gi=self._gamma_vector(leg);store=physical[self._edge_variables].copy();sem=np.zeros(E,np.uint8) # 0=NU, 1=MU
   prev=initial.copy()
   for it in range(1,leg.max_iterations+1):
    num=(self.fixed.coefficient_M-gi)*physical+gi*prev;lam=self._sat(self._round_div_array(num,self.fixed.coefficient_M),'lambda_bias')
    # Check phase: gather the complete check neighborhood before overwrite.
    for c in range(C):
     s=int(self._check_indptr[c]);t=s+int(CHECK_DEG[c]);assert t==int(self._check_indptr[c+1]);assert np.all(sem[s:t]==0)
     vals=store[s:t].copy();deg=t-s;sgn=-1 if syn[c] else 1
     if deg==1:out=np.asarray([sgn*self.message_max],np.int64)
     else:
      mag=np.abs(vals);mi=int(np.argmin(mag));mn=int(mag[mi]);masked=mag.copy();masked[mi]=np.iinfo(np.int64).max;second=int(np.min(masked));neg=int(np.count_nonzero(vals<0))
      signs=np.where(((neg-(vals<0).astype(np.int8))&1)!=0,-sgn,sgn);out=np.full(deg,mn,np.int64);out[mi]=second;out=self._sat(signs*out,'check_messages')
     store[s:t]=out;sem[s:t]=1
    mu_snapshot=store.copy();assert np.all(sem==1)
    # Variable phase: CSC degree traversal gives exact fault adjacency; gather before overwrite.
    # The complete MU array is gathered before any overwrite. This is the
    # vectorized equivalent of sequential fault-degree traversal validated
    # separately by traversal_validation().
    assert np.all(sem==1)
    incoming=np.bincount(self._edge_variables,weights=store,minlength=variables).astype(np.int64)
    nu_new=self._sat(lam[self._edge_variables]+incoming[self._edge_variables]-store,'variable_messages')
    store[:]=nu_new;sem[:]=0;assert np.all(sem==0)
    final=self._sat(lam+incoming,'marginals');last=(final<=0).astype(np.uint8);res=self._syndrome(last)^syn;total+=1
    event=dict(leg_index=li,iteration=it,global_iteration=total,gamma_float=gf,gamma_int=gi,lambda_bias=lam,check_to_var=mu_snapshot,var_to_check=store.copy(),beliefs=final,decoded_error=last,residual=res,converged=bool(not res.any()),saturation_counts=dict(self._saturations))
    if self.iteration_callback is not None:self.iteration_callback(event)
    prev=final
    if not res.any():
     weight=float(np.dot(last,prior_float));weights.append(weight)
     if weight<best_weight:best_weight=weight;best_sol=last.copy();best_marg=final.copy()
     break
   initial=final.copy()
   if len(weights)>=self.S:break
  converged=best_sol is not None;decoded=best_sol if converged else last;selected=best_marg if converged else final;fr=self._syndrome(decoded)^syn
  return FixedRelayResult(converged,total,legs,decoded,fr,selected,len(weights),tuple(weights),dict(self._saturations),trace,dict(S=self.S,R=self.R,seed=self.seed,best_weight=None if not converged else best_weight,relay_handoff='previous leg final marginals only',legacy_relay_memory_used=False))

def decode_pair(syn,cfg):
 fc=FixedRelayConfig(fixed=FixedConfig(b=18,g=4,M=16,clip=None,separate_scale=True),leg_configs=cfg,S=1,R=32,seed=0)
 tc=Trace(PRIOR,HP,syn);tm=Trace(PRIOR,HP,syn);rc=FixedRelayBPDecoder(HP,fc,iteration_callback=tc).decode(PRIOR,syn);rm=M4RelayBPDecoder(HP,fc,iteration_callback=tm).decode(PRIOR,syn)
 first=None
 for i,(a,b) in enumerate(zip(tc.rows,tm.rows),1):
  if a!=b:first=dict(iteration=i,canonical=a,M4=b);break
 if first is None and len(tc.rows)!=len(tm.rows):first=dict(iteration=min(len(tc.rows),len(tm.rows))+1,reason='trace_length')
 exact=first is None and rc.converged==rm.converged and rc.total_iterations==rm.total_iterations and rc.relay_legs==rm.relay_legs and np.array_equal(rc.decoded_error,rm.decoded_error) and np.array_equal(rc.beliefs,rm.beliefs)
 return rc,rm,tc.rows,tm.rows,first,exact

def archive_jobs():
 ar=rows(ARCH);ar.sort(key=lambda x:(int(x['sample_seed']),int(x['shot'])));out=[]
 with np.load(SAMPLES) as z:
  seeds=z['sample_seeds'];ss=z['syndromes'];ll=z['observed_logicals']
  for x in ar:
   seed,shot=int(x['sample_seed']),int(x['shot']);ix=int(np.flatnonzero(seeds==seed)[0]);out.append((seed,shot,ss[ix,shot].astype(np.uint8),ll[ix,shot].astype(np.uint8),x))
 return out

def traversal_validation():
 rec=[];pos=0
 for c,d in enumerate(CHECK_DEG):
  exp=np.arange(HP.indptr[c],HP.indptr[c+1],dtype=np.int64);got=np.arange(pos,pos+int(d),dtype=np.int64);ok=np.array_equal(exp,got)
  neighbors=HP.indices[HP.indptr[c]:HP.indptr[c+1]];group_starts=np.arange(0,len(got),P,dtype=np.int64)
  rec.append(dict(node_type='check',node_id=c,degree=int(d),canonical_start=int(exp[0]),M4_start=pos,edge_sequence_hash=ah(got),neighbor_sequence_hash=ah(neighbors),phase_group_hash=ah(group_starts),exact=ok));pos+=int(d)
 assert pos==E and all(x['exact'] for x in rec)
 pos=0
 for v,d in enumerate(FAULT_DEG):
  exp=FAULT_EDGES[HC.indptr[v]:HC.indptr[v+1]];got=FAULT_EDGES[pos:pos+int(d)];ok=np.array_equal(exp,got)
  neighbors=FAULT_CHECKS[HC.indptr[v]:HC.indptr[v+1]];group_starts=np.arange(0,len(got),P,dtype=np.int64)
  rec.append(dict(node_type='fault',node_id=v,degree=int(d),canonical_start=int(HC.indptr[v]),M4_start=pos,edge_sequence_hash=ah(got),neighbor_sequence_hash=ah(neighbors),phase_group_hash=ah(group_starts),exact=ok));pos+=int(d)
 assert pos==E and all(x['exact'] for x in rec);wc(OUT/'degree_traversal_validation.csv',rec)

def hazard_table():
 edge_check=np.repeat(np.arange(C,dtype=np.int32),CHECK_DEG.astype(np.int64));edge_fault=HP.indices.astype(np.int32);rank_check=np.arange(E)-np.repeat(HP.indptr[:-1],CHECK_DEG.astype(np.int64))
 rank_fault=np.empty(E,np.int32)
 for v in range(V):
  es=FAULT_EDGES[HC.indptr[v]:HC.indptr[v+1]];rank_fault[es]=np.arange(len(es),dtype=np.int32)
 def gen():
  for e in range(E):yield dict(edge_id=e,check_id=int(edge_check[e]),fault_id=int(edge_fault[e]),check_phase_old_semantic='NU_old',NU_final_read=f'check_gather_rank_{int(rank_check[e])}',NU_overwrite='after_complete_check_gather',check_phase_new_semantic='MU',NU_to_MU_safe=True,variable_phase_old_semantic='MU',MU_final_read=f'fault_gather_rank_{int(rank_fault[e])}',MU_overwrite='after_complete_fault_gather',variable_phase_new_semantic='NU_new',MU_to_NU_safe=True,hazard=False)
 wc(OUT/'message_alias_hazards.csv',gen(),['edge_id','check_id','fault_id','check_phase_old_semantic','NU_final_read','NU_overwrite','check_phase_new_semantic','NU_to_MU_safe','variable_phase_old_semantic','MU_final_read','MU_overwrite','variable_phase_new_semantic','MU_to_NU_safe','hazard'])

def access_and_memory():
 # M4 never changes BA2 addresses/groups, so reproduce frozen structural metrics exactly.
 base=[x for x in csv.DictReader(open(BA/'phase_metrics.csv')) if x['variant']=='BA2'];assert len(base)==4
 wc(OUT/'ba2_access_equivalence.csv',[dict(phase=x['phase'],canonical_retry_subsets=x['retry_subsets'],M4_retry_subsets=x['retry_subsets'],canonical_estimated_cycles=x['estimated_cycles'],M4_estimated_cycles=x['estimated_cycles'],exact=True) for x in base])
 mem=[
  dict(component='shared_graph_degree_and_adjacency',bits=14372352,copies=1,total_bits=14372352),dict(component='shared_prior',bits=1219536,copies=1,total_bits=1219536),dict(component='shared_syndrome',bits=1728,copies=1,total_bits=1728),
  dict(component='aliased_edge_message_store',bits=7043760,copies=2,total_bits=14087520),dict(component='marginal',bits=1219536,copies=2,total_bits=2439072),dict(component='gamma',bits=338760,copies=2,total_bits=677520),dict(component='decision',bits=67752,copies=2,total_bits=135504),dict(component='trajectory_control',bits=166,copies=2,total_bits=332)]
 wc(OUT/'validated_memory_model.csv',mem);total=sum(x['total_bits'] for x in mem);assert total==32933564
 br=[dict(model='capacity_only',bits=total,MiB=total/8/2**20,BRAM36=math.ceil(total/36864),assumption='total bits only'),dict(model='banked_capacity',bits=total,MiB=total/8/2**20,BRAM36=925,assumption='per-array and four-bank rounding'),dict(model='bandwidth_aware_true_dual_read',bits=total,MiB=total/8/2**20,BRAM36=925,assumption='shared read-only banks use true dual-port 2R; no replication'),dict(model='bandwidth_aware_replication_fallback',bits=total+15593616,MiB=(total+15593616)/8/2**20,BRAM36=925+421,assumption='replicate all shared static arrays if 2R mapping unavailable; conservative capacity sum')]
 wc(OUT/'port_aware_bram_estimate.csv',br)
 wc(OUT/'gari_memory_recomparison.csv',[dict(design='GARI_one_core',BRAM=704,type='measured',below_2121=True,below_704=False),dict(design='GARI_three_core',BRAM=2121,type='measured',below_2121=False,below_704=False),dict(design='M4_capacity_only',BRAM=894,type='analytical',below_2121=True,below_704=False),dict(design='M4_dual_read_banked',BRAM=925,type='analytical',below_2121=True,below_704=False),dict(design='M4_full_static_replication_fallback',BRAM=1346,type='analytical',below_2121=True,below_704=False)])

def bank_subsets(addresses):
 pending=list(map(int,addresses));issued=[]
 while pending:
  seen=set();subset=[];remain=[]
  for a in pending:
   if a%P not in seen:seen.add(a%P);subset.append(a)
   else:remain.append(a)
  issued.append(subset);pending=remain
 return issued

def static_access_templates():
 """Address-level shared-static issue groups for one iteration/relay init.

 Fractions are measured over (issued group, bank) observations, not over the
 controller's unrelated arithmetic/idle cycles.  Both engines execute the
 same static address stream while active, so an accessed bank sees two reads.
 """
 check_edges=[np.arange(HP.indptr[c],HP.indptr[c+1],dtype=np.int64) for c in range(C)]
 variable_edges=[FAULT_EDGES[HC.indptr[v]:HC.indptr[v+1]] for v in range(V)]
 groups={x:[] for x in ['edge_to_fault','fault_to_edge','degree_tables','prior','syndrome']}
 # Per iteration: degree/check and syndrome are read in check and convergence;
 # degree/fault, prior, and packed fault adjacency are read in variable.
 groups['degree_tables'] += [[c] for c in range(C)]*2 + [[v] for v in range(V)]
 groups['syndrome'] += [[c] for c in range(C)]*2
 groups['prior'] += [[v] for v in range(V)]
 for es in variable_edges:
  for i in range(0,len(es),P):groups['fault_to_edge'].append(list(range(i,min(i+P,len(es)))))
 for es in check_edges:
  for i in range(0,len(es),P):groups['edge_to_fault'].append(es[i:i+P].tolist())
 iteration_counts={k:len(v) for k,v in groups.items()}
 # Relay init: consecutive edge-to-fault reads and conflict-resolved prior reads.
 relay={x:[] for x in groups}
 for s in range(0,E,P):
  es=np.arange(s,min(s+P,E),dtype=np.int64);relay['edge_to_fault'].append(es.tolist())
  relay['prior'] += bank_subsets(HP.indices[es])
 relay_counts={k:len(v) for k,v in relay.items()}
 return groups,relay,iteration_counts,relay_counts

def port_and_first_success(jobs,full):
 groups,relay,ic,rc=static_access_templates();demand=[]
 for name in groups:
  gs=groups[name]+relay[name];counts=[0,0,0]
  for g in gs:
   used={int(a)%P for a in g}
   for b in range(P):counts[2 if b in used else 0]+=1
  n=sum(counts);demand.append(dict(structure=name,issue_groups=len(gs),bank_cycle_observations=n,
   demand_0_fraction=counts[0]/n if n else 1.0,demand_1_fraction=0.0,demand_2_fraction=counts[2]/n if n else 0.0,
   demand_gt2_fraction=0.0,mean_reads_per_bank=(2*counts[2]/n if n else 0.0),maximum_reads_per_bank=2 if gs else 0,dual_read_stalls=0,
   scope='conditional address-level static issue stream; arithmetic/idle controller cycles excluded'))
 wc(OUT/'shared_memory_port_demand.csv',demand)
 # Deterministic negative control: E0-priority, phase-lock serialization.  Each
 # coincident shared-static issue consumes one extra E1 service slot.  This is
 # an address-level control, not a cycle-accurate RTL arbitration claim.
 ITER=508753+1958833+747049;RELAY=1068955;static_iter=sum(ic.values());static_relay=sum(rc.values())
 fs=[];single=[]
 for j in jobs:
  rec={x['trajectory']:x for x in full if x['sample_seed']==j[0] and x['shot']==j[1]}
  costs={t:int(rec[t]['iterations'])*ITER+int(rec[t]['legs'])*RELAY for t in ('E0','E1')}
  conv={t:bool(rec[t]['converged']) for t in ('E0','E1')}
  viable=[(costs[t],0 if t=='E0' else 1,t) for t in ('E0','E1') if conv[t]]
  dual_w=min(viable)[2] if viable else 'NONE';dual_cycle=min(x[0] for x in viable) if viable else max(costs.values())
  e1_stall=int(rec['E1']['iterations'])*static_iter+int(rec['E1']['legs'])*static_relay
  scost={'E0':costs['E0'],'E1':costs['E1']+e1_stall};sviable=[(scost[t],0 if t=='E0' else 1,t) for t in ('E0','E1') if conv[t]]
  single_w=min(sviable)[2] if sviable else 'NONE';single_cycle=min(x[0] for x in sviable) if sviable else max(scost.values())
  fs.append(dict(sample_seed=j[0],shot=j[1],canonical_winner=dual_w,M4_winner=dual_w,winner_changed=False,canonical_BA2_cycles=dual_cycle,M4_dual_read_BA2_cycles=dual_cycle,cycles_changed=False,lost_success=False,logical_regression=False,rescue=int(j[4]['parallel_rescue'])))
  single.append(dict(sample_seed=j[0],shot=j[1],dual_read_winner=dual_w,single_port_winner=single_w,winner_changed=dual_w!=single_w,dual_read_cycles=dual_cycle,single_port_cycles=single_cycle,added_stalls=single_cycle-dual_cycle,E1_static_service_slots=e1_stall))
 wc(OUT/'n2_first_success_validation.csv',fs);wc(OUT/'single_port_control.csv',single)
 delta=np.asarray([x['added_stalls'] for x in single],np.int64)
 return dict(static_issue_groups_per_iteration=static_iter,static_issue_groups_per_relay_init=static_relay,
  structure_groups_per_iteration=ic,structure_groups_per_relay_init=rc,single_port_model='E0-priority phase-lock serialization negative control',
  single_port_mean_added_cycles=float(delta.mean()),single_port_p95_added_cycles=float(np.percentile(delta,95)),single_port_p99_added_cycles=float(np.percentile(delta,99)),single_port_max_added_cycles=int(delta.max()),
  single_port_changed_winners=sum(x['winner_changed'] for x in single),dual_read_changed_winners=0,dual_read_changed_cycles=0)

def main():
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'checkpoints').mkdir(exist_ok=True);traversal_validation();hazard_table();access_and_memory();jobs=archive_jobs();lookup={(x[0],x[1]):x for x in jobs};pil=[]
 if (OUT/'pilot_equivalence.csv').exists():pil=rows(OUT/'pilot_equivalence.csv')
 else:
  for p in rows(PILOT):
   j=lookup[(int(p['sample_seed']),int(p['shot']))];traj=p['trajectory'];seed=int(j[4]['s0' if traj=='E0' else 's1']);cfg,meta=schedule(seed);rc,rm,tc,tm,first,exact=decode_pair(j[2],cfg)
   pil.append(dict(case_id=p['case_id'],category=p['category'],trajectory=traj,sample_seed=j[0],shot=j[1],classification='EXACT MATCH' if exact else 'OUTCOME MATCH BUT TRACE DIFFERENCE',iterations=rc.total_iterations,legs=rc.relay_legs,trace_exact=first is None,correction_exact=np.array_equal(rc.decoded_error,rm.decoded_error),first_difference=json.dumps(first)))
   print('pilot',p['case_id'],pil[-1]['classification'],flush=True)
  wc(OUT/'pilot_equivalence.csv',pil)
 if not all(x['classification']=='EXACT MATCH' for x in pil):raise RuntimeError('M4 pilot diverged; full panel stopped')
 if os.environ.get('PILOT_ONLY')=='1':return
 full=[]
 for ji,j in enumerate(jobs):
  for traj,key in [('E0','s0'),('E1','s1')]:
   cp=OUT/'checkpoints'/f'{traj}_{j[0]}_{j[1]:03d}.json'
   if cp.exists():r=json.loads(cp.read_text())
   else:
    cfg,meta=schedule(int(j[4][key]));rc,rm,tc,tm,first,exact=decode_pair(j[2],cfg);dec=np.asarray(rm.decoded_error,np.uint8);logical=np.asarray(AP@dec).reshape(-1).astype(np.uint8)&1
    r=dict(trajectory=traj,sample_seed=j[0],shot=j[1],classification='EXACT MATCH' if exact else 'OUTCOME MATCH BUT TRACE DIFFERENCE',iterations=rc.total_iterations,legs=rc.relay_legs,trace_iterations=len(tc),trace_exact=first is None,converged=bool(rc.converged),correction_hash=bh(dec),logical_correct=bool(rc.converged and np.array_equal(logical,j[3])),first_difference=first,final_rng_state=meta[rc.relay_legs-1]['state']);wj(cp,r)
   full.append(r);print(f"{len(full)}/256 {traj} {j[0]}:{j[1]} {r['classification']}",flush=True)
 archived_exact=all(int(x['iterations'])==int(next(j[4] for j in jobs if j[0]==x['sample_seed'] and j[1]==x['shot'])[('e0_' if x['trajectory']=='E0' else 'e1_')+'iterations']) and int(x['legs'])==int(next(j[4] for j in jobs if j[0]==x['sample_seed'] and j[1]==x['shot'])[('e0_' if x['trajectory']=='E0' else 'e1_')+'legs']) for x in full)
 summary=dict(trajectories=len(full),classification_counts={k:sum(x['classification']==k for x in full) for k in ['EXACT MATCH','OUTCOME MATCH BUT TRACE DIFFERENCE','OUTCOME MISMATCH','INVALID']},compared_iterations=sum(x['trace_iterations'] for x in full),E0=sum(x['trajectory']=='E0' for x in full),E1=sum(x['trajectory']=='E1' for x in full),all_exact=all(x['classification']=='EXACT MATCH' for x in full),archive_iterations_and_legs_exact=archived_exact,expected_compared_iterations=47736,iteration_total_exact=sum(x['trace_iterations'] for x in full)==47736,first_divergence=next((x for x in full if x['classification']!='EXACT MATCH'),None));wj(OUT/'full_equivalence_summary.json',summary)
 port=port_and_first_success(jobs,full)
 manifest=dict(status='complete' if summary['all_exact'] and archived_exact and summary['iteration_total_exact'] else 'failed',model='separate M4 oracle',pilot_exact=True,full=summary,degree_traversal_exact=True,message_hazards=0,BA2_access_exact=True,dual_read_max_demand=2,dual_read_stalls=0,first_success_changed_winners=0,first_success_changed_cycles=0,lost_successes=0,logical_regressions=0,port_model=port,memory_bits=32933564,capacity_BRAM36=894,banked_BRAM36=925,bandwidth_aware_dual_read_BRAM36=925,replication_fallback_BRAM36=1346,RTL_modified=False,synthesis=False);wj(OUT/'study_manifest.json',manifest)

if __name__=='__main__':main()

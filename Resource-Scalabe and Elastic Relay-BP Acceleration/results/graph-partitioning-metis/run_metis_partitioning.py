#!/usr/bin/env python3
"""Run the first reversible, software-only METIS graph-layout experiment."""
from __future__ import annotations
import csv, hashlib, importlib.metadata, json, platform, time
from pathlib import Path
import numpy as np
import pymetis
from scipy import sparse

OUT=Path(__file__).resolve().parent; ROOT=OUT.parents[1]
GRAPH=ROOT/"graphs/generated/gross_circuit_level/memory_Z_r12_p0p003"
K=4; SEEDS=(1,2,3,4,5); RANDOM_SEED=20260830; UFACTOR=30; WORK_TOL=0.05

def jsonable(x):
    if isinstance(x,np.generic): return x.item()
    if isinstance(x,np.ndarray): return x.tolist()
    raise TypeError(type(x).__name__)
def write_json(path,x): path.write_text(json.dumps(x,indent=2,default=jsonable)+"\n")
def ahash(a):
    a=np.ascontiguousarray(a); h=hashlib.sha256(); h.update(str(a.dtype).encode());h.update(str(a.shape).encode());h.update(a.tobytes());return h.hexdigest()
def matrix(edges,r,c):
    m=sparse.csr_matrix((np.ones(len(edges),np.uint8),(edges[:,1],edges[:,0])),shape=(r,c),dtype=np.uint8)
    m.data&=1;m.eliminate_zeros();m.sort_indices();return m
def load_graph():
    pkg=json.loads((GRAPH/'package.json').read_text());c,v,o=pkg['detector_count'],pkg['fault_count'],pkg['observable_count']
    with np.load(GRAPH/'edge_lists.npz') as z: de=np.asarray(z['detector_edges'],np.int32);oe=np.asarray(z['observable_edges'],np.int32)
    with np.load(GRAPH/'faults.npz') as z: prob=np.asarray(z['probabilities'],np.float64)
    if(c,v,len(de),o)!=(1728,67752,391320,12):raise RuntimeError('Unexpected canonical dimensions')
    h=matrix(de,c,v);a=matrix(oe,o,v)
    if h.nnz!=len(de) or a.nnz!=len(oe):raise RuntimeError('Duplicate incidence')
    src=np.r_[de[:,1],c+de[:,0]].astype(np.int64);dst=np.r_[c+de[:,0],de[:,1]].astype(np.int64)
    order=np.argsort(src,kind='stable');src=src[order];adjncy=dst[order]
    xadj=np.r_[0,np.cumsum(np.bincount(src,minlength=c+v))].astype(np.int64)
    if len(adjncy)!=2*len(de) or xadj[-1]!=len(adjncy):raise RuntimeError('CSR failure')
    return dict(C=c,V=v,O=o,de=de,oe=oe,p=prob,H=h,A=a,xadj=xadj,adjncy=adjncy,degrees=np.diff(xadj).astype(np.int64))
def targets(n):return np.array([n//K+(p<n%K) for p in range(K)],np.int64)

def typed_rebalance(parts,xadj,adjncy,start,count):
    """Exact typed counts via lowest local cut-delta moves; opposite type stays fixed."""
    out=parts.copy();nodes=np.arange(start,start+count);goal=targets(count);before=np.bincount(out[nodes],minlength=K);surplus=before-goal
    candidates=[]
    for node in nodes:
        source=int(out[node])
        if surplus[source]<=0:continue
        nc=np.bincount(out[adjncy[xadj[node]:xadj[node+1]]],minlength=K)
        for target in range(K):
            if surplus[target]<0:candidates.append((int(nc[source]-nc[target]),int(node),source,target))
    candidates.sort();used=set();moves=[]
    for delta,node,source,target in candidates:
        if node in used or surplus[source]<=0 or surplus[target]>=0:continue
        out[node]=target;surplus[source]-=1;surplus[target]+=1;used.add(node);moves.append((node,source,target,delta))
        if np.all(surplus==0):break
    if np.any(surplus):raise RuntimeError(f'Rebalance residual {surplus}')
    return out,dict(counts_before=before,target_counts=goal,counts_after=np.bincount(out[nodes],minlength=K),move_count=len(moves),sum_local_cut_delta=int(sum(x[3] for x in moves)))
def rebalance(raw,g):
    p,cinfo=typed_rebalance(raw,g['xadj'],g['adjncy'],0,g['C']);p,finfo=typed_rebalance(p,g['xadj'],g['adjncy'],g['C'],g['V'])
    return p,dict(check_stage=cinfo,fault_stage=finfo)

def metrics(name,parts,g,runtime,seed=None):
    c,v,de=g['C'],g['V'],g['de'];cp,fp=parts[:c],parts[c:];cd,fd=g['degrees'][:c],g['degrees'][c:]
    cross=cp[de[:,1]]!=fp[de[:,0]];cut=int(cross.sum())
    cm=np.zeros(c,np.uint8);fm=np.zeros(v,np.uint8)
    np.bitwise_or.at(cm,de[:,1],(1<<fp[de[:,0]]).astype(np.uint8));np.bitwise_or.at(fm,de[:,0],(1<<cp[de[:,1]]).astype(np.uint8))
    ct=np.fromiter((int(x).bit_count() for x in cm),np.int8,count=c);ft=np.fromiter((int(x).bit_count() for x in fm),np.int8,count=v)
    cb=np.zeros(c,bool);fb=np.zeros(v,bool);np.logical_or.at(cb,de[:,1],cross);np.logical_or.at(fb,de[:,0],cross)
    cc=np.bincount(cp,minlength=K);fc=np.bincount(fp,minlength=K);cw=np.bincount(cp,weights=cd,minlength=K).astype(np.int64);fw=np.bincount(fp,weights=fd,minlength=K).astype(np.int64)
    imb=dict(check_count=float(np.max(np.abs(cc/(c/K)-1))),fault_count=float(np.max(np.abs(fc/(v/K)-1))),check_work=float(np.max(np.abs(cw/(len(de)/K)-1))),fault_work=float(np.max(np.abs(fw/(len(de)/K)-1))))
    return dict(name=name,seed=seed,runtime_seconds=runtime,check_counts=cc,fault_counts=fc,check_degree_workloads=cw,fault_degree_workloads=fw,imbalance_fraction=imb,maximum_conceptual_imbalance=max(imb.values()),edge_cut_count=cut,edge_cut_ratio=cut/len(de),boundary_check_count=int(cb.sum()),boundary_check_fraction=float(cb.mean()),boundary_fault_count=int(fb.sum()),boundary_fault_fraction=float(fb.mean()),mean_partitions_touched_per_check=float(ct.mean()),max_partitions_touched_per_check=int(ct.max()),mean_partitions_touched_per_fault=float(ft.mean()),max_partitions_touched_per_fault=int(ft.max()))

def random_balanced(g):
    t=time.perf_counter();rng=np.random.default_rng(RANDOM_SEED);c,v=g['C'],g['V'];p=np.empty(c+v,np.int8)
    for off,n in ((0,c),(c,v)):
        labels=np.repeat(np.arange(K,dtype=np.int8),targets(n));p[off:off+n]=labels[rng.permutation(n)]
    return p,time.perf_counter()-t
def greedy_balanced(g):
    """Balance check work, then place faults with maximum assigned-check affinity."""
    t=time.perf_counter();c,v=g['C'],g['V'];cd,fd=g['degrees'][:c],g['degrees'][c:];p=np.full(c+v,-1,np.int8)
    cap=targets(c);count=np.zeros(K,int);work=np.zeros(K,int)
    for node in np.lexsort((np.arange(c),-cd)):
        eligible=np.flatnonzero(count<cap);part=min(eligible,key=lambda q:(work[q],count[q],q));p[node]=part;count[part]+=1;work[part]+=cd[node]
    hc=g['H'].tocsc();cap=targets(v);count[:]=0;work[:]=0
    for fault in np.lexsort((np.arange(v),-fd)):
        nb=hc.indices[hc.indptr[fault]:hc.indptr[fault+1]];aff=np.bincount(p[nb],minlength=K);eligible=np.flatnonzero(count<cap)
        part=min(eligible,key=lambda q:(-aff[q],work[q],count[q],q));p[c+fault]=part;count[part]+=1;work[part]+=fd[fault]
    return p,time.perf_counter()-t

def run_metis(g):
    runs=[];assign={};adj=pymetis.CSRAdjacency(g['xadj'],g['adjncy'])
    for seed in SEEDS:
        opts=pymetis.Options(seed=seed,ufactor=UFACTOR,objtype=0,ncuts=1,niter=10);t=time.perf_counter()
        result=pymetis.part_graph(K,adjacency=adj,vweights=g['degrees'],recursive=False,options=opts);rawtime=time.perf_counter()-t;raw=np.asarray(result.vertex_part,np.int8)
        final,rinfo=rebalance(raw,g);run=metrics('metis_limited',final,g,time.perf_counter()-t,seed);run['raw_metis_edge_cut_reported']=int(result.edge_cuts);run['raw_metis_metrics']=metrics('raw_metis',raw,g,rawtime,seed);run['typed_rebalance']=rinfo;run['acceptable']=run['maximum_conceptual_imbalance']<=WORK_TOL
        runs.append(run);assign[seed]=final
    return runs,assign

def write_csv(path,records,fields):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in records:w.writerow({k:json.dumps(r[k],default=jsonable) if isinstance(r[k],(dict,list,np.ndarray)) else r[k] for k in fields})
def permutations(parts,n,off):
    old=np.arange(n);n2o=np.lexsort((old,parts[off:off+n])).astype(np.int64);o2n=np.empty(n,np.int64);o2n[n2o]=np.arange(n);return o2n,n2o
def canon(e):return e[np.lexsort((e[:,1],e[:,0]))]
def reorder(selected,g):
    c,v=g['C'],g['V'];co,cn=permutations(selected,c,0);fo,fn=permutations(selected,v,c)
    hp=g['H'][cn,:][:,fn].tocsr();ap=g['A'][:,fn].tocsr();pp=g['p'][fn];hb=hp[co,:][:,fo];ab=ap[:,fo];pb=pp[fo]
    dep=np.c_[fo[g['de'][:,0]],co[g['de'][:,1]]].astype(np.int32);deb=np.c_[fn[dep[:,0]],cn[dep[:,1]]].astype(np.int32)
    oep=np.c_[fo[g['oe'][:,0]],g['oe'][:,1]].astype(np.int32);oeb=np.c_[fn[oep[:,0]],oep[:,1]].astype(np.int32)
    report=dict(all_checks_present_once=bool(np.array_equal(np.sort(cn),np.arange(c))),all_faults_present_once=bool(np.array_equal(np.sort(fn),np.arange(v))),H_inverse_exact=bool((hb!=g['H']).nnz==0),A_inverse_exact=bool((ab!=g['A']).nnz==0),probabilities_inverse_exact=bool(np.array_equal(pb,g['p'])),detector_fault_incidence_set_exact=bool(np.array_equal(canon(deb),canon(g['de']))),observable_fault_incidence_set_exact=bool(np.array_equal(canon(oeb),canon(g['oe']))),detector_fault_edge_count_original=len(g['de']),detector_fault_edge_count_partitioned=hp.nnz,observable_fault_edge_count_original=len(g['oe']),observable_fault_edge_count_partitioned=ap.nnz,no_missing_or_duplicate_detector_fault_edges=bool(hp.nnz==len(g['de'])),no_missing_or_duplicate_observable_fault_edges=bool(ap.nnz==len(g['oe'])),no_fault_split=True,hashes=dict(H_original_indptr=ahash(g['H'].indptr),H_roundtrip_indptr=ahash(hb.indptr),H_original_indices=ahash(g['H'].indices),H_roundtrip_indices=ahash(hb.indices),A_original_indices=ahash(g['A'].indices),A_roundtrip_indices=ahash(ab.indices),probabilities_original=ahash(g['p']),probabilities_roundtrip=ahash(pb)))
    if not all(x for x in report.values() if isinstance(x,bool)):raise RuntimeError(f'Invariance failure {report}')
    np.savez_compressed(OUT/'permutations.npz',check_old_to_new=co,check_new_to_old=cn,fault_old_to_new=fo,fault_new_to_old=fn);sparse.save_npz(OUT/'H_partitioned.npz',hp);sparse.save_npz(OUT/'A_partitioned.npz',ap);np.savez_compressed(OUT/'probabilities_partitioned.npz',probabilities=pp);write_json(OUT/'invariance_report.json',report)
    return dict(check_old_to_new=co,check_new_to_old=cn,fault_old_to_new=fo,fault_new_to_old=fn,report=report)
def memberships(parts,perm,g):
    for kind,n,off,mapping,name in [('check',g['C'],0,perm['check_old_to_new'],'partition_membership_checks.csv'),('fault',g['V'],g['C'],perm['fault_old_to_new'],'partition_membership_faults.csv')]:
        with (OUT/name).open('w',newline='') as f:
            w=csv.writer(f);w.writerow([f'original_{kind}_id','partition_id',f'new_{kind}_id'])
            for node in range(n):w.writerow([node,int(parts[off+node]),int(mapping[node])])

def small_demo():
    edges=[(0,0),(0,1),(0,2),(1,1),(1,2),(1,3),(2,0),(2,2),(2,3)];c,v=3,4;adj=[[] for _ in range(c+v)]
    for x,y in edges:adj[x].append(c+y);adj[c+y].append(x)
    r=pymetis.part_graph(2,adjacency=adj,recursive=False,options=pymetis.Options(seed=1,ufactor=100));p=np.asarray(r.vertex_part,np.int8);inside=[];cross=[]
    for x,y in edges:(inside if p[x]==p[c+y] else cross).append(f'C{x} -- V{y}')
    rec=dict(k=2,seed=1,assignment={**{f'C{i}':int(p[i]) for i in range(c)},**{f'V{i}':int(p[c+i]) for i in range(v)}},internal_edges=inside,cross_partition_edges=cross,cut_count=len(cross),balance=dict(total_nodes=np.bincount(p,minlength=2),checks=np.bincount(p[:c],minlength=2),faults=np.bincount(p[c:],minlength=2)))
    lines=['Small graph PyMetis k=2 demonstration','','Node assignments:',*[f'{n} -> P{q}' for n,q in rec['assignment'].items()],'','Internal edges:',*inside,'','Cross-partition edges:',*cross,'',f'Cut count: {len(cross)}',f"Balance: {json.dumps(rec['balance'],default=jsonable)}"];(OUT/'small_graph_partition.txt').write_text('\n'.join(lines)+'\n');return rec

def readme(selected,comp,small):
    rows='\n'.join(f"| {r['name']} | {r['edge_cut_ratio']:.6f} | {r['maximum_conceptual_imbalance']:.4%} | {r['boundary_check_fraction']:.4%} | {r['boundary_fault_fraction']:.4%} |" for r in comp)
    (OUT/'README.md').write_text(f"""# Limited METIS graph-partitioning baseline

Software-only structural experiment on the canonical Tier-2 gross `[[144,12,12]]` memory-Z detector/fault graph. Relay-BP was not run and RTL was not modified.

## Interface and limitation

- PyMetis {importlib.metadata.version('pymetis')}; direct k-way via `recursive=False`; fixed `Options.seed`; edge-cut objective; `Options.ufactor={UFACTOR}` (3%).
- The wrapper does **not reliably expose four simultaneous balance channels**. This is a **LIMITED METIS BASELINE**.
- METIS balances one scalar vertex weight equal to node degree (combined endpoint-incidence work).
- A deterministic post-stage reaches exact check and fault counts using lowest local cut-penalty moves.
- Separate check/fault workloads are measured and filtered at {WORK_TOL:.0%}, not claimed as independently METIS-enforced.

## Selection

Seed `{selected['seed']}` passed the 5% conceptual-work filter and was selected by minimum edge-cut ratio, then summed mean neighborhood dispersion, maximum imbalance, and seed.

| Assignment | Edge-cut ratio | Maximum imbalance | Boundary checks | Boundary faults |
|---|---:|---:|---:|---:|
{rows}

The unpartitioned graph is reported separately without a fake k=4 cut score. Structural locality is not evidence of decoding improvement.

Reproduce with `../.venv/bin/python results/graph-partitioning-metis/run_metis_partitioning.py`. The small k=2 example has cut {small['cut_count']}.
""")

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    write_json(OUT/'dependency_report.json',dict(
        python_executable=str(Path(__import__('sys').executable)),python_version=platform.python_version(),
        interface='pymetis',version=importlib.metadata.version('pymetis'),available=True,
        direct_kway=True,fixed_seed_control=True,imbalance_tolerance=True,
        multi_constraint_vertex_weights=False,
        limitation='PyMetis 2025.2.2 does not reliably expose the four simultaneous target-weight channels required here; toy flattened-weight probing produced invalid all-in-one assignments.',
        experiment_label='LIMITED METIS BASELINE'))
    g=load_graph();runs,assign=run_metis(g);acceptable=[r for r in runs if r['acceptable']]
    write_csv(OUT/'metis_runs.csv',runs,['seed','acceptable','runtime_seconds','edge_cut_count','edge_cut_ratio','check_counts','fault_counts','check_degree_workloads','fault_degree_workloads','maximum_conceptual_imbalance','boundary_check_count','boundary_check_fraction','boundary_fault_count','boundary_fault_fraction','mean_partitions_touched_per_check','max_partitions_touched_per_check','mean_partitions_touched_per_fault','max_partitions_touched_per_fault','raw_metis_edge_cut_reported'])
    if not acceptable:write_json(OUT/'partition_metrics.json',dict(status='failed_balance_filter',metis_runs=runs));raise RuntimeError('No run passed balance filter')
    selected=min(acceptable,key=lambda r:(r['edge_cut_ratio'],r['mean_partitions_touched_per_check']+r['mean_partitions_touched_per_fault'],r['maximum_conceptual_imbalance'],r['seed']));parts=assign[selected['seed']]
    rp,rt=random_balanced(g);gp,gt=greedy_balanced(g);rm=metrics('random_balanced',rp,g,rt,RANDOM_SEED);gm=metrics('greedy_balanced',gp,g,gt);sm=dict(selected);sm['name']='metis_limited_selected';comp=[rm,gm,sm]
    write_csv(OUT/'baseline_comparison.csv',comp,['name','seed','edge_cut_count','edge_cut_ratio','check_counts','fault_counts','check_degree_workloads','fault_degree_workloads','maximum_conceptual_imbalance','boundary_check_fraction','boundary_fault_fraction','mean_partitions_touched_per_check','mean_partitions_touched_per_fault','runtime_seconds'])
    perm=reorder(parts,g);memberships(parts,perm,g);write_json(OUT/'selected_partition.json',dict(selection_rule=['reject maximum conceptual imbalance > 5%','minimum edge-cut ratio','minimum summed mean neighborhood dispersion','minimum maximum imbalance','lowest seed'],selected_seed=selected['seed'],metrics=selected,check_partitions=parts[:g['C']],fault_partitions=parts[g['C']:]))
    small=small_demo();write_json(OUT/'partition_metrics.json',dict(status='complete',experiment_label='LIMITED METIS BASELINE',interface=dict(name='pymetis',version=importlib.metadata.version('pymetis'),python=platform.python_version(),direct_kway=True,fixed_seed=True,imbalance_tolerance=True,multi_constraint_vertex_weights=False),enforced_balance='single scalar degree weight plus deterministic exact typed-count rebalancing',conceptual_workload_tolerance=WORK_TOL,metis_options=dict(k=K,recursive=False,seeds=SEEDS,ufactor=UFACTOR,objtype=0,ncuts=1,niter=10),unpartitioned_reference=dict(vertices=g['C']+g['V'],edges=len(g['de']),k4_cut_metrics=None),metis_runs=runs,controls=[rm,gm],selected_seed=selected['seed'],small_graph=small));readme(selected,comp,small)
    print(json.dumps(dict(status='complete',selected_seed=selected['seed'],selected_edge_cut_ratio=selected['edge_cut_ratio'],invariance_passed=all(x for x in perm['report'].values() if isinstance(x,bool))),indent=2))
if __name__=='__main__':main()

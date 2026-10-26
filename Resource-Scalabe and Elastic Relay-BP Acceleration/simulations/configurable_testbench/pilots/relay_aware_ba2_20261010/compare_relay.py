"""Graph-specific BA2 comparison with explicit inverse-mapped decoder traces."""
from pathlib import Path
import argparse
import csv
from dataclasses import asdict
import hashlib
import json
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
BENCH=HERE.parents[1]
sys.path.insert(0,str(BENCH))
import testbench as tb
import numpy as np
from scipy import sparse

BASE=HERE.parent/"ba2_graph_specific_20261010"
PAIRED=HERE.parent/"paired_bb_4shot_20261010"


def dump(path,value):
    Path(path).write_text(json.dumps(value,indent=2,default=lambda x:x.tolist() if isinstance(x,np.ndarray) else x.item())+"\n")


def rows(path):
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))


def digest(array):
    a=np.ascontiguousarray(array)
    return hashlib.sha256(str(a.dtype).encode()+str(a.shape).encode()+a.tobytes()).hexdigest()


def schedule(seed,cfg,v,fn):
    original=[tb.FixedRelayLegConfig(cfg.first_limit,gamma=.125)]
    mapped=[tb.FixedRelayLegConfig(cfg.first_limit,gamma=.125)]
    state=seed
    words=[0]
    for _ in range(1,cfg.R):
        values,_,state,rejected=tb.vector(state,v)
        gamma=np.asarray(values,dtype=float)/16
        original.append(tb.FixedRelayLegConfig(cfg.later_limit,gamma=gamma))
        mapped.append(tb.FixedRelayLegConfig(cfg.later_limit,gamma=gamma[fn]))
        words.append(v+rejected)
    return original,mapped,words


def relay_cost(groups,residues):
    return sum(int(np.bincount(residues[group],minlength=4).max())-1 for group in groups)


def relay_assignment(ba,groups,original):
    """Optimize exact relay retry count, with bounded deterministic local search.

    Duplicate fault references remain duplicate accesses (no broadcast assumed).
    Swaps exchange bank residues of two distinct identities; capacities stay exact.
    """
    v=len(original)
    graph=ba.pair_matrix(v,groups).tocsr()
    seed,_=ba.greedy_residues(graph,np.ones(v),np.zeros(v,np.int8),0.,0.)
    initial=relay_cost(groups,original)
    assignment=(seed if relay_cost(groups,seed)<initial else original).copy()
    padded=np.full((len(groups),4),v,dtype=np.int64)
    memberships=[[] for _ in range(v)]
    for i,group in enumerate(groups):
        padded[i,:len(group)]=group
        for item in np.unique(group): memberships[item].append(i)
    order=np.lexsort((np.arange(v),-np.asarray(graph.sum(axis=1)).ravel()))
    accepted=0
    for sweep in range(2):
        for item in order:
            choices=[]
            for bank in range(4):
                if bank==assignment[item]: continue
                pool=np.flatnonzero(assignment==bank)
                if len(pool):
                    indices=(np.arange(8)*max(1,len(pool)//8)+int(item)+sweep*17)%len(pool)
                    choices.extend(pool[indices].tolist())
            best=None
            for other in sorted(set(choices)):
                affected=np.union1d(memberships[item],memberships[other]).astype(int)
                nodes=padded[affected]
                extended=np.append(assignment,-1)
                before=extended[nodes]
                after=before.copy()
                after[nodes==item]=assignment[other];after[nodes==other]=assignment[item]
                def cost(banks):
                    counts=np.stack([(banks==bank).sum(axis=1) for bank in range(4)],axis=1)
                    return int((counts.max(axis=1)-1).sum())
                delta=cost(after)-cost(before)
                if delta<0 and (best is None or (delta,other)<best): best=(delta,other)
            if best is not None:
                other=best[1];assignment[item],assignment[other]=assignment[other],assignment[item];accepted+=1
    final=relay_cost(groups,assignment)
    if not np.array_equal(np.bincount(assignment,minlength=4),ba.residue_capacities(v)):
        raise ValueError("Cannot construct capacity-preserving fault assignment")
    if final>initial: raise ValueError("Relay objective regressed")
    return assignment,dict(initial_retries=initial,greedy_retries=relay_cost(groups,seed),final_retries=final,
                           accepted_swaps=accepted,capacities=np.bincount(assignment,minlength=4),passes=2)


def compare_code(code):
    out=HERE/code
    out.mkdir(exist_ok=False)
    start=time.monotonic()
    cfg=tb.Config(**json.loads((PAIRED/"configs"/f"bb{code}_n2_p4.json").read_text()))
    if (cfg.P,cfg.shots,cfg.first_limit,cfg.later_limit,cfg.R,cfg.S)!=(4,4,2,2,2,1):
        raise ValueError("Paired pilot configuration changed")
    directory,pkg,manifest,circuit,h,action,priors=tb.load_problem(cfg)
    detectors,logicals=tb.samples(cfg,directory,pkg,circuit)
    ba=tb.module("ba2_comparison",tb.ROOT/"results/bank-aware-folding-layout/run_bank_aware_layout.py")
    ba.P=ba.fm.P=4
    fm=ba.fm
    ec,ev,ve=fm.original_edge_tables(h)
    with np.load(directory/"faults.npz") as data:
        probabilities=data["probabilities"].copy()
    g=dict(C=h.shape[0],V=h.shape[1],O=action.shape[0],E=h.nnz,H=h,A=action,p=probabilities,
           edge_check=ec,edge_fault=ev,variable_edges=ve)
    with np.load(BASE/code/"storage_maps.npz") as saved:
        fr=saved["fault_residues"].copy();er=saved["edge_residues"].copy()
        baseline=ba.bank_layout("BA2",g,fr,er)
        for key in ("fault_old_to_new","fault_new_to_old","edge_old_to_new","edge_new_to_old"):
            if not np.array_equal(baseline[key],saved[key]): raise ValueError("BA2 map reproduction failed")
    groups=[ev[baseline["edge_new_to_old"][chunk]] for chunk in fm.chunks(np.arange(g["E"]))]
    candidate,fs=relay_assignment(ba,groups,fr)
    fr=candidate;es={"frozen_existing_BA2_edge_map":True}
    layout=ba.bank_layout("BA2_relay",g,fr,er)
    assert np.array_equal(layout["edge_old_to_new"],baseline["edge_old_to_new"])
    inv,hp,ap,pp=ba.invariance(g,layout)
    # Decoder CSR order is separate from physical edge-storage IDs.
    hp.sort_indices();ap.sort_indices()
    fo,fn=layout["fault_old_to_new"],layout["fault_new_to_old"]
    eo,en=layout["edge_old_to_new"],layout["edge_new_to_old"]
    perm_keys=np.repeat(np.arange(g["C"],dtype=np.int64),np.diff(hp.indptr))*g["V"]+fn[hp.indices]
    old_keys=ec*g["V"]+ev
    decoder_new_to_old=np.searchsorted(old_keys,perm_keys)
    if not np.array_equal(old_keys[decoder_new_to_old],perm_keys):
        raise ValueError("Cannot restore decoder edge identities")
    decoder_old_to_new=np.empty(g["E"],np.int64)
    decoder_old_to_new[decoder_new_to_old]=np.arange(g["E"])
    if not np.array_equal(priors[fn][fo],priors) or not np.array_equal(pp[fo],probabilities):
        raise ValueError("Prior correspondence failure")
    inv.update(priors_inverse_exact=True,checks_and_syndrome_order_unchanged=True,
               decoder_edge_identity_inverse_exact=bool(np.array_equal(np.sort(decoder_new_to_old),np.arange(g["E"]))),
               physical_edge_maps_separate_from_decoder_CSR=True)
    np.savez_compressed(out/"storage_maps.npz",fault_old_to_new=fo,fault_new_to_old=fn,
                        edge_old_to_new=eo,edge_new_to_old=en,decoder_edge_old_to_new=decoder_old_to_new,
                        fault_residues=fr,edge_residues=er)
    dump(out/"bank_assignment_statistics.json",dict(fault=fs,edge=es))
    print(code,"validating inverse-mapped decoder trajectories",flush=True)
    pilot=rows(PAIRED/"runs"/f"bb{code}_n2_p4"/"per_engine.csv")
    pilot_index={(int(e["shot"]),int(e["engine"])):e for e in pilot}
    original_engines={};paired=[]
    edge_fields=("check_to_var","var_to_check")
    node_fields=("gamma_float","gamma_int","lambda_bias","beliefs","decoded_error")
    for shot,(syndrome,logical) in enumerate(zip(detectors,logicals)):
        for engine,seed in enumerate(tb.trajectory_seeds(cfg,shot)):
            legs,plegs,words=schedule(seed,cfg,g["V"],fn)
            for leg,pleg in zip(legs,plegs):
                if not np.isscalar(leg.gamma) and not np.array_equal(np.asarray(pleg.gamma)[fo],np.asarray(leg.gamma)):
                    raise ValueError("Gamma inverse mapping failure")
            traces=[];ptraces=[]
            def callback(target,mapped):
                def observe(event):
                    hashes={}
                    for field in node_fields:
                        hashes[field]=digest(event[field][fo] if mapped else event[field])
                    for field in edge_fields:
                        hashes[field]=digest(event[field][decoder_old_to_new] if mapped else event[field])
                    hashes["residual"]=digest(event["residual"])
                    target.append(dict(leg=int(event["leg_index"]),iteration=int(event["iteration"]),
                                       global_iteration=int(event["global_iteration"]),converged=bool(event["converged"]),
                                       saturations=dict(event["saturation_counts"]),hashes=hashes))
                return observe
            def decoder(matrix,configs,hook):
                return tb.FixedRelayBPDecoder(matrix,tb.FixedRelayConfig(
                    fixed=tb.FixedConfig(b=18,g=4,M=16,clip=None,separate_scale=True),
                    leg_configs=tuple(configs),R=cfg.R,S=cfg.S,seed=0),iteration_callback=hook)
            # Neither decoder gets A, observed logicals or sampled fault labels.
            original=decoder(h,legs,callback(traces,False)).decode(priors,syndrome)
            mapped=decoder(hp,plegs,callback(ptraces,True)).decode(priors[fn],syndrome)
            decision=original.decoded_error.astype(np.uint8)
            restored=mapped.decoded_error[fo].astype(np.uint8)
            exact=(traces==ptraces and original.total_iterations==mapped.total_iterations
                   and original.relay_legs==mapped.relay_legs and original.converged==mapped.converged
                   and np.array_equal(decision,restored) and np.array_equal(original.beliefs,mapped.beliefs[fo]))
            scored=tb.score(h,action,decision,syndrome,logical)
            pscore=tb.score(hp,ap,mapped.decoded_error,syndrome,logical)
            ref=pilot_index[(shot,engine)]
            reproduction=(int(ref["iterations"])==original.total_iterations and int(ref["legs"])==original.relay_legs
                          and int(ref["seed"])==seed and hashlib.sha256(decision.tobytes()).hexdigest()==ref["decision_hash"]
                          and all(int(ref[k])==scored[k] for k in scored))
            trace_record=dict(shot=shot,engine=engine,seed=seed,exact_trace=exact,paired_pilot_reproduction=reproduction,
                              trace_iterations=len(traces),scoring_inverse_exact=scored==pscore,
                              original_trace=traces,inverse_mapped_trace=ptraces,
                              candidate_weight_delta=None if not original.converged else
                                  float(mapped.metadata["best_weight"]-original.metadata["best_weight"]))
            paired.append(trace_record)
            if not exact or not reproduction or scored!=pscore:
                dump(out/"FAILED_equivalence.json",trace_record)
                raise ValueError("Decoder equivalence or paired-pilot reproduction failure")
            original_engines[(shot,engine)]=dict(iterations=original.total_iterations,legs=original.relay_legs,
                                                syndrome_converged=bool(not scored["nonconvergence"]),**scored)
    dump(out/"decoder_equivalence.json",paired)
    inv["gamma_inverse_mapping_exact"]=True
    inv["all_8_decoder_trajectories_exact"]=True
    inv["all_pilot_engine_decisions_and_scoring_exact"]=True
    dump(out/"invariants.json",inv)
    # Interpret structural costs only after exact graph/decoder checks have passed.
    original_layout=dict(check_order=np.arange(g["C"]),fault_order=np.arange(g["V"]),
                         check_edges=[np.arange(h.indptr[c],h.indptr[c+1]) for c in range(g["C"])],
                         variable_edges=ve,edge_fault=ev,edge_check=ec)
    profiles={}
    for name,lay in (("original",original_layout),("BA2",baseline),("BA2_relay",layout)):
        phases,total=fm.profile(lay,np.zeros(g["C"],int),np.zeros(g["V"],int))
        profiles[name]=dict(phases=phases,total=total)
    archived=json.loads((PAIRED/"runs"/f"bb{code}_n2_p4"/"summary.json").read_text())["folding_metrics"]
    for phase,cost in profiles["original"]["phases"].items():
        for field in ("logical_accesses","issued_groups","retry_subsets","estimated_cycles"):
            if cost[field]!=archived["phases"][phase][field]:
                raise ValueError("Original folding pilot reproduction failure")
    archived_profiles=json.loads((BASE/code/"phase_profiles.json").read_text())
    for name in ("original","BA2"):
        if profiles[name]!=archived_profiles[name]: raise ValueError("Archived phase reproduction failed")
    dump(out/"phase_profiles.json",profiles)
    comparisons=[];selection=[]
    for n in (1,2):
        for name,profile in profiles.items():
            records=[]
            for shot in range(cfg.shots):
                engines=[]
                for i in range(n):
                    e=original_engines[(shot,i)].copy()
                    phases=profile["phases"]
                    e["result_cycles"]=sum(phases[k]["estimated_cycles"]*(e["legs"] if k=="relay_init" else e["iterations"]) for k in phases)
                    engines.append(e)
                cycles,winner=tb.select(engines)
                critical=engines[winner] if winner>=0 else max(engines,key=lambda e:e["result_cycles"])
                status=dict(nonconvergence=1,syndrome_valid_logical_error=0,total_failure=1) if winner<0 else {k:engines[winner][k] for k in ("nonconvergence","syndrome_valid_logical_error","total_failure")}
                repetitions={k:critical["legs"] if k=="relay_init" else critical["iterations"] for k in profile["phases"]}
                def weighted(field):
                    return sum(repetitions[k]*profile["phases"][k][field] for k in repetitions)
                records.append(dict(shot=shot,winner=winner,modeled_cycles=cycles,**status,
                                    critical_retry_subsets=weighted("retry_subsets"),critical_conflict_events=weighted("conflict_events"),
                                    critical_issue_group_occupancy=weighted("logical_accesses")/(4*weighted("issued_groups"))))
            total=profile["total"]
            avg=lambda field:sum(r[field] for r in records)/len(records)
            comparisons.append(dict(code=code,N=n,layout=name,shots=cfg.shots,
                                    variable_retries=profile["phases"]["variable"]["retry_subsets"],
                                    relay_init_retries=profile["phases"]["relay_init"]["retry_subsets"],
                                    convergence_retries=profile["phases"]["convergence"]["retry_subsets"],
                                    mean_engine_iterations=sum(e["iterations"] for (shot,i),e in original_engines.items() if i<n)/(cfg.shots*n),
                                    structural_cycles=total["estimated_cycles"],structural_retry_subsets=total["retry_subsets"],
                                    structural_conflict_events=total["conflict_events"],structural_issue_group_occupancy=total["mean_lane_utilization"],
                                    mean_completion_cycles=avg("modeled_cycles"),mean_critical_retry_subsets=avg("critical_retry_subsets"),
                                    mean_critical_issue_group_occupancy=avg("critical_issue_group_occupancy"),
                                    total_failure=sum(r["total_failure"] for r in records),nonconvergence=sum(r["nonconvergence"] for r in records),
                                    logical_errors=sum(r["syndrome_valid_logical_error"] for r in records),
                                    failure_statistics=tb.rate(sum(r["total_failure"] for r in records),cfg.shots),
                                    timing_label="structural_extrapolation_not_RTL_calibrated"))
            selection.append(dict(N=n,layout=name,records=records))
    dump(out/"comparison.json",comparisons)
    dump(out/"per_shot_selection.json",selection)
    dump(out/"provenance.json",dict(configuration=asdict(cfg),input_package=str(directory),
                                   input_manifest_sha256=tb.sha(directory/"manifest.json"),
                                   paired_config_sha256=tb.sha(PAIRED/"configs"/f"bb{code}_n2_p4.json"),
                                   paired_engine_csv_sha256=tb.sha(PAIRED/"runs"/f"bb{code}_n2_p4"/"per_engine.csv"),
                                   objective=dict(method="relay-only greedy seed plus exact retry-reducing capacity-preserving swaps",candidate_limit_per_bank=8,passes=2,statistics=fs,P=4),
                                   mapping_semantics="Explicit mathematical ID <-> physical address maps; gamma/priors generated in original order then indexed by fault_new_to_old; decisions/trace mapped back before comparison",
                                   timing_semantics="Archived phase service formulas only; no top-level/RNG/cancellation overhead; no integrated hardware latency measurement",
                                   wall_seconds=time.monotonic()-start,trace_iterations=sum(r["trace_iterations"] for r in paired),
                                   output_hashes={p.name:tb.sha(p) for p in out.iterdir() if p.is_file()}))
    print(code,"PASS: 8 exact trajectories;",time.monotonic()-start,"seconds",flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--code",choices=list(tb.CODE_NAMES))
    args=parser.parse_args()
    if args.code:
        compare_code(args.code);return
    if (HERE/"protected_hashes.json").exists():
        raise FileExistsError("Use a fresh comparison directory")
    started=time.monotonic()
    # Include all historical data, packages, testbench baselines and paired pilot.
    protected=[tb.ROOT/"results",tb.ROOT/"reference",tb.ROOT/"graphs",BENCH/"testbench.py",
               BENCH/"test_testbench.py",BENCH/"README.md",BENCH/"smoke_config.json",
               BENCH/"runs",BENCH/"smoke_outputs",PAIRED,BASE]
    before={str(p):tb.sha(p) for root in protected for p in
            ([root] if root.is_file() else root.rglob("*")) if p.is_file()}
    dump(HERE/"protected_hashes.json",before)
    # Validate all packages before starting any expensive layout generation.
    for code in tb.CODE_NAMES:
        cfg=tb.Config(**json.loads((PAIRED/"configs"/f"bb{code}_n2_p4.json").read_text()))
        tb.load_problem(cfg)
    commands=[];durations=[]
    for code in ("288_12_18","18_4_3","72_12_6","144_12_12"):
        command=[sys.executable,"-B",str(Path(__file__).resolve()),"--code",code]
        commands.append(command);dump(HERE/"commands.json",commands)
        tick=time.monotonic()
        proc=subprocess.run(command,timeout=180)
        duration=time.monotonic()-tick;durations.append(duration)
        if proc.returncode:
            raise RuntimeError("Stopped on layout/equivalence failure: "+code)
        projection=time.monotonic()-started+max(durations)*(4-len(durations))
        print("Projected total seconds:",round(projection,1),flush=True)
        if projection>360:
            raise RuntimeError("Projected static-layout pilot exceeds six minutes; stopped")
    assert all(Path(p).is_file() and tb.sha(p)==h for p,h in before.items())
    table=[row for code in tb.CODE_NAMES for row in json.loads((HERE/code/"comparison.json").read_text())]
    dump(HERE/"comparison.json",table)
    with (HERE/"comparison.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    changed=[]
    for code in tb.CODE_NAMES:
        selection=json.loads((HERE/code/"per_shot_selection.json").read_text())
        for n in (1,2):
            a=next(x["records"] for x in selection if x["N"]==n and x["layout"]=="original")
            b=next(x["records"] for x in selection if x["N"]==n and x["layout"]=="BA2_relay")
            for x,y in zip(a,b):
                if x["winner"]!=y["winner"] or x["total_failure"]!=y["total_failure"]:
                    changed.append(dict(code=code,N=n,shot=x["shot"],original=x,BA2=y,reason="timing race only; engine trajectories already verified exact"))
    dump(HERE/"validation.json",dict(status="PASS",decoder_trajectories=32,
                                      exact_trace_iterations=sum(json.loads((HERE/c/"provenance.json").read_text())["trace_iterations"] for c in tb.CODE_NAMES),
                                      all_graph_and_prior_gamma_logical_invariants_exact=True,
                                      frozen_BA2_edge_maps_exact=True,paired_pilot_reproduction=True,
                                      selection_changes=changed,protected_files_unchanged=len(before),
                                      wall_seconds=time.monotonic()-started,
                                      limitations=["Bounded four-shot/R2/S1 validation, not universal equivalence or LER evidence",
                                                   "Physical storage maps are evaluated by a model; decoder uses its own mapped CSR",
                                                   "No exact cancellation, integrated RTL, contention or measured hardware timing",
                                                   "Relay-only objective may regress convergence retries; all regressions retained"] ))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    codes=list(tb.CODE_NAMES)
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout="constrained")
    for offset,name in enumerate(("original","BA2","BA2_relay")):
        selected=[next(r for r in table if r["code"]==c and r["N"]==1 and r["layout"]==name) for c in codes]
        x=[i+(offset-1)*.25 for i in range(len(codes))]
        axes[0].bar(x,[r["structural_cycles"]/1e6 for r in selected],width=.25,label=name)
        axes[1].bar(x,[r["structural_retry_subsets"]/1e3 for r in selected],width=.25,label=name)
    for ax in axes:
        ax.set_xticks(range(len(codes)),codes,rotation=20)
        ax.set_xlabel("BB code n_k_d")
    axes[0].set_ylabel("One iteration + relay init\n(structural million cycles)")
    axes[1].set_ylabel("Bank retry subsets\n(structural thousands)")
    axes[0].legend();fig.suptitle("Relay-aware BA2 at P4: structural extrapolations",fontsize=12)
    fig.savefig(HERE/"structural_comparison.png",dpi=160);plt.close(fig)
    dump(HERE/"provenance.json",dict(command=[sys.executable,"-B",str(Path(__file__).resolve())],
                                    base_git_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=tb.ROOT,text=True).strip(),
                                    implementation_hashes={str(p.relative_to(tb.ROOT)):tb.sha(p) for p in
                                        (Path(__file__),BENCH/"testbench.py",tb.ROOT/"reference/relay_bp_fixed.py",
                                         tb.ROOT/"results/bank-aware-folding-layout/run_bank_aware_layout.py",
                                         tb.ROOT/"results/graph-partitioning-folding-model/run_folding_layout_comparison.py")},
                                    versions=dict(python=sys.version,numpy=np.__version__,stim=tb.stim.__version__),
                                    outputs={str(p.relative_to(HERE)):tb.sha(p) for p in HERE.rglob("*") if p.is_file() and p!=HERE/"provenance.json"}))
    print("ALL FOUR CODES PASS; protected historical files unchanged",flush=True)


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        dump(HERE/"STOPPED.json",dict(error=type(exc).__name__,reason=str(exc)))
        raise

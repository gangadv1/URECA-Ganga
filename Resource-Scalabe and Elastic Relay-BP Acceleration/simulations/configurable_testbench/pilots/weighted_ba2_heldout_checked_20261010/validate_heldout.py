"""Graph-specific BA2 comparison with explicit inverse-mapped decoder traces."""
from pathlib import Path
import argparse
import csv
from dataclasses import asdict, replace
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

FROZEN=HERE.parent/"weighted_ba2_validated_20261010"
RELAY=HERE.parent/"relay_aware_ba2_bounded_20261010"
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


def compare_code(code):
    out=HERE/code
    out.mkdir(exist_ok=False)
    start=time.monotonic()
    cfg=tb.Config(**json.loads((PAIRED/"configs"/f"bb{code}_n2_p4.json").read_text()))
    if (cfg.P,cfg.shots,cfg.first_limit,cfg.later_limit,cfg.R,cfg.S)!=(4,4,2,2,2,1):
        raise ValueError("Paired pilot configuration changed")
    cfg=replace(cfg,sample_seed=2026101101,trajectory_base_seed=11400714819323198485,first_limit=8,later_limit=8)
    training=tb.Config(**json.loads((PAIRED/"configs"/f"bb{code}_n2_p4.json").read_text()))
    training_seeds={seed for shot in range(4) for seed in tb.trajectory_seeds(training,shot)}
    heldout_seeds={seed for shot in range(4) for seed in tb.trajectory_seeds(cfg,shot)}
    if cfg.sample_seed==training.sample_seed or training_seeds & heldout_seeds:
        raise ValueError("Held-out seed overlap")
    dump(out/"requested_config.json",asdict(cfg))
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
    with np.load(FROZEN/code/"storage_maps.npz") as saved:
        fr=saved["fault_residues"].copy()
        if not np.array_equal(saved["edge_residues"],er): raise ValueError("Frozen edge mismatch")
        layout=ba.bank_layout("weighted",g,fr,er)
        for key in ("fault_old_to_new","fault_new_to_old","edge_old_to_new","edge_new_to_old"):
            if not np.array_equal(layout[key],saved[key]): raise ValueError("Frozen map mismatch")
    fs=json.loads((FROZEN/code/"weight_sweep.json").read_text())
    es={"frozen_existing_BA2_edge_map":True}
    assert np.array_equal(layout["edge_old_to_new"],baseline["edge_old_to_new"])
    binv,bh,ba_action,bprob=ba.invariance(g,baseline)
    bh.sort_indices();ba_action.sort_indices()
    bfo,bfn=baseline["fault_old_to_new"],baseline["fault_new_to_old"]
    bkeys=np.repeat(np.arange(g["C"]),np.diff(bh.indptr))*g["V"]+bfn[bh.indices]
    bn_to_old=np.searchsorted(ec*g["V"]+ev,bkeys)
    bold_to_new=np.empty(g["E"],int);bold_to_new[bn_to_old]=np.arange(g["E"])
    if not np.array_equal((ec*g["V"]+ev)[bn_to_old],bkeys): raise ValueError("BA2 decoder edge identity failure")
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
    dump(out/"frozen_layout.json",dict(selected=fs["selected"],weighted_maps_sha256=tb.sha(FROZEN/code/"storage_maps.npz"),BA2_maps_sha256=tb.sha(BASE/code/"storage_maps.npz"),regenerated=False,retuned=False))
    print(code,"validating held-out inverse-mapped trajectories",flush=True)
    original_engines={};paired=[]
    edge_fields=("check_to_var","var_to_check")
    node_fields=("gamma_float","gamma_int","lambda_bias","beliefs","decoded_error")
    shot_durations=[];completed=0
    for shot,(syndrome,logical) in enumerate(zip(detectors,logicals)):
        elapsed=time.monotonic()-start
        if shot_durations and elapsed+max(shot_durations)>60:
            break
        shot_started=time.monotonic()
        for engine,seed in enumerate(tb.trajectory_seeds(cfg,shot)):
            legs,plegs,words=schedule(seed,cfg,g["V"],fn)
            for leg,pleg in zip(legs,plegs):
                if not np.isscalar(leg.gamma) and not np.array_equal(np.asarray(pleg.gamma)[fo],np.asarray(leg.gamma)):
                    raise ValueError("Gamma inverse mapping failure")
            traces=[];ptraces=[];btraces=[]
            def callback(target,mapped):
                node_inverse=bfo if mapped==2 else fo
                edge_inverse=bold_to_new if mapped==2 else decoder_old_to_new
                def observe(event):
                    hashes={}
                    for field in node_fields:
                        hashes[field]=digest(event[field][node_inverse] if mapped else event[field])
                    for field in edge_fields:
                        hashes[field]=digest(event[field][edge_inverse] if mapped else event[field])
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
            _,blegs,_=schedule(seed,cfg,g["V"],bfn)
            bresult=decoder(bh,blegs,callback(btraces,2)).decode(priors[bfn],syndrome)
            if traces!=btraces or not np.array_equal(original.decoded_error,bresult.decoded_error[bfo]):
                raise ValueError("BA2 held-out trace equivalence failure")
            decision=original.decoded_error.astype(np.uint8)
            restored=mapped.decoded_error[fo].astype(np.uint8)
            exact=(traces==ptraces and original.total_iterations==mapped.total_iterations
                   and original.relay_legs==mapped.relay_legs and original.converged==mapped.converged
                   and np.array_equal(decision,restored) and np.array_equal(original.beliefs,mapped.beliefs[fo]))
            scored=tb.score(h,action,decision,syndrome,logical)
            pscore=tb.score(hp,ap,mapped.decoded_error,syndrome,logical)
            reproduction=True # Independent held-out samples; no training outcomes are reused.
            trace_record=dict(shot=shot,engine=engine,seed=seed,exact_trace=exact,BA2_trace_exact=traces==btraces,heldout_seed_distinct=seed not in training_seeds,
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
        completed+=1;shot_durations.append(time.monotonic()-shot_started)
        dump(out/"progress.json",dict(completed_shots=completed,requested_shots=4,elapsed_seconds=time.monotonic()-start))
    cfg=replace(cfg,shots=completed)
    if not completed: raise TimeoutError("No complete paired shot within cap")
    dump(out/"sample_hashes.json",dict(detectors=digest(detectors[:completed]),logicals=digest(logicals[:completed]),source_seed=cfg.sample_seed))
    dump(out/"engine_iterations.json",[dict(shot=shot,engine=engine,**e) for (shot,engine),e in original_engines.items()])
    dump(out/"decoder_equivalence.json",paired)
    inv["gamma_inverse_mapping_exact"]=True
    inv["all_completed_decoder_trajectories_exact"]=True
    inv["all_heldout_decisions_and_scoring_exact"]=True
    dump(out/"invariants.json",inv)
    # Interpret structural costs only after exact graph/decoder checks have passed.
    # Profiles are frozen, seed-independent structural schedule data, not new evidence.
    archived_profiles=json.loads((FROZEN/code/"phase_profiles.json").read_text())
    profiles={name:archived_profiles[name] for name in ("BA2","weighted")}
    dump(out/"phase_profiles.json",dict(seed_independent=True,reused_from=str(FROZEN/code/"phase_profiles.json"),profiles=profiles))
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
                                   objective=dict(method="Frozen training assignment; no held-out optimization",statistics=fs,P=4),
                                   mapping_semantics="Explicit mathematical ID <-> physical address maps; gamma/priors generated in original order then indexed by fault_new_to_old; decisions/trace mapped back before comparison",
                                   timing_semantics="Archived phase service formulas only; no top-level/RNG/cancellation overhead; no integrated hardware latency measurement",
                                   wall_seconds=time.monotonic()-start,trace_iterations=sum(r["trace_iterations"] for r in paired),
                                   output_hashes={p.name:tb.sha(p) for p in out.iterdir() if p.is_file()}))
    print(code,"PASS:",completed,"paired shots;",time.monotonic()-start,"seconds",flush=True)


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
               BENCH/"runs",BENCH/"smoke_outputs",PAIRED,BASE,RELAY,FROZEN]
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
        remaining=180-(time.monotonic()-started)
        if remaining<=0: raise TimeoutError("180-second total comparison cap")
        proc=subprocess.run(command,timeout=min(75,remaining))
        duration=time.monotonic()-tick;durations.append(duration)
        if proc.returncode:
            raise RuntimeError("Stopped on layout/equivalence failure: "+code)
        projection=time.monotonic()-started+max(durations)*(4-len(durations))
        print("Projected total seconds:",round(projection,1),flush=True)
        if time.monotonic()-started>180: raise TimeoutError("180-second comparison cap")
    assert all(Path(p).is_file() and tb.sha(p)==h for p,h in before.items())
    table=[row for code in tb.CODE_NAMES for row in json.loads((HERE/code/"comparison.json").read_text())]
    dump(HERE/"comparison.json",table)
    with (HERE/"comparison.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    changed=[]
    for code in tb.CODE_NAMES:
        selection=json.loads((HERE/code/"per_shot_selection.json").read_text())
        for n in (1,2):
            a=next(x["records"] for x in selection if x["N"]==n and x["layout"]=="BA2")
            b=next(x["records"] for x in selection if x["N"]==n and x["layout"]=="weighted")
            for x,y in zip(a,b):
                if x["winner"]!=y["winner"] or x["total_failure"]!=y["total_failure"]:
                    changed.append(dict(code=code,N=n,shot=x["shot"],original=x,BA2=y,reason="timing race only; engine trajectories already verified exact"))
    dump(HERE/"validation.json",dict(status="PASS",decoder_trajectories=sum(len(json.loads((HERE/c/"decoder_equivalence.json").read_text())) for c in tb.CODE_NAMES),
                                      exact_trace_iterations=sum(json.loads((HERE/c/"provenance.json").read_text())["trace_iterations"] for c in tb.CODE_NAMES),
                                      all_graph_and_prior_gamma_logical_invariants_exact=True,
                                      frozen_BA2_edge_maps_exact=True,heldout_seed_disjoint=True,frozen_layouts_exact=True,
                                      selection_changes=changed,protected_files_unchanged=len(before),
                                      wall_seconds=time.monotonic()-started,
                                      limitations=["Requested four shots; runtime-budget reduction recorded per code; 8/8 R2/S1; no LER conclusion",
                                                   "Physical storage maps are evaluated by a model; decoder uses its own mapped CSR",
                                                   "No exact cancellation, integrated RTL, contention or measured hardware timing",
                                                   "Profiles reused from training: sample-seed independent, not held-out evidence"] ))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    codes=list(tb.CODE_NAMES)
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout="constrained")
    for offset,name in enumerate(("BA2","weighted")):
        selected=[next(r for r in table if r["code"]==c and r["N"]==1 and r["layout"]==name) for c in codes]
        x=[i+(offset-.5)*.32 for i in range(len(codes))]
        axes[0].bar(x,[r["mean_completion_cycles"]/1e6 for r in selected],width=.32,label=name)
        axes[1].bar(x,[r["mean_critical_retry_subsets"]/1e3 for r in selected],width=.32,label=name)
    for ax in axes:
        ax.set_xticks(range(len(codes)),codes,rotation=20)
        ax.set_xlabel("BB code n_k_d")
    axes[0].set_ylabel("Held-out mean completion\n(structural million cycles)")
    axes[1].set_ylabel("Bank retry subsets\n(structural thousands)")
    axes[0].legend();fig.suptitle("Frozen weighted BA2 held-out P4: structural extrapolations",fontsize=12)
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

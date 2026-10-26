"""Bounded paired pilot. Only this fresh pilot directory receives outputs."""
from pathlib import Path
from dataclasses import asdict
import csv
import json
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
BENCH = HERE.parents[1]
sys.path.insert(0,str(BENCH))
import testbench as tb


def read_csv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_json(name,value):
    (HERE/name).write_text(json.dumps(value,indent=2)+"\n")


def main():
    started=time.monotonic()
    if (HERE/"configs").exists() or (HERE/"runs").exists():
        raise FileExistsError("Pilot outputs already exist; use a fresh directory")
    protected=[tb.ROOT/"graphs/generated",tb.ROOT/"graphs/sources",
               tb.ROOT/"reference",tb.ROOT/"results",BENCH/"testbench.py",
               BENCH/"README.md",BENCH/"smoke_config.json",BENCH/"test_testbench.py",
               BENCH/"smoke_outputs",BENCH/"runs"]
    before={str(p):tb.sha(p) for root in protected for p in
            ([root] if root.is_file() else root.rglob("*")) if p.is_file()}
    write_json("protected_input_hashes.json",before)
    configs={}
    availability={}
    for code in tb.CODE_NAMES:
        cfg=tb.Config(code=code,physical_p=.003,N=2,P=4,shots=4,
                      sample_seed=20261010,first_limit=2,later_limit=2,R=2,S=1,
                      timing_model="folding_original",sample_mode="circuit")
        directory,pkg,manifest,circuit,h,action,priors=tb.load_problem(cfg)
        availability[code]=dict(package=str(directory),dimensions=[*h.shape,action.shape[0]],
                                source_sha256=manifest["provenance"]["source_circuit_sha256"],
                                package_manifest_sha256=tb.sha(directory/"manifest.json"))
        for n in (1,2):
            for p in (2,4):
                values=asdict(cfg);values.update(N=n,P=p)
                c=tb.Config(**values);c.validate()
                configs[f"bb{code}_n{n}_p{p}"]=c
    write_json("package_preflight.json",availability)
    (HERE/"configs").mkdir();(HERE/"runs").mkdir()
    commands=[];durations={}
    # Largest problem first: project conservatively before committing to 16 runs.
    first="bb288_12_18_n2_p4"
    order=[first]+[key for key in configs if key!=first]
    for index,key in enumerate(order):
        cfg=configs[key];config_path=HERE/"configs"/(key+".json")
        config_path.write_text(json.dumps(asdict(cfg),indent=2)+"\n")
        command=[sys.executable,"-B",str(BENCH/"testbench.py"),"--config",str(config_path),
                 "--output",str(HERE/"runs"/key)]
        commands.append(command);write_json("commands.json",commands)
        tick=time.monotonic()
        try:
            result=subprocess.run(command,capture_output=True,text=True,timeout=60)
        except subprocess.TimeoutExpired:
            write_json("STOPPED.json",dict(reason="Single configuration exceeded 60 seconds",configuration=key))
            raise
        durations[key]=time.monotonic()-tick
        (HERE/(key+".log")).write_text(result.stdout+result.stderr)
        if result.returncode:
            write_json("STOPPED.json",dict(reason="Invalid configuration or testbench failure",configuration=key))
            raise RuntimeError(result.stderr)
        elapsed=time.monotonic()-started
        projected=elapsed+durations[first]*(len(order)-index-1)
        print(f"{key}: {durations[key]:.2f}s; elapsed={elapsed:.1f}s; conservative projected={projected:.1f}s",flush=True)
        if projected>180:
            write_json("STOPPED.json",dict(reason="Projected pilot runtime exceeds 180 seconds",projected_seconds=projected))
            raise RuntimeError("Projected runtime excessive")
    data={key:dict(shots=read_csv(HERE/"runs"/key/"per_shot.csv"),
                   engines=read_csv(HERE/"runs"/key/"per_engine.csv"),
                   summary=json.loads((HERE/"runs"/key/"summary.json").read_text()),
                   manifest=json.loads((HERE/"runs"/key/"manifest.json").read_text())) for key in configs}
    checks=0;anomalies=[];changes=[]
    immutable=("seed","iterations","legs","syndrome_converged","rng_words","decision_hash",
               "nonconvergence","syndrome_valid_logical_error","total_failure")
    for code in tb.CODE_NAMES:
        baseline=data[f"bb{code}_n1_p2"]
        for n in (1,2):
            for p in (2,4):
                run=data[f"bb{code}_n{n}_p{p}"]
                for ref,row in zip(baseline["shots"],run["shots"]):
                    assert (ref["shot"],ref["detector_hash"],ref["logical_hash"])==(row["shot"],row["detector_hash"],row["logical_hash"])
                    checks+=1
                ref_eng={e["shot"]:e for e in baseline["engines"]}
                for e in run["engines"]:
                    if e["engine"]=="0":
                        assert all(e[k]==ref_eng[e["shot"]][k] for k in immutable)
                        checks+=1
                for row in run["shots"]:
                    engines=[e for e in run["engines"] if e["shot"]==row["shot"]]
                    successes=[(int(e["result_cycles"]),int(e["engine"])) for e in engines if e["syndrome_converged"]=="True"]
                    selected=min(successes) if successes else (max(int(e["result_cycles"]) for e in engines),-1)
                    assert selected==(int(row["modeled_completion_cycles"]),int(row["winner_engine"]))
                    checks+=1
                summary=run["summary"]
                assert summary["total_failure"]["count"]==summary["nonconvergence"]["count"]+summary["syndrome_valid_logical_error"]["count"]
                for name,digest in run["manifest"]["output_hashes"].items():
                    assert tb.sha(HERE/"runs"/f"bb{code}_n{n}_p{p}"/name)==digest
        for n in (1,2):
            left,right=data[f"bb{code}_n{n}_p2"],data[f"bb{code}_n{n}_p4"]
            for a,b in zip(left["engines"],right["engines"]):
                assert all(a[k]==b[k] for k in immutable)
                checks+=1
            for a,b in zip(left["shots"],right["shots"]):
                if a["winner_engine"]!=b["winner_engine"]:
                    anomalies.append(dict(code=code,N=n,shot=a["shot"],kind="timing-only P winner change",p2=a["winner_engine"],p4=b["winner_engine"]))
        for p in (2,4):
            left,right=data[f"bb{code}_n1_p{p}"],data[f"bb{code}_n2_p{p}"]
            for a,b in zip(left["shots"],right["shots"]):
                if (a["winner_engine"],a["total_failure"],a["modeled_completion_cycles"])!=(b["winner_engine"],b["total_failure"],b["modeled_completion_cycles"]):
                    changes.append(dict(code=code,P=p,shot=a["shot"],n1_winner=a["winner_engine"],n2_winner=b["winner_engine"],n1_failure=a["total_failure"],n2_failure=b["total_failure"],n1_cycles=a["modeled_completion_cycles"],n2_cycles=b["modeled_completion_cycles"]))
    # Original Gross folding regression, preserving exact service-model baseline.
    expected=read_csv(tb.ROOT/"results/folding-factor-sweep/phase_retry_summary.csv")
    for p in (2,4):
        actual=data[f"bb144_12_12_n1_p{p}"]["summary"]["folding_metrics"]["phases"]
        for row in expected:
            if row["P"]==str(p) and row["layout"]=="original":
                phase=actual[row["phase"]]
                assert phase["estimated_cycles"]==int(row["estimated_cycles"])
                assert phase["retry_subsets"]==int(row["retry_subsets"])
                assert abs(phase["mean_lane_utilization"]-float(row["lane_utilization"]))<1e-12
                checks+=1
    assert all(Path(p).is_file() and tb.sha(p)==digest for p,digest in before.items())
    table=[]
    for key,cfg in configs.items():
        run=data[key];summary=run["summary"];phases=summary["folding_metrics"]["phases"]
        retries=[];occupancy=[];critical_iterations=[]
        for row in run["shots"]:
            engines=[e for e in run["engines"] if e["shot"]==row["shot"]]
            winner=int(row["winner_engine"])
            critical=engines[winner] if winner>=0 else max(engines,key=lambda e:int(e["result_cycles"]))
            repetitions={k:int(critical["legs"] if k=="relay_init" else critical["iterations"]) for k in phases}
            retries.append(sum(repetitions[k]*phases[k]["retry_subsets"] for k in phases))
            groups=sum(repetitions[k]*phases[k]["issued_groups"] for k in phases)
            active=sum(repetitions[k]*phases[k]["logical_accesses"] for k in phases)
            occupancy.append(active/(groups*cfg.P))
            critical_iterations.append(int(critical["iterations"]))
        avg=lambda xs:sum(xs)/len(xs)
        rate=summary["total_failure"]
        table.append(dict(code=cfg.code,N=cfg.N,P=cfg.P,shots=cfg.shots,
                          failure_count=rate["count"],failure_rate=rate["rate"],failure_wilson95=rate["wilson95"],
                          nonconvergence=summary["nonconvergence"]["count"],
                          syndrome_valid_logical_errors=summary["syndrome_valid_logical_error"]["count"],
                          mean_engine_iterations=avg([int(e["iterations"]) for e in run["engines"]]),
                          mean_winner_iterations=None if summary["winner_iterations"] is None else summary["winner_iterations"]["mean"],
                          mean_critical_iterations=avg(critical_iterations),
                          mean_modeled_cycles=summary["modeled_latency_cycles"]["mean"],
                          mean_critical_bank_retry_subsets=avg(retries),
                          mean_critical_issue_group_occupancy=avg(occupancy),
                          structural_retry_subsets=summary["folding_metrics"]["all_phases_once"]["retry_subsets"],
                          structural_conflict_events=summary["folding_metrics"]["all_phases_once"]["conflict_events"],
                          timing_label="structural_extrapolation_not_RTL_calibrated",
                          wall_seconds=durations[key]))
    with (HERE/"comparison.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    write_json("comparison.json",table)
    write_json("validation.json",dict(status="PASS",pairing_and_regression_checks=checks,
                                       protected_files_unchanged=len(before),P_selection_changes=anomalies,N_first_success_changes=changes,
                                       elapsed_seconds=time.monotonic()-started,
                                       cancellations="Unavailable: no acknowledgement/quiescence timestamps",
                                       occupancy_scope="Critical natural trajectory; issued-group occupancy, not elapsed PE utilization",
                                       budgets=dict(shots=4,first_limit=2,later_limit=2,R=2,S=1,max_iterations=4),
                                       timing_policy="All 16 configurations use folding_original for like-for-like P comparison; Gross P4 canonical calibration is available but not mixed in"))
    # Static, exportable plots from actual generated pilot rows only; no LER trend.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    codes=list(tb.CODE_NAMES)
    for offset,(n,p) in enumerate([(1,2),(1,4),(2,2),(2,4)]):
        subset=[next(row for row in table if row["code"]==code and row["N"]==n and row["P"]==p) for code in codes]
        x=[i+(offset-1.5)*.18 for i in range(len(codes))]
        axes[0].bar(x,[r["mean_modeled_cycles"]/1e6 for r in subset],width=.18,label=f"N{n}/P{p}")
        axes[1].bar(x,[r["mean_critical_bank_retry_subsets"]/1e3 for r in subset],width=.18,label=f"N{n}/P{p}")
    for ax in axes:
        ax.set_xticks(range(len(codes)),codes,rotation=20);ax.set_xlabel("BB code n_k_d")
    axes[0].set_ylabel("Mean modeled completion (million cycles)")
    axes[1].set_ylabel("Mean critical-trajectory retry subsets (thousands)")
    axes[0].legend();fig.suptitle("Paired 4-shot pilot: structural extrapolation, maximum 4 iterations/engine")
    fig.tight_layout();fig.savefig(HERE/"modeled_cycles_and_retries.png",dpi=160);plt.close(fig)
    write_json("pilot_provenance.json",dict(driver_sha256=tb.sha(__file__),git_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=tb.ROOT,text=True).strip(),
                                            outputs={str(p.relative_to(HERE)):tb.sha(p) for p in HERE.rglob("*") if p.is_file() and p.name!="pilot_provenance.json"},
                                            exact_driver_command=[sys.executable,"-B",str(Path(__file__).resolve())]))
    print("PASS:",len(table),"configurations;",checks,"pairing/regression checks; protected files unchanged.",flush=True)


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        write_json("failure_diagnosis.json",dict(error=type(exc).__name__,message=str(exc)))
        raise

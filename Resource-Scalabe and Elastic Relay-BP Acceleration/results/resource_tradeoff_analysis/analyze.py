from pathlib import Path
import csv,json,hashlib
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
SOURCES=["results/n-scaling-canonical/per_shot_results.csv","results/n-scaling-canonical/aggregate_summary.json","results/n-scaling-canonical/manifest.json","results/n-scaling-canonical-n8-complete/per_shot_results.csv","results/m4-memory-fabric-synthesis/final_synthesis_report.md","results/m4-memory-fabric-synthesis/full_fabric_resources.csv","results/m4-memory-fabric-synthesis/timing_summary.csv","results/m4-memory-fabric-rtl/synthesis_summary.csv","results/vivado-n1-baseline/summary.md","results/gari-vs-relaybp-system/relaybp_memory_summary.json","results/relaybp-memory-optimization/final_memory_report.md"]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={s:sha(ROOT/s) for s in SOURCES}
load=lambda p:json.loads(p.read_text())
with (ROOT/SOURCES[0]).open() as f: shots=list(csv.DictReader(f))
with (ROOT/SOURCES[3]).open() as f: old=list(csv.DictReader(f))
aggregate=load(ROOT/SOURCES[1]);manifest=load(ROOT/SOURCES[2]);assert len(shots)==len(old)==128 and manifest["configuration"]["P"]==4
ns=[1,2,4,8,16];arrays={n:np.array([float(r[f"n{n}_cycles"]) for r in shots]) for n in ns};table=[]
for i,n in enumerate(ns):
 a=arrays[n];mean=float(a.mean());p99=float(np.percentile(a,99,method="linear"));syn=sum(int(r[f"n{n}_syndrome_converged"]) for r in shots);success=sum(int(r[f"n{n}_logical_correct"]) for r in shots);nonconv=sum(int(r[f"n{n}_non_convergence"]) for r in shots);logical=sum(int(r[f"n{n}_syndrome_valid_logical_error"]) for r in shots)
 assert np.isclose(mean,aggregate["latency"][f"n{n}"]["mean"],rtol=0,atol=1e-6) and np.isclose(p99,aggregate["latency"][f"n{n}"]["p99"],rtol=0,atol=1e-6)
 assert nonconv==aggregate["logical"][f"n{n}"]["non_convergence"] and logical==aggregate["logical"][f"n{n}"]["syndrome_valid_logical_errors"]
 assert success+nonconv+logical==128
 if n<=8: assert [r[f"n{n}_cycles"] for r in shots]==[r[f"n{n}_cycles"] for r in old]
 row=dict(N=n,provisioned_lanes=4*n,mean_cycles=mean,p99_cycles=p99,mean_provisioned_lane_cycles=mean*4*n,p99_provisioned_lane_cycles=p99*4*n,syndrome_success=syn,logical_success=success,nonconvergence=nonconv,syndrome_valid_logical_errors=logical,total_failure=nonconv+logical)
 for metric,value in [("mean",mean),("p99",p99)]:
  base=arrays[1].mean() if metric=="mean" else np.percentile(arrays[1],99)
  prev=(arrays[ns[i-1]].mean() if metric=="mean" else np.percentile(arrays[ns[i-1]],99)) if i else value
  row[metric+"_improvement_vs_N1_percent"]=100*(1-value/base);row[metric+"_improvement_vs_previous_percent"]=100*(1-value/prev) if i else None
 table.append(row)
for metric in ("mean_cycles","p99_cycles"):
 for r in table:
  r[metric+"_pareto_nondominated"]=not any(q["provisioned_lanes"]<=r["provisioned_lanes"] and q[metric]<=r[metric] and (q["provisioned_lanes"]<r["provisioned_lanes"] or q[metric]<r[metric]) for q in table)
def write_csv(name,rows):
 with (OUT/name).open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
write_csv("comparison.csv",table)
deadlines=np.array([.3,.5,.75,1,1.1,1.5,2,4,8])*1e9;deadline_rows=[]
for d in deadlines:
 for n in ns:
  met=arrays[n]<=d;valid=np.array([int(r[f"n{n}_logical_correct"]) for r in shots],bool)
  deadline_rows.append(dict(hypothetical_deadline_cycles=int(d),N=n,completion_by_deadline_count=int(met.sum()),shots=128,completion_by_deadline_fraction=float(met.mean()),logical_success_by_deadline_count=int((met&valid).sum()),logical_success_by_deadline_fraction=float((met&valid).mean())))
write_csv("hypothetical_deadlines.csv",deadline_rows)
plt.rcParams.update({"font.size":13,"axes.spines.top":False,"axes.spines.right":False,"axes.titleweight":"bold"})
colors=["#64748b","#2563eb","#7c3aed","#059669","#d97706"]
def finish(fig,name,foot):
 fig.subplots_adjust(left=.12,right=.96,bottom=.23,top=.84);fig.text(.08,.04,foot,fontsize=10,color="#475569")
 for ext in ("png","pdf"):fig.savefig(OUT/f"{name}.{ext}",dpi=320,facecolor="white")
 plt.close(fig)
for metric,label,file in [("mean_cycles","Mean","graph1_mean_latency_vs_lanes"),("p99_cycles","p99","graph2_p99_latency_vs_lanes")]:
 fig,ax=plt.subplots(figsize=(12,7));lanes=[r["provisioned_lanes"] for r in table];y=[r[metric]/1e6 for r in table]
 ax.plot(lanes,y,"--",color="#94a3b8",lw=2,label="Observed latency–lane Pareto frontier")
 for r,v,c in zip(table,y,colors):
  ax.scatter(r["provisioned_lanes"],v,s=100,color=c,zorder=3);ax.annotate(f"N={r['N']}\n{v:,.1f} M cycles",(r["provisioned_lanes"],v),xytext=(0,15),textcoords="offset points",ha="center",fontsize=11)
 ax.set_xscale("log",base=2);ax.set_xticks(lanes,[str(x) for x in lanes]);ax.set_yscale("log");ax.set_ylim(min(y)*.70,max(y)*1.7);ax.set_xlabel("Provisioned lanes = N × 4 (hardware provisioning proxy)");ax.set_ylabel(f"{label} modeled completion latency\n(million cycles; log scale)",fontsize=12);ax.set_title(f"{label} latency vs lane provisioning: every N is nondominated",pad=20);ax.grid(alpha=.2);ax.legend(loc="upper right",fontsize=11)
 finish(fig,file,"Canonical Gross [[144,12,12]], P4, 128 paired shots, p=.003. Fewer lanes and lower latency are both objectives.\nLane count is not FPGA area. Modeled cycles are not measured FPGA timing; p99 is tail-sensitive with 128 shots.")
fig,ax=plt.subplots(figsize=(12,7));grid=np.unique(np.concatenate(([.2e9,8e9],*[a[(a>=.2e9)&(a<=8e9)] for a in arrays.values()])))
for n,c in zip(ns,colors): ax.step(grid/1e9,[(arrays[n]<=d).mean()*100 for d in grid],where="post",color=c,lw=2.4,label=f"N={n}, {4*n} lanes")
ax.axhline(95,color="#475569",ls=":",lw=1,label="Hypothetical 95% target");ax.set_xscale("log");ax.set_xticks([.3,.5,.75,1,1.5,2,4,8],["0.3","0.5","0.75","1","1.5","2","4","8"]);ax.set_ylim(0,104);ax.set_xlabel("Hypothetical deadline (billion modeled cycles; log scale)");ax.set_ylabel("Shots completed by deadline (%)");ax.set_title("Hypothetical deadline coverage vs provisioned lanes",pad=20);ax.legend(loc="lower right",fontsize=10);ax.grid(alpha=.2)
finish(fig,"graph3_hypothetical_deadlines","128 paired shots; deadlines and 95% target are illustrative, not application requirements. Completion includes all-fail returns.\nSuccessful decoding by deadline is recorded separately in CSV. No clock/Fmax conversion or real-time claim.")
examples=[]
for d in (2e9,1.1e9,.75e9):
 passing=[r for r in deadline_rows if r["hypothetical_deadline_cycles"]==d and r["logical_success_by_deadline_fraction"]>=.95]
 best=min(passing,key=lambda r:r["N"]);examples.append(best)
report=['# Resource-aware canonical N-scaling analysis','', 'Only archived results were analyzed. Gross [[144,12,12]], physical p=.003, P4, 128 paired shots, four sample seeds; R32, first/later 80/60, S1. Modeled architectural cycles preserve archived first-success/last-engine-on-all-fail semantics. Phase costs have RTL calibration evidence; complete FPGA timing is not measured.', '', '| N | Lanes | Mean cycles | p99 cycles | Mean × lanes | p99 × lanes | Success / failure | Mean gain vs N1 / previous | p99 gain vs N1 / previous |','|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
for r in table:
 prev=lambda key:'—' if r[key] is None else f"{r[key]:.2f}%"
 report.append(f"| {r['N']} | {r['provisioned_lanes']} | {r['mean_cycles']:,.2f} | {r['p99_cycles']:,.2f} | {r['mean_provisioned_lane_cycles']:,.2f} | {r['p99_provisioned_lane_cycles']:,.2f} | {r['logical_success']} / {r['total_failure']} | {r['mean_improvement_vs_N1_percent']:.2f}% / {prev('mean_improvement_vs_previous_percent')} | {r['p99_improvement_vs_N1_percent']:.2f}% / {prev('p99_improvement_vs_previous_percent')} |")
report+=['', 'Products are provisioned lane-cycle proxies: elapsed completion cycles × N × P. They are neither busy executed work nor actual FPGA area-delay product and do not model cancellation/drain utilization. No historical active_work is used. N1 has three nonconvergences; all other N have zero failures. No syndrome-valid logical errors were observed. Zero failures in 128 shots still has Wilson 95% upper bound about 2.91%.', '', 'Pareto rule: a point is dominated only if another uses no more lanes and has no greater latency, with at least one strict improvement. All five configurations are nondominated for both mean and p99: latency falls as provisioning rises. No point is uniquely optimal without a budget or utility. N16 is best for absolute observed mean/p99 but doubles N8 lanes for just 2.25% mean and 8.85% p99 gain. N1 minimizes mean lane-cycle product; N2 minimizes p99 lane-cycle product. These proxy minima do not establish minimum area-delay or energy.', '', 'Recommendations under explicit priorities:', '', '- Minimum hardware provisioning: N1 (four lanes) is the true minimum. If requiring at least two trajectories or eliminating the three observed N1 failures, N2 (eight lanes) is the smallest ensemble; actual FPGA fit remains unverified.', '- Average-latency compromise: N4 (16 lanes) reduces mean by 48.31% vs N1 and 20.30% vs N2. Choose it only if that gain justifies doubling N2 provisioning. N16 wins absolute mean, not resource efficiency.', '- Tail-latency priority: N8 (32 lanes) cuts p99 by 61.84% vs N4 and 91.22% vs N1. It is a practical tail-focused compromise; N16 cuts a further 8.85% for twice the lanes. N2 is the best observed p99×lanes proxy if provisioning dominates.', '- Deadline satisfaction: select the smallest N meeting a declared target, using success-by-deadline rather than completion alone when correctness is required. The examples below are explicitly hypothetical, chosen to illustrate priorities rather than assert a real deadline.']
for r in examples: report.append(f"  - At {r['hypothetical_deadline_cycles']/1e9:g} billion cycles and a hypothetical ≥95% successful-by-deadline target, smallest observed qualifying N is {r['N']}: {r['logical_success_by_deadline_count']}/128 ({100*r['logical_success_by_deadline_fraction']:.2f}%).")
report+=['', 'Deadline formulas: completion fraction = count(completion_cycles ≤ D)/128; successful fraction additionally requires archived logical_correct=1. Grid: 0.3, 0.5, 0.75, 1, 1.1, 1.5, 2, 4, 8 billion hypothetical cycles. Graph is an empirical completion CDF; CSV contains both completion and success counts. Outcomes are paired across N. No true application deadline or clock is invented.', '', 'Resource evidence: results/m4-memory-fabric-synthesis/final_synthesis_report.md says BLOCKED BEFORE SYNTHESIS; full_fabric_resources.csv and timing_summary.csv contain NOT EXECUTED entries. results/m4-memory-fabric-rtl/synthesis_summary.csv likewise contains no inferred counts. results/vivado-n1-baseline/summary.md reports missing target/toolchain. No actual Relay-BP LUT/FF/BRAM/DSP/Fmax or area-delay product is available; literature GARI figures are a different design.', '', 'A defensible architecture-specific capacity model exists in results/gari-vs-relaybp-system/relaybp_memory_summary.json: one original P4 engine has 15,407,678 static bits + 16,934,998 input/dynamic bits = 32,342,676 bits, 900 per-array/four-bank BRAM36 capacity equivalents. Current N2 duplicates full fabrics: 64,685,352 bits / 1,800 banked capacity equivalents. Conditional full replication would give 32,342,676×N bits and 900×N capacity equivalents, but N4/8/16 implementation, routing, clocks and packing are not verified. M4 sharing/aliasing has different analytical estimates and cannot be mixed with this original replication model. All such counts are analytical storage capacity, not actual resource utilization or area. Sharing may require port replication and contention; no performance benefit is assumed.', '', 'Limitations: 128 samples constrain tail estimates (p99 depends on roughly the largest two observations) and failure conclusions. Hypothetical deadline coverage is empirical, not a guaranteed service level or a statistically significant comparison. Modeled N trajectories assume dedicated P-lane engines; FPGA timing closure, shared-resource stalls, cancellation effects and clock scaling are not characterized by these plots. No decoding, synthesis, commit or push was run.', '', 'Inputs (exact paths relative to project root):']
report += ['- `'+s+'`' for s in SOURCES]
report+=['', 'Outputs: comparison.csv, hypothetical_deadlines.csv, report.md, three 3840×2240 PNGs and vector PDFs, analyze.py, validation.json and provenance.json. All calculations are plotting/analysis only. Mean = arithmetic mean; p99 = NumPy linear percentile rank 0.99×127; improvement = 100×(1−new/old).', '', 'Command from project directory:', '```sh','MPLCONFIGDIR=/private/tmp/relay-resource-matplotlib ../.venv/bin/python -B results/resource_tradeoff_analysis/analyze.py','```']
(OUT/"report.md").write_text('\n'.join(report)+'\n')
assert all(sha(ROOT/s)==h for s,h in before.items())
(OUT/"validation.json").write_text(json.dumps(dict(status="PASS",shots=128,raw_means_p99_match_aggregates=True,counts_match_aggregate=True,N1_N8_archive_row_equality=True,all_mean_and_p99_points_nondominated=True,source_hashes_unchanged=True,area_delay_product="UNAVAILABLE",hypothetical_deadline_examples=examples),indent=2)+'\n')
(OUT/"provenance.json").write_text(json.dumps(dict(source_sha256=before,script_sha256=sha(Path(__file__)),versions=dict(numpy=np.__version__,matplotlib=matplotlib.__version__),command="MPLCONFIGDIR=/private/tmp/relay-resource-matplotlib ../.venv/bin/python -B results/resource_tradeoff_analysis/analyze.py",outputs={x.name:sha(x) for x in OUT.iterdir() if x.is_file() and x.name!="provenance.json"}),indent=2)+'\n')
print(json.dumps(examples,indent=2));print("PASS: verified 128 shots; products, Pareto/deadlines, report and 3 PNG/PDF graphs created")

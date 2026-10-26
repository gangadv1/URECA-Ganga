from pathlib import Path
import csv,json,hashlib
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
PILOT=ROOT/"simulations/configurable_testbench/pilots"
DIRS=[ROOT/"results/n-scaling-canonical",ROOT/"results/n-scaling-canonical-n8-complete"]+[PILOT/x for x in ["ba2_graph_specific_20261010","relay_aware_ba2_bounded_20261010","weighted_ba2_validated_20261010","weighted_ba2_heldout_checked_20261010"]]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={str(p.relative_to(ROOT)):sha(p) for d in DIRS for p in d.rglob("*") if p.is_file()}
load=lambda p:json.loads(p.read_text())
canon=load(DIRS[0]/"aggregate_summary.json")
manifest=load(DIRS[0]/"manifest.json")
assert manifest["configuration"]["P"]==4 and canon["shots"]==128
with (DIRS[0]/"per_shot_results.csv").open() as f: shots=list(csv.DictReader(f))
with (DIRS[1]/"per_shot_results.csv").open() as f: older=list(csv.DictReader(f))
assert len(shots)==len(older)==128
ns=[1,2,4,8,16];values=[]
for n in ns:
 x=np.array([float(s[f"n{n}_cycles"]) for s in shots])
 mean=float(x.mean());p99=float(np.percentile(x,99,method="linear"))
 assert np.isclose(mean,canon["latency"][f"n{n}"]["mean"],rtol=0,atol=1e-6)
 assert np.isclose(p99,canon["latency"][f"n{n}"]["p99"],rtol=0,atol=1e-6)
 if n<=8: assert [s[f"n{n}_cycles"] for s in shots]==[s[f"n{n}_cycles"] for s in older]
 values.append(dict(N=n,mean_cycles=mean,p99_cycles=p99))
tables=[load(d/"comparison.json") for d in DIRS[2:]]
for d in DIRS[2:]: assert load(d/"validation.json")["status"]=="PASS"
codes=["18_4_3","72_12_6","144_12_12","288_12_18"]
select=lambda table,c,name:next(r for r in table if r["code"]==c and r["N"]==1 and r["layout"]==name)
banking=[]
for c in codes:
 original=select(tables[0],c,"original")["structural_cycles"]
 ba2=select(tables[0],c,"BA2")["structural_cycles"]
 relay=select(tables[1],c,"BA2_relay")["structural_cycles"]
 weighted=select(tables[2],c,"weighted")["structural_cycles"]
 for t in tables[1:]: assert select(t,c,"BA2")["structural_cycles"]==ba2
 assert select(tables[2],c,"original")["structural_cycles"]==original
 assert select(tables[2],c,"relay_only")["structural_cycles"]==relay
 assert select(tables[3],c,"weighted")["structural_cycles"]==weighted
 for name,count in [("original",original),("BA2",ba2),("relay_only",relay),("weighted",weighted)]:
  directory=DIRS[3] if name=="relay_only" else DIRS[4]
  phase=load(directory/c/"phase_profiles.json")["BA2_relay" if name=="relay_only" else name]
  assert sum(v["estimated_cycles"] for v in phase["phases"].values())==count
 banking.append(dict(code=c,original=original,BA2=ba2,relay_only=relay,weighted=weighted))
plt.rcParams.update({"font.family":"DejaVu Sans","font.size":13,"axes.spines.top":False,"axes.spines.right":False,"axes.titleweight":"bold","savefig.facecolor":"white"})
colors={"original":"#94a3b8","BA2":"#2563eb","weighted":"#059669","relay_only":"#dc2626"}
labels=["[[18,4,3]]","[[72,12,6]]","[[144,12,12]]","[[288,12,18]]"]
def finish(fig,name,foot):
 fig.text(.075,.035,foot,fontsize=10,color="#475569",va="bottom")
 fig.subplots_adjust(left=.1,right=.97,top=.84,bottom=.24)
 for ext in ("png","pdf"): fig.savefig(OUT/f"{name}.{ext}",dpi=320)
 plt.close(fig)
fig,ax=plt.subplots(figsize=(12,7))
for field,label,color,marker in [("mean_cycles","Mean","#2563eb","o"),("p99_cycles","p99","#7c3aed","s")]:
 y=[r[field]/1e6 for r in values];ax.plot(range(5),y,marker=marker,lw=2.8,ms=8,label=label,color=color)
 for i,v in enumerate(y): ax.annotate(f"{v:,.1f}",(i,v),xytext=(0,10 if field=="p99_cycles" else -21),textcoords="offset points",ha="center",fontsize=11,color=color)
mean_drop=100*(1-values[4]["mean_cycles"]/values[3]["mean_cycles"]);tail_drop=100*(1-values[4]["p99_cycles"]/values[3]["p99_cycles"])
ax.set_yscale("log");ax.set_ylim(190,12000);ax.set_xticks(range(5),ns);ax.set_xlabel("Independent decoding trajectories, N (P = 4 per engine)");ax.set_ylabel("Modeled decoding latency (million cycles; log scale)");ax.set_title("More trajectories reduce latency — diminishing returns at N16",pad=20);ax.grid(axis="y",alpha=.2);ax.legend(loc="upper right")
ax.text(.45,.78,f"N8 → N16: mean −{mean_drop:.2f}%; p99 −{tail_drop:.2f}%\nTrajectory count doubles",transform=ax.transAxes,fontsize=12,bbox=dict(boxstyle="round,pad=.6",fc="#f1f5f9",ec="none"))
finish(fig,"graph1_canonical_n_latency","Canonical Gross [[144,12,12]]: 128 paired shots, p = 0.003; mean and linear-interpolated p99.\nModeled first-success / last-engine-on-all-fail latency; not measured FPGA/RTL timing. p99 is tail-sensitive at 128 shots.")
fig,ax=plt.subplots(figsize=(12,7));x=np.arange(4)
for j,name in enumerate(("original","BA2","weighted")):
 y=[100*(1-r[name]/r["original"]) for r in banking];pos=x+(j-1)*.24
 ax.bar(pos,y,width=.24,color=colors[name],label={"original":"Original (reference)","BA2":"Graph-specific BA2","weighted":"Selected weighted BA2"}[name])
 for z,v in zip(pos,y): ax.text(z,v+.25,f"{v:.2f}%",ha="center",fontsize=11)
ax.set_xticks(x,labels);ax.set_ylim(0,13);ax.set_ylabel("Structural cycle reduction vs original (%)");ax.set_xlabel("Circuit-level BB code");ax.set_title("Graph-specific banking reduces structural service cycles",pad=20);ax.legend(loc="upper left",fontsize=11);ax.grid(axis="y",alpha=.2);ax.set_axisbelow(True)
finish(fig,"graph2_banking_vs_original","P = 4; one full iteration + one relay initialization, identical structural phase accounting for all layouts.\nVerified four-shot pilot layouts (2/2 iterations, R2/S1); profile values are seed-independent. Not FPGA/RTL measurements.")
fig,ax=plt.subplots(figsize=(12,7))
for j,name in enumerate(("relay_only","weighted")):
 y=[100*(r[name]/r["BA2"]-1) for r in banking];pos=x+(j-.5)*.3
 ax.bar(pos,y,width=.3,color=colors[name],label="Relay-only banking" if j==0 else "Budget-weighted banking")
 for z,v in zip(pos,y): ax.annotate(f"{v:+.2f}%",(z,v),xytext=(0,8 if v>=0 else -18),textcoords="offset points",ha="center",fontsize=12)
ax.axhline(0,color="#334155",lw=1);ax.set_xticks(x,labels);ax.set_ylim(-1.7,.95);ax.set_ylabel("Structural cycle change vs BA2 (%)\nNegative = fewer cycles; positive = more cycles");ax.set_xlabel("Circuit-level BB code");ax.set_title("Relay-only optimization regresses; weighted banking improves",pad=20);ax.legend(loc="upper center",bbox_to_anchor=(.5,-.15),ncol=2,fontsize=11);ax.grid(axis="y",alpha=.2);ax.set_axisbelow(True)
finish(fig,"graph3_relay_vs_weighted","P = 4; one iteration + one relay initialization. Baseline: existing graph-specific BA2.\nFour-shot pilot layout comparison; no statistical-significance or LER claim. All cycles are structural model estimates.")
(OUT/"plotted_values.json").write_text(json.dumps(dict(canonical=values,banking=banking),indent=2)+"\n")
assert all(sha(ROOT/p)==h for p,h in before.items())
(OUT/"validation.json").write_text(json.dumps(dict(status="PASS",canonical_shots=128,canonical_mean_p99_recomputed=True,N1_N8_archive_latency_rows_exact=True,all_pilot_validation_reports_PASS=True,structural_cycles_match_phase_sums=True,heldout_structural_profiles_exact=True,existing_files_hash_unchanged=len(before),source_sha256=before),indent=2)+"\n")
readme=f"""# URECA professor briefing — 10 October 2026

Three 3840 × 2240 PNGs (320 dpi) and matching vector PDFs. No decoding experiments were run. All cycles are model/structural estimates, not measured FPGA or RTL timing. No significance or LER claims.

1. **graph1_canonical_n_latency**: Gross [[144,12,12]], P4, completed 128-shot N1/2/4/8/16 campaign. Source: `../n-scaling-canonical/per_shot_results.csv`, columns `nN_cycles`; cross-checked `aggregate_summary.json` and `manifest.json`. Mean = arithmetic mean of 128 rows; p99 = NumPy linear percentile (rank 0.99×127). N1–N8 latency rows match `../n-scaling-canonical-n8-complete/per_shot_results.csv`. The archived first-success/last-engine-on-all-fail latency is unchanged. Mean falls {mean_drop:.2f}% and p99 {tail_drop:.2f}% from N8 to N16: diminishing incremental latency returns despite doubling trajectories. Empirical p99 is unstable with only 128 shots. Log y-axis; plotted units are cycles / 1,000,000. No active_work quantity is used.

2. **graph2_banking_vs_original**: four BB codes; original, graph-specific BA2 and selected weighted BA2. Sources: `simulations/configurable_testbench/pilots/ba2_graph_specific_20261010/comparison.json` and `weighted_ba2_validated_20261010/comparison.json`, `N=1`, `structural_cycles`. Reduction = 100×(original−layout)/original. Weighted values are read directly, never approximated. Each structural total is one full iteration plus one relay initialization. BA2 and weighted banking lower these structural totals; normalization avoids code-size domination.

3. **graph3_relay_vs_weighted**: sources `relay_aware_ba2_bounded_20261010/comparison.json` (BA2_relay) and `weighted_ba2_validated_20261010/comparison.json` (weighted), using existing BA2 as baseline. Signed change = 100×(layout−BA2)/BA2: negative means fewer cycles, positive means more. Relay-only reduces relay retries but worsens convergence enough to increase the total; weighted banking improves the total.

Graphs 2/3 use compatible seed-independent structural profiles from the verified four-shot, 2/2-budget R2/S1 pilot layouts. These are not sample-dependent mean completion costs. Source phase sums were checked. `weighted_ba2_heldout_checked_20261010/comparison.json` independently confirms the frozen numbers are unchanged; its 8/8 completion estimates are not mixed into these plots. All four pilot validation reports were inspected and PASS. Canonical latency and pilot structural service metrics are shown separately and are not compared numerically.

Validation: raw canonical means/p99 match summaries; 128 shots in both archives; N1–N8 archive row equality; original/BA2/relay/weighted consistency across reports; structural totals equal phase sums; existing source files hash-identical after generation. See `validation.json` for checks/source hashes and `plotted_values.json` for exact underlying values. `generate_graphs.py` is the reproducible plotting-only implementation.

Run from project directory:
```sh
MPLCONFIGDIR=/private/tmp/relay-prof-matplotlib ../.venv/bin/python -B results/prof_briefing_20261010/generate_graphs.py
```
"""
(OUT/"README.md").write_text(readme)
print("PASS: three PNG/PDF pairs;",len(before),"source files unchanged")

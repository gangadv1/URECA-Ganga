from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parent
rows=json.loads((P/"comparison.json").read_text());n=rows[0]["shots"]
plt.rcParams.update({"font.size":12,"axes.spines.top":False,"axes.spines.right":False,"axes.titleweight":"bold"})
labels=["BP","BP–OSD0","Relay N1","Relay N2","Relay N4","Relay N8"]
fig,ax=plt.subplots(figsize=(12,7));x=np.arange(6)
nonconv=[r["nonconvergence"]*100/n for r in rows];logical=[r["syndrome_valid_logical_error"]*100/n for r in rows]
ax.bar(x,nonconv,color="#f59e0b",label="Nonconvergence / syndrome invalid");ax.bar(x,logical,bottom=nonconv,color="#dc2626",label="Syndrome-valid logical error")
for i,r in enumerate(rows):
 lo,hi=r["failure_stats"]["wilson95"];v=r["total_failure"]*100/n
 ax.errorbar(i,v,yerr=[[v-lo*100],[hi*100-v]],fmt="none",capsize=5,color="#334155")
 ax.text(i,hi*100+1.2,f"{r['total_failure']}/{n}",ha="center")
ax.set_xticks(x,labels);ax.set_ylim(0,43);ax.set_ylabel("Total decoding failure (%)");ax.set_title("Same circuit syndromes: observed decoder outcomes",pad=18);ax.legend(loc="upper right",fontsize=10);ax.grid(axis="y",alpha=.2);ax.set_axisbelow(True)
fig.subplots_adjust(left=.1,right=.97,top=.83,bottom=.25);fig.text(.08,.045,f"Gross [[144,12,12]], p=.003, 12 noisy rounds; {n} common samples, runtime-limited prefix of 128.\nWhiskers: Wilson 95% intervals. BP ≤1940 iterations; OSD0 adds work; Relay N engines × R32/80–60.\nMatched data/priors, unequal aggregate compute and implementations. No significance or general LER claim.",fontsize=10,color="#475569")
for ext in ("png","pdf"):fig.savefig(P/f"graph1_paired_outcomes.{ext}",dpi=320,facecolor="white")
plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(13,7));w=.32
for ax,subset,fields,scale,names in [(axes[0],rows[:2],("mean_software_decode_seconds","p99_software_decode_seconds"),1000,labels[:2]),(axes[1],rows[2:],("mean_modeled_cycles","p99_modeled_cycles"),1e-6,labels[2:])]:
 for j,(field,label,color) in enumerate(zip(fields,("Mean","p99"),("#2563eb","#7c3aed"))):
  values=[r[field]*scale for r in subset];pos=np.arange(len(subset))+(j-.5)*w
  ax.bar(pos,values,width=w,color=color,label=label)
  for z,v in zip(pos,values):ax.annotate(f"{v:,.0f}",(z,v),xytext=(0,7),textcoords="offset points",ha="center",fontsize=10)
 ax.set_xticks(range(len(subset)),names);ax.set_ylim(0,ax.get_ylim()[1]*1.18);ax.legend(fontsize=10);ax.grid(axis="y",alpha=.2);ax.set_axisbelow(True)
axes[0].set_ylabel("Measured CPU decode wall time (milliseconds)");axes[1].set_ylabel("Modeled FPGA completion (million cycles)");axes[0].set_title("External software: measured once",fontsize=13);axes[1].set_title("Archived Relay: architectural cycle model",fontsize=13)
fig.suptitle("Timing domains remain separate — no cross-domain speedup",fontsize=17,fontweight="bold");fig.subplots_adjust(left=.085,right=.97,top=.80,bottom=.25,wspace=.3);fig.text(.065,.045,f"Same {n} canonical samples. CPU decode timings exclude initialization, IPC and scoring.\nOne unrandomized run per method: lower BP–OSD0 wall time does not establish a speed advantage.\nRelay software timing unavailable; no measured FPGA/Fmax timing or cross-domain clock conversion.",fontsize=10,color="#475569")
for ext in ("png","pdf"):fig.savefig(P/f"graph2_separate_timing_domains.{ext}",dpi=320,facecolor="white")
plt.close(fig)

"""Plot saved pilot data only; no sampling or decoding."""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
table=json.loads((HERE/"comparison.json").read_text())
codes=list(dict.fromkeys(row["code"] for row in table))
fig,axes=plt.subplots(1,2,figsize=(11,4),layout="constrained")
for offset,(n,p) in enumerate([(1,2),(1,4),(2,2),(2,4)]):
    rows=[next(r for r in table if (r["code"],r["N"],r["P"])==(code,n,p)) for code in codes]
    x=[i+(offset-1.5)*.18 for i in range(len(codes))]
    axes[0].bar(x,[r["mean_modeled_cycles"]/1e6 for r in rows],width=.18,label=f"N{n}/P{p}")
    axes[1].bar(x,[r["mean_critical_bank_retry_subsets"]/1e3 for r in rows],width=.18,label=f"N{n}/P{p}")
for ax in axes:
    ax.set_xticks(range(len(codes)),codes,rotation=20)
    ax.set_xlabel("BB code n_k_d")
axes[0].set_ylabel("Mean modeled completion\n(million cycles)")
axes[1].set_ylabel("Critical-trajectory retry subsets\n(mean, thousands)")
axes[0].legend(fontsize=9)
fig.suptitle("Paired four-shot pilot: structural extrapolation; maximum four iterations/engine",fontsize=12)
fig.savefig(HERE/"modeled_cycles_and_retries.png",dpi=160)
plt.close(fig)

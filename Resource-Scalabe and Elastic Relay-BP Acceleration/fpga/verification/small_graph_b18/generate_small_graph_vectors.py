"""Generate complete-engine vectors using the locked integer Relay-BP rules."""
from pathlib import Path
import json
import numpy as np

OUT = Path(__file__).resolve().parent
H = np.array([[1,1,1,0], [0,1,1,1], [1,0,1,1]], dtype=np.uint8)
CHECK_PTR = [0,3,6,9]
EDGE_VAR = [0,1,2,1,2,3,0,2,3]
VAR_PTR = [0,2,4,7,9]
VAR_EDGE = [0,6,1,3,2,4,7,5,8]
GAMMA = [[2,2,2,2], [-4,2,4,0]]
SHOTS = [
    {"prior":[7,7,7,7], "syndrome":[0,0,0], "limits":[2,3]},
    {"prior":[-7,-7,-7,-7], "syndrome":[0,1,1], "limits":[2,3]},
    {"prior":[9,-5,6,8], "syndrome":[1,0,1], "limits":[2,3]},
]
LO, HI = -(1<<17), (1<<17)-1
GLO, GHI = -(1<<21), (1<<21)-1
def sat(x,lo=LO,hi=HI): return max(lo,min(hi,int(x)))
def r16(x): return (-1 if x<0 else 1)*((abs(int(x))+8)//16)
def run(s):
    prior=np.array(s["prior"],dtype=np.int64); hand=prior.copy(); trace=[]
    final_dec=None
    for leg,limit in enumerate(s["limits"]):
        nu=prior[np.array(EDGE_VAR)].copy(); prev=hand.copy()
        for it in range(1,limit+1):
            bias=np.array([sat(r16(16*prior[j]+GAMMA[leg][j]*(prev[j]-prior[j]))) for j in range(4)])
            mu=np.zeros(9,dtype=np.int64)
            for c in range(3):
                a,b=CHECK_PTR[c:c+2]; vals=nu[a:b]; mags=np.abs(vals)
                first=int(np.argmin(mags)); second=int(np.min(np.delete(mags,first)))
                parity=int(s["syndrome"][c]) ^ (int(np.sum(vals<0))&1)
                for q in range(len(vals)):
                    mag=second if q==first else int(mags[first])
                    mu[a+q]=sat(-mag if parity ^ int(vals[q]<0) else mag)
            incoming=np.zeros(4,dtype=np.int64)
            for e,v in enumerate(EDGE_VAR): incoming[v]+=mu[e]
            incoming=np.clip(incoming,GLO,GHI)
            marg=np.array([sat(bias[j]+incoming[j]) for j in range(4)])
            dec=(marg<=0).astype(np.uint8)
            newnu=np.array([sat(marg[v]-mu[e]) for e,v in enumerate(EDGE_VAR)])
            residual=(H@dec)%2 ^ np.array(s["syndrome"])
            trace.append({"leg":leg+1,"iteration":it,"mu":mu.tolist(),"marginal":marg.tolist(),
                          "nu":newnu.tolist(),"decision":dec.tolist(),"converged":int(not residual.any())})
            nu=newnu; prev=marg; hand=marg.copy(); final_dec=dec
            if not residual.any():
                return trace, final_dec, int(np.dot(dec,prior)), leg+1
    return trace,final_dec,int(np.dot(final_dec,prior)),len(s["limits"])
def main():
    records=[]
    with (OUT/"iteration_vectors.txt").open("w") as f:
        for shot,s in enumerate(SHOTS):
            trace,dec,weight,legs=run(s)
            records.append({**s,"trace":trace,"final_correction":dec.tolist(),"weight":weight,
                            "total_iterations":len(trace),"legs":legs,"converged":trace[-1]["converged"]})
            for t in trace:
                f.write(" ".join(map(str,[shot,t["leg"],t["iteration"],*t["mu"],*t["marginal"],
                                           *t["nu"],*t["decision"],t["converged"]]))+"\n")
    with (OUT/"final_vectors.txt").open("w") as f:
        for shot,r in enumerate(records):
            f.write(" ".join(map(str,[shot,r["converged"],r["total_iterations"],r["legs"],
                                      r["weight"],*r["final_correction"]]))+"\n")
    (OUT/"small_graph_manifest.json").write_text(json.dumps({"H":H.tolist(),"check_row_ptr":CHECK_PTR,
      "check_edge_fault_ids":EDGE_VAR,"variable_row_ptr":VAR_PTR,"variable_to_edge":VAR_EDGE,
      "gamma_q_by_leg":GAMMA,"shots":records},indent=2)+"\n")
if __name__=="__main__": main()

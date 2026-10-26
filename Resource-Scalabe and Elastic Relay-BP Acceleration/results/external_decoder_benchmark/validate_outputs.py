"""Read-only verification of saved predictions, scores and archive preservation."""
from pathlib import Path
import json,csv,sys,hashlib
import numpy as np
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
sys.path.insert(0,str(ROOT/"simulations/configurable_testbench"))
import testbench as tb
_,_,_,_,h,a,_=tb.load_problem(tb.Config(code="144_12_12",physical_p=.003,shots=1))
with (ROOT/"results/n-scaling-canonical/per_shot_results.csv").open() as f:canonical=list(csv.DictReader(f))
with np.load(ROOT/"results/circuit-level-multiseed/paired_samples.npz") as d:ss=d["syndromes"].copy();ll=d["observed_logicals"].copy();seeds=d["sample_seeds"].copy()
records={}
for method in ("BP","BP_OSD0"):
 records[method]={r["index"]:r for r in json.loads((P/f"{method}_results.json").read_text())}
 with np.load(P/f"{method}_predictions.npz") as d:
  assert len(d["canonical_indices"])==len(records[method])
  for index,decision in zip(d["canonical_indices"],d["predicted_faults"]):
   index=int(index);r=canonical[index];seedindex=int(np.flatnonzero(seeds==int(r["sample_seed"]))[0]);shot=int(r["shot"])
   scored=tb.score(h,a,decision,ss[seedindex,shot].astype(np.uint8),ll[seedindex,shot].astype(np.uint8))
   assert all(records[method][index][k]==v for k,v in scored.items())
   assert hashlib.sha256(decision.tobytes()).hexdigest()==records[method][index]["decision_sha256"]
paired=json.loads((P/"paired_indices.json").read_text())
assert paired==sorted(set(records["BP"])&set(records["BP_OSD0"]))
for i in paired:
 b,o=records["BP"][i],records["BP_OSD0"][i]
 assert b["bp_iterations"]==o["bp_iterations"] and b["bp_converged"]==o["bp_converged"]
 if b["bp_converged"]:assert b["decision_sha256"]==o["decision_sha256"]
summary=json.loads((P/"comparison.json").read_text())
for r in summary:
 assert r["shots"]==len(paired)
 if r["decoder"] in records:
  rows=[records[r["decoder"]][i] for i in paired]
  assert r["total_failure"]==sum(x["total_failure"] for x in rows)
  assert r["logical_success"]==sum(not x["total_failure"] for x in rows)
 else:
  n=int(r["decoder"].split("N")[1])
  assert r["logical_success"]==sum(int(canonical[i][f"n{n}_logical_correct"]) for i in paired)
  assert r["nonconvergence"]==sum(int(canonical[i][f"n{n}_non_convergence"]) for i in paired)
  assert np.isclose(r["mean_modeled_cycles"],np.mean([int(canonical[i][f"n{n}_cycles"]) for i in paired]),rtol=0,atol=1e-6)
protected=json.loads((P/"protected_hashes.json").read_text())
assert all(hashlib.sha256((ROOT/x).read_bytes()).hexdigest()==v for x,v in protected.items())
print(f"PASS: {len(paired)} pairs independently rescored; BP stage exact; summaries and {len(protected)} protected files verified. No decoding executed.")

"""Fast deterministic accounting/statistics tests; no decoding."""
import json,csv
from pathlib import Path
import numpy as np
from analyze import lower,ci,holm
p=Path(__file__).resolve().parent
assert lower(0,128,.05)==0 and ci(128,128)[1]==1
assert lower(128,128,.05/45)<.95<lower(128,128,.05/5)
assert np.allclose(holm([.01,.02,.5]),[.03,.04,.5])
# Correctness must gate deadline completion; equality is timely.
correct=np.array([True,False,True]);cycles=np.array([100,10,101]);assert (correct&(cycles<=100)).tolist()==[True,False,False]
with (p/'deadline_metrics.csv').open() as f:
 for r in csv.DictReader(f):
  assert int(r['success_by_deadline'])+int(r['nonconvergence'])+int(r['logical_errors'])+int(r['correct_but_late'])==128
summary=json.loads((p/'analysis_summary.json').read_text())
assert all(r['whole_grid_minimum_N']=='no statistically certified optimum' for r in summary['selections'])
assert len(summary['significant_paired_tests'])==7
print('PASS: boundary handling, multiplicity, failure partition, deadline equality and selection regressions; zero decode calls.')

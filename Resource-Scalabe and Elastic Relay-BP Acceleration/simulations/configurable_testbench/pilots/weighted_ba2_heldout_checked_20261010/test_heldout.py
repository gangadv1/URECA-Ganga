import unittest,json
import numpy as np
from dataclasses import replace
import validate_heldout as m
class HeldoutTests(unittest.TestCase):
 def test_frozen_maps_and_distinct_seeds(self):
  for code in m.tb.CODE_NAMES:
   train=m.tb.Config(**json.loads((m.PAIRED/"configs"/f"bb{code}_n2_p4.json").read_text()))
   held=replace(train,sample_seed=2026101101,trajectory_base_seed=11400714819323198485,first_limit=8,later_limit=8)
   self.assertNotEqual(train.sample_seed,held.sample_seed)
   old={x for s in range(4) for x in m.tb.trajectory_seeds(train,s)}
   new={x for s in range(4) for x in m.tb.trajectory_seeds(held,s)}
   self.assertFalse(old & new)
   with np.load(m.FROZEN/code/"storage_maps.npz") as f, np.load(m.BASE/code/"storage_maps.npz") as b:
    np.testing.assert_array_equal(f["edge_old_to_new"],b["edge_old_to_new"])
    for prefix in ("fault","edge"):
     fo,fn=f[prefix+"_old_to_new"],f[prefix+"_new_to_old"]
     np.testing.assert_array_equal(fo[fn],np.arange(len(fo)))
    np.testing.assert_array_equal(np.bincount(f["fault_residues"],minlength=4),np.bincount(b["fault_residues"],minlength=4))
if __name__=="__main__": unittest.main()

import unittest
import numpy as np
import compare_weighted as m
class WeightedTests(unittest.TestCase):
 def test_capacities_determinism_and_fallback(self):
  ba=m.tb.module("weighted_unit",m.tb.ROOT/"results/bank-aware-folding-layout/run_bank_aware_layout.py")
  ba.P=ba.fm.P=4
  original=np.arange(9,dtype=np.int8)%4
  conv=[np.array([0,4,8,1]),np.array([2,6,3,7])]
  relay=[np.array([0,0,5]),np.array([2,3,4,5])]
  a,s=m.weighted_assignment(ba,conv,relay,original,4,2)
  b,t=m.weighted_assignment(ba,conv,relay,original,4,2)
  np.testing.assert_array_equal(a,b)
  np.testing.assert_array_equal(np.bincount(a,minlength=4),ba.residue_capacities(9))
  base=next(r for r in s["records"] if r["candidate"]=="BA2")
  best=next(r for r in s["records"] if r["candidate"]==s["selected"])
  self.assertLessEqual(best["expected_conflict_cycles"],base["expected_conflict_cycles"])
  self.assertEqual(best["expected_conflict_cycles"],3*(4*m.relay_cost(conv,a)+2*m.relay_cost(relay,a)))
 def test_BA2_wins_ties(self):
  ba=m.tb.module("weighted_tie",m.tb.ROOT/"results/bank-aware-folding-layout/run_bank_aware_layout.py")
  ba.P=ba.fm.P=4
  original=np.arange(4,dtype=np.int8)
  a,s=m.weighted_assignment(ba,[np.array([0])],[np.array([0,0])],original,1,1)
  self.assertEqual(s["selected"],"BA2")
  np.testing.assert_array_equal(a,original)
if __name__=="__main__": unittest.main()

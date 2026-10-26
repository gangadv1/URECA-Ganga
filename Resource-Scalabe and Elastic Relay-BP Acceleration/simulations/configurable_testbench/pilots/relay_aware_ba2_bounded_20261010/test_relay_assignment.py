import unittest
import numpy as np
import compare_relay as model

class RelayAssignmentTests(unittest.TestCase):
    def test_duplicates_and_partial_groups(self):
        groups=[np.array([0,0,1,2]),np.array([3])]
        self.assertEqual(model.relay_cost(groups,np.array([0,1,2,3])),1)
    def test_capacity_identity_determinism_and_objective(self):
        ba=model.tb.module("relay_test_ba",model.tb.ROOT/"results/bank-aware-folding-layout/run_bank_aware_layout.py")
        ba.P=ba.fm.P=4
        original=np.arange(9,dtype=np.int8)%4
        groups=[np.array([0,4,8,1]),np.array([2,6,3,7]),np.array([0,0,5])]
        a,stats=model.relay_assignment(ba,groups,original)
        b,_=model.relay_assignment(ba,groups,original)
        np.testing.assert_array_equal(a,b)
        np.testing.assert_array_equal(np.bincount(a,minlength=4),ba.residue_capacities(9))
        fo,fn=ba.permutation_from_residues(a)
        np.testing.assert_array_equal(fo[fn],np.arange(9))
        self.assertLessEqual(stats["final_retries"],stats["initial_retries"])
        self.assertEqual(stats["final_retries"],model.relay_cost(groups,a))
        self.assertLess(stats["final_retries"],stats["initial_retries"])
if __name__=="__main__": unittest.main()

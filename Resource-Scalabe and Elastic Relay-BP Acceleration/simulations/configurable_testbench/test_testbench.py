"""Bounded smoke coverage; no Monte Carlo campaign or archived writes."""
import csv
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy import sparse

from testbench import (Config, ROOT, CODE_NAMES, decode_engine, folding,
                       load_problem, rate, run, samples, score, select, trajectory_seeds)


class TestbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent=Path(__file__).parent/"smoke_outputs"
        parent.mkdir(exist_ok=True)
        cls.output=Path(tempfile.mkdtemp(prefix="run-",dir=parent))
        print("Isolated smoke outputs:",cls.output,flush=True)

    def test_four_codes(self):
        for code in CODE_NAMES:
            with self.subTest(code=code):
                cfg=Config(code=code,N=2,P=4,shots=1,first_limit=1,later_limit=1,R=2,S=1,
                           sample_seed=12345,timing_model="folding_original")
                result=run(cfg,self.output/code)
                manifest=json.loads((self.output/code/"manifest.json").read_text())
                self.assertEqual(manifest["dimensions"]["observables"],int(code.split("_")[1]))
                self.assertEqual(result["total_failure"]["count"],
                                 result["nonconvergence"]["count"]+result["syndrome_valid_logical_error"]["count"])
                self.assertEqual(result["total_failure"]["shots"],1)
                self.assertEqual(len(result["per_engine_iterations"]),2)
                self.assertIsNone(result["elapsed_cycle_PE_utilization"])
                self.assertIsNone(result["cancellation_aware_executed_work"])
                self.assertGreater(result["folding_metrics"]["all_phases_once"]["issued_groups"],0)
                with self.assertRaises(FileExistsError):
                    run(cfg,self.output/code)

    def test_gross_canonical_n1_p4(self):
        # Cheapest real archived E0 case: 17 iterations in the first leg.
        cfg=Config(sample_mode="canonical_paired",sample_seed=20260810,shot_offset=15,
                   shots=1,N=1,P=4,timing_model="canonical_p4")
        run(cfg,self.output/"gross_canonical_regression")
        with (ROOT/"results/n-scaling-canonical/per_shot_results.csv").open(newline="") as f:
            expected=next(r for r in csv.DictReader(f) if r["sample_seed"]=="20260810" and r["shot"]=="15")
        with (self.output/"gross_canonical_regression/per_engine.csv").open(newline="") as f:
            actual=next(csv.DictReader(f))
        for key in ("iterations","legs","natural_cycles","result_cycles","rng_words"):
            self.assertEqual(int(actual[key]),int(expected["e0_"+key]))
        self.assertEqual(int(actual["seed"]),int(expected["s0"]))
        self.assertEqual(int(actual["total_failure"]),1-int(expected["e0_logical_correct"]))
        with (self.output/"gross_canonical_regression/per_shot.csv").open(newline="") as f:
            ensemble=next(csv.DictReader(f))
        self.assertEqual(int(ensemble["modeled_completion_cycles"]),int(expected["n1_cycles"]))

    def test_determinism_and_label_separation(self):
        cfg=Config(code="18_4_3",R=2,first_limit=1,later_limit=1,sample_seed=777)
        directory,pkg,_,circuit,h,a,priors=load_problem(cfg)
        d,l=samples(cfg,directory,pkg,circuit)
        d2,l2=samples(cfg,directory,pkg,circuit)
        np.testing.assert_array_equal(d,d2);np.testing.assert_array_equal(l,l2)
        seed=trajectory_seeds(cfg,0)[0]
        costs=dict(check=10,variable=20,convergence=5,relay_init=7)
        e=decode_engine(h,priors,d[0],seed,cfg,costs)
        e2=decode_engine(h,priors,d[0],seed,cfg,costs)
        np.testing.assert_array_equal(e.pop("decision"),e2.pop("decision"))
        self.assertEqual(e,e2)
        # Logical labels are scoring-only. A valid fixed decision can be scored
        # differently without changing a decoder input or choosing a winner.
        small=sparse.eye(2,dtype=np.uint8,format="csr");decision=np.array([1,0],np.uint8)
        self.assertEqual(score(small,small,decision,decision,decision)["total_failure"],0)
        self.assertEqual(score(small,small,decision,decision,1-decision)["syndrome_valid_logical_error"],1)

    def test_selection_ties_rescue_all_fail(self):
        e=lambda t,s:dict(result_cycles=t,syndrome_converged=s)
        self.assertEqual(select([e(10,True),e(10,True)]),(10,0))
        self.assertEqual(select([e(2,False),e(8,True)]),(8,1))
        self.assertEqual(select([e(2,False),e(8,False)]),(8,-1))
        self.assertEqual(select([e(10,True),e(5,True)]),(5,1))

    def test_validation(self):
        with self.assertRaises(ValueError):
            load_problem(Config(code="18_4_3",physical_p=.004))
        with self.assertRaises(ValueError):
            load_problem(Config(code="18_4_3",source_circuit=str(ROOT/"graphs/sources/relay_official/bicycle_bivariate/bb_72_12_6_memory_Z_r6_p0.003.stim")))
        with self.assertRaises(ValueError):
            Config(S=2,R=1).validate()
        with self.assertRaises(ValueError):
            Config(P=2,timing_model="canonical_p4").validate()
        with self.assertRaises(ValueError):
            Config(engine_seeds=[1,2],N=1).validate()
        for failures in (0,1):
            bounds=rate(failures,1)["wilson95"]
            self.assertLessEqual(bounds[0],failures)
            self.assertGreaterEqual(bounds[1],failures)

    def test_folding_variable_p(self):
        h=sparse.csr_matrix(np.array([[1,1,0],[0,1,1]],np.uint8))
        for p in (2,4,8):
            _,total=folding(h,p)
            self.assertLessEqual(total["mean_lane_utilization"],1)
            self.assertGreater(total["estimated_cycles"],0)

    def test_original_gross_folding_regression(self):
        _,_,_,_,h,_,_=load_problem(Config())
        actual,_=folding(h,4)
        with (ROOT/"results/folding-factor-sweep/phase_retry_summary.csv").open(newline="") as f:
            expected=[r for r in csv.DictReader(f) if r["P"]=="4" and r["layout"]=="original"]
        self.assertEqual(len(expected),4)
        for row in expected:
            phase=actual[row["phase"]]
            self.assertEqual(phase["estimated_cycles"],int(row["estimated_cycles"]))
            self.assertEqual(phase["retry_subsets"],int(row["retry_subsets"]))
            self.assertAlmostEqual(phase["mean_lane_utilization"],float(row["lane_utilization"]))


if __name__=="__main__":
    unittest.main()

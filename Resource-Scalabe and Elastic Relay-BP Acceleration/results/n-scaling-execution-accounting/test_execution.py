import csv
from pathlib import Path
import unittest

from analyze_execution import account, ROOT

PHASES = dict(check=1, variable=1, convergence=1, relay_init=1)


def row(*engines):
    return {f"e{i}_{k}": v for i, e in enumerate(engines) for k, v in
            dict(natural_cycles=e[0], result_cycles=e[1], syndrome_converged=e[2],
                 iterations=1, legs=1).items()}


class AccountingTests(unittest.TestCase):
    def test_n1(self):
        r = account(row((10, 9, 1)), 1, 4, PHASES)
        self.assertEqual(r["ensemble_completion_cycles"], 9)
        self.assertEqual(r["provisioned_lane_cycles"], 36)
        self.assertEqual(r["executed_phase_controller_cycles_lower_bound"], 4)
        self.assertEqual(r["executed_engine_elapsed_cycles_lower_bound"], 10)
        self.assertIsNone(r["cancellation_aware_executed_work"])

    def test_n2_failed_loser(self):
        r = account(row((10, 9, 1), (20, 20, 0)), 2, 4, PHASES)
        self.assertEqual(r["winner_engine"], 0)
        self.assertEqual(r["uncancelled_natural_work"], 30)
        self.assertEqual(r["executed_engine_elapsed_cycles_lower_bound"], 19)
        self.assertEqual(r["executed_phase_controller_cycles_lower_bound"], 4)
        self.assertEqual(r["executed_phase_controller_cycles_upper_bound"], 8)
        self.assertIsNone(r["cancellation_ack_cycles"])

    def test_ties(self):
        r = account(row((10, 9, 1), (10, 9, 1)), 2, 4, PHASES)
        self.assertEqual((r["winner_engine"], r["same_cycle_successes"]), (0, 2))

    def test_completed_failure_and_rescue(self):
        r = account(row((5, 5, 0), (10, 9, 1)), 2, 4, PHASES)
        self.assertEqual(r["winner_engine"], 1)
        self.assertEqual(r["executed_engine_elapsed_cycles_lower_bound"], 15)

    def test_all_fail_waits_last(self):
        r = account(row((5, 5, 0), (20, 20, 0)), 2, 4, PHASES)
        self.assertEqual((r["winner_engine"], r["ensemble_completion_cycles"]), (-1, 20))
        self.assertEqual(r["executed_phase_controller_cycles_lower_bound"], 8)
        self.assertEqual(r["executed_engine_elapsed_cycles_lower_bound"], 25)

    def test_invalid_counts_rejected(self):
        with self.assertRaises(ValueError):
            account(row((3, 3, 0)), 1, 4, PHASES)

    def test_n8_archive_and_bound_order(self):
        import json
        source = ROOT / "results/n-scaling-canonical"
        phases = json.loads((source / "manifest.json").read_text())["cycle_model"]
        with (source / "per_shot_results.csv").open(newline="") as f:
            rows = list(csv.DictReader(f))
        with (ROOT / "results/n-scaling-canonical-n8-complete/per_shot_results.csv").open(newline="") as f:
            n8 = {(r["sample_seed"], r["shot"]): r for r in csv.DictReader(f)}
        for r in rows:
            a = account(r, 8, 4, phases)
            self.assertEqual(a, account(n8[r["sample_seed"], r["shot"]], 8, 4, phases))
            for n in (1, 2, 4, 8, 16):
                a = account(r, n, 4, phases)
                for prefix in ("executed_engine_elapsed_cycles", "executed_phase_controller_cycles",
                               "ensemble_quiescence_cycles", "post_result_quiescence_overhead_cycles"):
                    self.assertLessEqual(a[prefix + "_lower_bound"], a[prefix + "_upper_bound"])

    def test_archived_n1_n2_regression(self):
        import json
        source = ROOT / "results/n-scaling-canonical"
        phases = json.loads((source / "manifest.json").read_text())["cycle_model"]
        with (source / "per_shot_results.csv").open(newline="") as f:
            rows = list(csv.DictReader(f))
        historical = ROOT / "results/n1-vs-n2-hardware-latency/per_shot_results.csv"
        with historical.open(newline="") as f:
            old = {(r["sample_seed"], r["shot"]): r for r in csv.DictReader(f)}
        for r in rows:
            for n in (1, 2):
                a = account(r, n, 4, phases)
                self.assertEqual(a["ensemble_completion_cycles"], int(r[f"n{n}_cycles"]))
                self.assertEqual(a["ensemble_completion_cycles"],
                                 int(old[r["sample_seed"], r["shot"]][f"n{n}_cycles"]))
                self.assertEqual(a["uncancelled_natural_work"], int(r[f"n{n}_active_work"]))


if __name__ == "__main__":
    unittest.main()

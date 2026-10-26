# URECA professor briefing — 10 October 2026

Three 3840 × 2240 PNGs (320 dpi) and matching vector PDFs. No decoding experiments were run. All cycles are model/structural estimates, not measured FPGA or RTL timing. No significance or LER claims.

1. **graph1_canonical_n_latency**: Gross [[144,12,12]], P4, completed 128-shot N1/2/4/8/16 campaign. Source: `../n-scaling-canonical/per_shot_results.csv`, columns `nN_cycles`; cross-checked `aggregate_summary.json` and `manifest.json`. Mean = arithmetic mean of 128 rows; p99 = NumPy linear percentile (rank 0.99×127). N1–N8 latency rows match `../n-scaling-canonical-n8-complete/per_shot_results.csv`. The archived first-success/last-engine-on-all-fail latency is unchanged. Mean falls 2.25% and p99 8.85% from N8 to N16: diminishing incremental latency returns despite doubling trajectories. Empirical p99 is unstable with only 128 shots. Log y-axis; plotted units are cycles / 1,000,000. No active_work quantity is used.

2. **graph2_banking_vs_original**: four BB codes; original, graph-specific BA2 and selected weighted BA2. Sources: `simulations/configurable_testbench/pilots/ba2_graph_specific_20261010/comparison.json` and `weighted_ba2_validated_20261010/comparison.json`, `N=1`, `structural_cycles`. Reduction = 100×(original−layout)/original. Weighted values are read directly, never approximated. Each structural total is one full iteration plus one relay initialization. BA2 and weighted banking lower these structural totals; normalization avoids code-size domination.

3. **graph3_relay_vs_weighted**: sources `relay_aware_ba2_bounded_20261010/comparison.json` (BA2_relay) and `weighted_ba2_validated_20261010/comparison.json` (weighted), using existing BA2 as baseline. Signed change = 100×(layout−BA2)/BA2: negative means fewer cycles, positive means more. Relay-only reduces relay retries but worsens convergence enough to increase the total; weighted banking improves the total.

Graphs 2/3 use compatible seed-independent structural profiles from the verified four-shot, 2/2-budget R2/S1 pilot layouts. These are not sample-dependent mean completion costs. Source phase sums were checked. `weighted_ba2_heldout_checked_20261010/comparison.json` independently confirms the frozen numbers are unchanged; its 8/8 completion estimates are not mixed into these plots. All four pilot validation reports were inspected and PASS. Canonical latency and pilot structural service metrics are shown separately and are not compared numerically.

Validation: raw canonical means/p99 match summaries; 128 shots in both archives; N1–N8 archive row equality; original/BA2/relay/weighted consistency across reports; structural totals equal phase sums; existing source files hash-identical after generation. See `validation.json` for checks/source hashes and `plotted_values.json` for exact underlying values. `generate_graphs.py` is the reproducible plotting-only implementation.

Run from project directory:
```sh
MPLCONFIGDIR=/private/tmp/relay-prof-matplotlib ../.venv/bin/python -B results/prof_briefing_20261010/generate_graphs.py
```

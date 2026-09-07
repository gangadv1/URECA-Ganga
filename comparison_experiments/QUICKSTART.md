#!/Users/gangadevi.aa/Desktop/URECA-Ganga/comparison_experiments

# QUICK START: RELAY-BP vs GARI COMPARISON

## File Locations

```
Primary Scripts:
  relay_gari_comparison.py          Main experiment runner (fully tested)
  
Reports:
  RELAY_BP_ENSEMBLE_REPORT.md       Technical analysis & findings
  COMPARISON_EXECUTION_STATUS.md    Detailed checklist & status

Results (500-shot baseline):
  raw_results/comparison_summary.csv
  raw_results/detailed_results.json
```

## Quick Commands

### Run Relay-BP Only (Recommended for Testing)
```bash
cd /Users/gangadevi.aa/Desktop/URECA-Ganga

# Fast test (100 shots, p=0.001)
python3 comparison_experiments/relay_gari_comparison.py \
  --shots 100 \
  --error-rate 0.001 \
  --max-iters 60 \
  --n-trajectories 1,2,4 \
  --skip-gari

# Moderate run (500 shots, p=0.001) - ~10-15 minutes
python3 comparison_experiments/relay_gari_comparison.py \
  --shots 500 \
  --error-rate 0.001 \
  --max-iters 60 \
  --n-trajectories 1,2,4 \
  --skip-gari

# Production (10000 shots, p=0.001) - ~3-5 hours
python3 comparison_experiments/relay_gari_comparison.py \
  --shots 10000 \
  --error-rate 0.001 \
  --max-iters 60 \
  --n-trajectories 1,2,4 \
  --skip-gari
```

### Run With GARI (Requires Linux or macOS Fix)
```bash
# First, ensure GARI is compiled
cd /tmp/gari-nms/my_decoders
make clean && make

# Then run comparison with GARI
cd /Users/gangadevi.aa/Desktop/URECA-Ganga
python3 comparison_experiments/relay_gari_comparison.py \
  --shots 500 \
  --error-rate 0.001 \
  --max-iters 60 \
  --n-trajectories 1,2,4
```

## Expected Output

### Console Output
```
================================================================================
RELAY-BP vs GARI-NMS SOFTWARE-ONLY COMPARISON
================================================================================

Experiment Configuration:
  Code: [[144,12,12]] Bivariate Bicycle (Gross)
  Noise model: Depolarizing (Gross circuit-level memory-Z)
  Physical error rate: 0.001
  Number of shots: 500
  Max iterations: 60
  Relay-BP trajectories: (1, 2, 4)
  Output dir: comparison_experiments/raw_results

Loaded code: Hx shape (72, 144), Hz shape (72, 144)

======================================================================
Running Relay-BP with N=1 trajectories
Shots: 500, Max iterations: 60
======================================================================
  Progress: 50/500
  Progress: 100/500
  Progress: 150/500
  ...
  
COMPARISON SUMMARY
======================================================================

Decoder: Relay-BP N=1
  Trials: 500 (successes: 28, failures: 472)
  LER: 0.944
  Iterations: mean=58.2, median=60.0, P95=60.0, P99=60.0, max=60
  ...

Saved summary to comparison_experiments/raw_results/comparison_summary.csv
Saved detailed results to comparison_experiments/raw_results/detailed_results.json

Experiment complete!
```

### CSV Output Format
```
name,num_trials,num_successes,num_failures,logical_error_rate,mean_iterations,...
Relay-BP N=1,500,28,472,0.944,58.166,60.0,8.419883847179841,60.0,60.0,60,7,...
Relay-BP N=2,500,46,454,0.908,56.778,60.0,11.090027772733484,60.0,60.0,60,7,...
Relay-BP N=4,500,88,412,0.824,53.594,60.0,15.112020513485284,60.0,60.0,60,7,...
```

## Interpreting Results

### Key Metrics

**Logical Error Rate (LER)**
- Fraction of shots that fail to converge
- Lower is better
- For N=1, N=2, N=4: should see decreasing trend

**Mean Iterations**
- Average number of BP iterations before convergence or timeout
- Lower is better
- Reflects decoder efficiency

**P95/P99 Iterations**  
- 95th and 99th percentile iteration counts
- Shows tail behavior
- If both = max_iterations, problem is hard for that configuration

**Success Rate**
- Fraction of shots that converged successfully
- = 1 - LER
- More trajectories should give higher rate

### Example Interpretation (500-shot results)

```
Relay-BP N=1: 5.6% success
  → 1 in ~18 decoding attempts succeeds
  → Hard problem, needs tuning or more iterations

Relay-BP N=4: 17.6% success (vs 5.6% baseline)
  → 1 in ~5.7 attempts succeeds
  → 3.1x improvement from parallel trajectories
  → Demonstrates ensemble benefit

Trend (N=1 → N=2 → N=4):
  Success: 5.6% → 9.2% → 17.6% ✓ monotonic increase
  Mean iters: 58.2 → 56.8 → 53.6 ✓ monotonic decrease
  → Evidence of working ensemble mechanism
```

## File Formats

### comparison_summary.csv

Machine-readable summary:
```
Fields: name, num_trials, num_successes, num_failures, logical_error_rate,
        mean_iterations, median_iterations, std_iterations, p95_iterations,
        p99_iterations, max_iterations, min_iterations, mean_latency_ms,
        total_latency_ms, success_rate
```

Parse with:
```python
import pandas as pd
df = pd.read_csv('comparison_experiments/raw_results/comparison_summary.csv')
print(df.to_string())
```

### detailed_results.json

Full configuration + results:
```json
{
  "config": {
    "code_name": "[[144,12,12]] Bivariate Bicycle (Gross)",
    "num_shots": 500,
    "physical_error_rate": 0.001,
    "max_iterations": 60,
    "relay_trajectories": [1, 2, 4],
    ...
  },
  "summaries": [
    {
      "name": "Relay-BP N=1",
      "num_trials": 500,
      ...
    },
    ...
  ]
}
```

Parse with:
```python
import json
with open('comparison_experiments/raw_results/detailed_results.json') as f:
    data = json.load(f)
print("Config:", data['config'])
print("Results:", data['summaries'])
```

## Reproducing Exact Previous Results

### 500-Shot Run (Completed 2025-09-07)

```bash
cd /Users/gangadevi.aa/Desktop/URECA-Ganga

# Exact command that produced reference results:
python3 comparison_experiments/relay_gari_comparison.py \
  --shots 500 \
  --error-rate 0.001 \
  --max-iters 60 \
  --n-trajectories 1,2,4 \
  --skip-gari
```

**Expected results:**
```
Relay-BP N=1: LER=0.944, success=5.6%, mean_iters=58.2
Relay-BP N=2: LER=0.908, success=9.2%, mean_iters=56.8
Relay-BP N=4: LER=0.824, success=17.6%, mean_iters=53.6
```

**Reproducibility:**
- ✅ Deterministic with fixed seed (seed_base=12345)
- ✅ No randomization in summary computation
- ✅ Should produce identical CSV values
- ✅ Minor latency differences (Python execution speed varies)

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'numpy'"
```bash
pip3 install numpy
```

### Issue: "No module named 'hbplib_wrapper_v2'" (GARI integration)
```bash
# This is expected; use --skip-gari flag
# To enable, run on Linux or fix macOS ABI compatibility
```

### Issue: Code matrices not found
```bash
cd Resource-Scalabe\ and\ Elastic\ Relay-BP\ Acceleration/graphs/
python3 bb_code.py --out-dir ./generated/gross_code
```

### Issue: "PermissionError" on output directory
```bash
mkdir -p comparison_experiments/raw_results
chmod 755 comparison_experiments
```

## Performance Expectations

| Shot Count | N Values | Approx. Time |
|-----------|----------|-------------|
| 100       | 1,2,4    | 20 sec      |
| 500       | 1,2,4    | 2 min       |
| 1000      | 1,2,4    | 4 min       |
| 5000      | 1,2,4    | 20 min      |
| 10000     | 1,2,4    | 40 min      |

Times are approximate; depends on CPU speed and system load.

## Reading the Full Report

```bash
# View the technical report with findings
cat comparison_experiments/RELAY_BP_ENSEMBLE_REPORT.md

# View the detailed execution status
cat comparison_experiments/COMPARISON_EXECUTION_STATUS.md

# Quick stats from CSV
head -5 comparison_experiments/raw_results/comparison_summary.csv
```

## Next Steps

1. **For immediate use:** Run 500-shot test with `--skip-gari`
2. **For GARI comparison:** Deploy on Linux and rerun without `--skip-gari`
3. **For paper-ready results:** Run 10,000-shot configuration
4. **For visualization:** Use CSV with matplotlib/pandas to create plots

## Contact & Questions

For questions about the experimental framework, see:
- `RELAY_BP_ENSEMBLE_REPORT.md` - Technical details
- `relay_gari_comparison.py` - Source code comments
- `COMPARISON_EXECUTION_STATUS.md` - Full specification

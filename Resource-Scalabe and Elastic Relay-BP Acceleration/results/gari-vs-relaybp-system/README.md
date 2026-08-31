# GARI versus the complete resource-scalable Relay-BP system

This study compares GARI with the full proposed Relay-BP research stack rather than BA2 alone. The main Relay-BP system is fixed-point Relay-BP with two independent E0/E1 trajectories for first-success tail mitigation, P=4 folded processing per trajectory, and the validated BA2 bank-aware layout. Stagnation-priority scheduling remains optional and is excluded from headline comparisons.

`final_system_comparison.md` is the integrated report. Latency, tail, correction, and memory evidence are separated because they have different comparability levels. New N=2+BA2 numbers are deterministic software-model derivations from archived E0/E1 iteration/leg counts and the existing layout-specific phase costs; decoder trajectories were not rerun.

No RTL was modified and no synthesis was run. BRAM values for Relay-BP are capacity-only analytical estimates, not implementation results.

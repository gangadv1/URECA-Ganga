# Folding-factor sweep

This software study treats P as both reusable processing lanes and logical banks. Address modulo P selects a bank; groups contain at most P requests and stable first-per-bank winners issue until all retries drain. P is not a decoder count.

Frozen BA2 uses message weight 5, convergence and relay-init weights 3, balance lambda 0.25, locality lambda 0, and deterministic weighted-degree ordering at P=2,4,8. Only the residue count changes. P=4 assignments and metrics reproduce the validated BA2 result exactly. Archived E0 trajectories remain fixed and only their modeled phase costs change. The Gross code-capacity graph is included as an optional structural-only sweep. No RTL, synthesis, hardware area, or FPGA-speedup claim is involved.

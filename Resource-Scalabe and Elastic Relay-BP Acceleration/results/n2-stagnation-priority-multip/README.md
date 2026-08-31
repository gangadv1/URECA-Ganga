# Frozen P1 multi-p validation audit

The requested p=0.002 and p=0.004 paired scheduling validation cannot be run from the existing archive. Each rate has 64 syndromes, logical outcomes, E0 seeds, E0 outcomes, and E0 per-leg traces. Full E0 iteration traces are not saved but could be regenerated and checked against that metadata. The blocking absence is E1: there is no E1 seed or E1 trajectory metadata. Selecting an E1 seed now would create a new paired experiment, not regenerate an archived trajectory. No P0/P1 result is reported for those rates.

The p=0.003 row is reused from the validated shared-resource study. The threshold (120 at a completed leg boundary, leg >=3) and conservative 2:1 policy remain frozen. This is a software-model data-availability audit; it makes no FPGA-speedup claim.

# Relay-BP memory-optimization study

This software/analytical study audits the complete P=4 memory fabric and develops N=2 capacity-reduction variants without changing Relay-BP equations, fixed-point width, BA2 assignments, or E0/E1 independence.

The selected candidate is M4: shared dual-read immutable storage, BA2 compiled into memory images, sequential degree-table addressing, and one phase-aliased NU/MU message RAM per trajectory. Its 925 BRAM36 banked-capacity equivalent is analytical, not synthesized.

Start with `final_memory_report.md` and `selected_memory_architecture.md`. Machine-readable inventory, sharing, bandwidth, variant, and GARI comparison tables are provided alongside them. No RTL was modified and no synthesis was run.

# Bank-aware P=4 folding layout

Software-only static layout experiment. No RTL, graph connectivity, decoder equations, or trajectory state changed.

Six layouts were evaluated with the unchanged P=4 model. Selected `BA2` by minimum structural cycles, then retry subsets. It has 142,566 retries (-57.606% versus original) and 4,283,590 structural cycles (-9.984%). Archived E0 scaling gives mean 617,117,727, p95 1,917,397,629, and p99 6,270,598,460 modeled cycles.

All selected permutations and graph data round-trip exactly. The mathematical neighborhoods are unchanged, but the new fault IDs change their sorted sparse iteration order. A paired decoder-equivalence check is therefore required before combining this layout with another decoder study. These are modeled folding-efficiency results, not FPGA speedup or decoding claims.

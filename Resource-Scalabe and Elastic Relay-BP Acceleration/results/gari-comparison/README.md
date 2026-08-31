# GARI comparison

This folder compares the GARI FPGA architecture in arXiv:2605.01035v1 with the repository's validated BA2/P=4 software model. The comparison is mechanism-level: GARI changes the detector-error-model factorization and implements it in FPGA hardware; BA2 preserves the Relay-BP mathematical graph and changes reversible storage addresses to reduce modulo-four bank conflicts.

Start with `final_gari_comparison.md`. Source extraction is in `gari_primary_source_audit.md` and `gari_architecture_notes.md`; machine-readable values and mappings are in the CSV files. Hardware latency/resource rankings are deliberately excluded because BA2 has not been synthesized or timed.

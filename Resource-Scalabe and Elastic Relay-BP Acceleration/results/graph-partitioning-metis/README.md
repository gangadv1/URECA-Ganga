# Limited METIS graph-partitioning baseline

Software-only structural experiment on the canonical Tier-2 gross `[[144,12,12]]` memory-Z detector/fault graph. Relay-BP was not run and RTL was not modified.

## Interface and limitation

- PyMetis 2025.2.2; direct k-way via `recursive=False`; fixed `Options.seed`; edge-cut objective; `Options.ufactor=30` (3%).
- The wrapper does **not reliably expose four simultaneous balance channels**. This is a **LIMITED METIS BASELINE**.
- METIS balances one scalar vertex weight equal to node degree (combined endpoint-incidence work).
- A deterministic post-stage reaches exact check and fault counts using lowest local cut-penalty moves.
- Separate check/fault workloads are measured and filtered at 5%, not claimed as independently METIS-enforced.

## Selection

Seed `2` passed the 5% conceptual-work filter and was selected by minimum edge-cut ratio, then summed mean neighborhood dispersion, maximum imbalance, and seed.

| Assignment | Edge-cut ratio | Maximum imbalance | Boundary checks | Boundary faults |
|---|---:|---:|---:|---:|
| random_balanced | 0.749532 | 0.8269% | 100.0000% | 99.5543% |
| greedy_balanced | 0.543698 | 0.0010% | 100.0000% | 97.2724% |
| metis_limited_selected | 0.104472 | 4.1030% | 78.4722% | 34.5850% |

The unpartitioned graph is reported separately without a fake k=4 cut score. Structural locality is not evidence of decoding improvement.

Reproduce with `../.venv/bin/python results/graph-partitioning-metis/run_metis_partitioning.py`. The small k=2 example has cut 4.

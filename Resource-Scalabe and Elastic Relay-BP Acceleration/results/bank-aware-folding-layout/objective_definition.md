# Bank-aware objective

The static objective penalizes pairs of mathematical items that occur in one current P=4 request group and receive the same address residue. Fault-pair weights are `3*convergence occurrences + 3*relay-init occurrences`; edge-pair weights are `5*variable occurrences`, reflecting the controller-cycle cost of retries across MU and NU. Exact address-residue capacities are mandatory. BA2 adds access-workload balance; BA3 adds a weak METIS-partition preference. No syndrome, convergence, logical, or tail labels enter construction.

This pairwise objective is a transparent surrogate for the exact retry-subset evaluator. Final selection always uses the unchanged exact folding model.

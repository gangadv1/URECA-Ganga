# Structural N=2 P=4 Relay-BP architecture

`relay_bp_parallel_n2_p4` broadcasts one accepted frame start and configuration writes to two physically replicated frozen engines. Graph, priors, syndrome, iteration limits, and first gamma are logically common but physically duplicated inside the engines for this correctness-first milestone.

Each engine privately owns nu, mu, marginals, active gamma, decisions, controller/iteration/relay state, candidate/correction state, and seed-state boundary. Two independent gamma valid/ready streams permit distinct trajectories without coupling progress.

The final result arbiter commits the first valid S=1 candidate. Engine 0 has deterministic priority when both candidates appear in the same cycle. Winner ID, weight, iteration/leg counts, frame ID, and commit cycle are latched atomically and remain stable. Global failure occurs only after both engines fail without a candidate. `first_success_cycle` is the candidate-sampling/winner-commit cycle, which is also the edge that makes sticky `global_done` visible.

Global correction reads are automatically routed to the committed winner; no consumer engine selection is required. Reads are invalid before a winner exists or after a dual failure.

## Phase-safe losing-engine cancellation

Winner commitment immediately drives `global_done`; it is not delayed by cleanup. On the following cycle the top asserts `cancel_request` only to the non-winning engine. Same-cycle dual success still chooses engine 0 and cancels engine 1. Cancellation is never classified as decoder failure.

The single-engine cancellation contract is `cancel_request`, pulse `cancel_ack`, sticky `cancelled`, and `quiescent`. Check, variable, convergence, and relay initialization drain the complete active verified phase before stopping. This guarantees all accepted reads receive exactly one consumed response, all accepted writes commit, and conflict-retry subsets finish without orphaning a transaction. Gamma loading stops at the current coefficient handshake boundary, deasserts `gamma_ready`, and pulses `gamma_abort` to terminate the external source. An idle loser can acknowledge cancellation to clear a same-cycle losing candidate.

After acknowledgement the engine has no owner, request, response, active phase controller, gamma write, or candidate notification. `pair_quiescent` is distinct from `global_done`; a new frame is accepted only after both engines are quiescent. No overlapping frames or double buffering are supported.

This conservative phase-boundary policy reduces wasted engine occupancy and energy when substantial work remains. It does not change first-success latency, and it can provide no saving when the loser is already near natural completion.

Remaining work: statistical N=1/N=2 latency and wasted-energy evaluation, SoC shell, and Vivado synthesis/implementation.

## Independent gamma generators

Normal N=2 operation may set `USE_INTERNAL_RNG=1`, instantiating one `relay_bp_gamma_rng` per engine. Fixture mode remains available for bit-exact legacy regression. Each generator uses a 64-bit xorshift recurrence `(13,7,17)` and has private seed, state, ready/valid, and abort state. It is deterministic and non-cryptographic. Seed zero is remapped to `0x9e3779b97f4a7c15`; every other seed is used literally.

The first leg remains uniform coefficient `+2` (`0.125*16`) and consumes no random words. Later legs reproduce continuous `Uniform[-0.24,0.66]` followed by ties-away rounding at `M=16`. A 10-bit PRNG region is accepted only when below 720. Regions allocate 17 values to coefficient -4, 50 values to every coefficient -3 through 10, and 3 values to coefficient 11. Rejected regions 720 through 1023 advance the PRNG but emit no coefficient.

State advances only when a random word is evaluated. A held `gamma_valid` value does not advance under backpressure. On abort, generation stops without `gamma_done`; the state is preserved after the last evaluated word, including a word already held by `gamma_valid`. The next requested leg continues from that state unless software explicitly loads a new seed. This gives cycle-independent coefficient sequences while making cancellation reproducible.

The PRNG sequence contract is an implementation/reproducibility choice. It does not change Relay-BP equations, gamma quantization, or per-leg gamma semantics.

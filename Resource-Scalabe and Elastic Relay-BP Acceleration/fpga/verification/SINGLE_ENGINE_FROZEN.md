# Frozen P=4 Relay-BP single-engine contract

- P=4 folded processing; one complete S=1 Relay trajectory.
- Signed 18-bit stored priors, biases, mu, nu, and marginals; signed 22-bit accumulator.
- M=16 coefficients; ties-away-from-zero rounding; saturation at stored-message boundaries.
- Full buffered mu and synchronous inference-wrapper-backed permanent memories.
- Canonical check-first iteration, marginal-only relay handoff, edge reset from physical priors.
- Hard decision `M <= 0`; convergence is exactly `H * e_hat == syndrome`.
- External gamma stream: start, leg index, variable count, valid/ready, variable index, signed 5-bit value, done, and 64-bit seed/state boundary.
- Uniform first-leg gamma fills active gamma RAM; later vectors are accepted only at leg boundaries and remain fixed for the leg.
- Four-bit packed correction readout; start/busy/done/converged/failed/candidate status.

Outside this engine: RNG algorithm, N=2 replication, first-success arbitration, cancellation, SoC/AXI shell, and Vivado implementation.

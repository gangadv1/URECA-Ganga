# Research Proposal: FPGA Architecture for Parallel Relay-BP Decoding of Quantum LDPC Codes

> Draft for a Master's research project. Insert the final paper citation, experimental references, and advisor-specific formatting where appropriate.

## Background

Quantum low-density parity-check (qLDPC) codes are a promising class of quantum error-correcting codes because they offer favorable asymptotic properties and can support scalable fault-tolerant quantum computation. In practice, however, decoding qLDPC codes remains a major bottleneck. Belief propagation (BP) is attractive because it is structured, iterative, and hardware-friendly, but in difficult decoding regimes it can suffer from slow convergence, error floors, and long-tail latency. These issues are especially problematic for real-time quantum error correction, where decode time must remain bounded and predictable.

Relay-BP is a message-passing decoding approach that improves on standard BP by introducing Relay-style trajectory behavior and schedule flexibility. The repository's architectural direction suggests that Relay-BP is particularly well suited to spatial parallelism, where multiple decoding trajectories can be executed concurrently and the earliest successful result can be selected. This makes Relay-BP a strong candidate for FPGA implementation.

[Insert literature references here: Relay-BP paper, qLDPC decoding surveys, FPGA decoding studies]

## Motivation

The central motivation for this project is that decoder latency, not only average error rate, determines whether a qLDPC decoder is usable in real-time systems. A single Relay-BP instance may still experience difficult cases that dominate end-to-end runtime. If several Relay-BP trajectories are run in parallel, each with a different schedule or seed, then the ensemble may reduce the tail of the decode-time distribution by allowing the first successful trajectory to terminate the computation.

An FPGA is a natural platform for this investigation because it can instantiate multiple lanes of a structured algorithm, exploit deterministic dataflow, and support custom memory architectures. The key research question is whether the available hardware resources can be used to trade spatial parallelism for reduced tail latency without degrading decoding performance beyond acceptable limits.

## Problem Statement

The problem addressed in this research is how to design and evaluate an FPGA architecture that executes multiple Relay-BP decoding trajectories in parallel for qLDPC decoding, while maintaining decoding correctness, limiting resource usage, and reducing the tail latency of the decoder.

More specifically, the project asks whether parallel Relay-BP lanes can provide a meaningful real-time advantage over a single BP or Relay-BP trajectory, and what architectural choices are required to make that advantage practical on FPGA fabric.

## Research Objectives

1. Design a spatially parallel FPGA architecture for Relay-BP decoding.
2. Develop a simulation framework to compare sequential Relay-BP and parallel Relay-BP behavior.
3. Evaluate the effect of different lane schedules, seeds, and arbitration policies on latency and decoding quality.
4. Investigate memory-sharing or compressed parity-check storage strategies that reduce hardware overhead.
5. Quantify the trade-off between resource usage and tail-latency improvement.
6. Produce a prototype HLS and/or RTL implementation suitable for synthesis and verification.
7. Compare the proposed architecture against baseline BP-style decoding behavior.

## Proposed Architecture

The proposed architecture consists of multiple Relay-BP lanes operating concurrently on the same received syndrome or log-likelihood input. Each lane performs the standard iterative variable-node and check-node updates associated with BP-style decoding, but each lane is parameterized by a distinct schedule, damping factor, or initialization seed. The hardware runs these lanes in lockstep or near-lockstep, depending on the final implementation choice.

A high-level block structure is as follows:

- Input broadcast logic distributes the syndrome and channel observations to all lanes.
- Each lane contains a Relay-BP decoding pipeline with its own iteration control and convergence monitor.
- A shared or compressed representation of the parity-check matrix reduces duplicated memory usage across lanes.
- A final arbitration unit selects the first valid converged output, or applies a bounded-wait policy to compare multiple completed candidates.
- Optional monitoring logic records iteration counts, convergence behavior, and residual syndrome weight for analysis.

The architecture is intended to exploit spatial parallelism rather than relying only on deeper pipelining of a single decoder instance. This is important because the main target is tail-latency reduction: several trajectories should race to convergence, and the design should return the earliest reliable decode result.

[Insert architecture diagram reference here]
[Insert experimental or simulation reference here]

## Expected Benefits

- Reduced tail latency compared with a single BP or single Relay-BP trajectory.
- Improved robustness against slow-converging or trapped decoding paths through trajectory diversity.
- Better use of FPGA spatial resources for a decoder workload that is naturally parallel at the lane level.
- Potentially improved real-time suitability for qLDPC decoding in latency-sensitive quantum control loops.
- A clearer implementation pathway from algorithm to hardware because Relay-BP remains within the message-passing family.

## Expected Trade-offs

- Higher resource consumption than a single-lane decoder because multiple trajectories must be instantiated.
- Increased design complexity due to arbitration logic, lane monitoring, and shared-memory coordination.
- Possible timing closure challenges if lane count and memory-sharing logic are not carefully balanced.
- Potential trade-off between number of lanes and per-lane quality if hardware constraints force reductions in precision or iteration budget.
- More complex verification because the ensemble behavior depends on concurrent execution and final-result selection.

## Open Research Questions

- How many Relay-BP lanes are needed before the tail-latency improvement becomes significant?
- Which schedule or seed diversification strategy gives the best latency-versus-quality trade-off?
- Can quasi-cyclic or otherwise compressed parity-check storage free enough hardware to support additional lanes?
- What arbitration policy is best: first-to-converge, bounded wait, majority vote, or residual-weight selection?
- How does the proposed architecture behave across different qLDPC code families and noise conditions?
- What is the practical resource cost in LUTs, FFs, BRAM/URAM, and timing slack for each lane configuration?
- Does the ensemble approach preserve decoding performance closely enough to justify the added hardware complexity?

## Research Scope and Methodology

The project will proceed in stages. First, a Python simulation framework will be used to model sequential Relay-BP and parallel Relay-BP trajectories under a common set of qLDPC benchmark cases. This stage will characterize latency distributions, convergence rates, and decoding accuracy trade-offs. Second, the best-performing architectural ideas will be translated into an FPGA-oriented design, beginning with high-level synthesis and then, if needed, a more detailed RTL implementation. Finally, synthesis and implementation reports will be used to assess resource usage and timing feasibility.

The evaluation will focus on:

- Latency distribution metrics, including mean and tail percentiles.
- Decoding success rate and error-rate behavior.
- Resource and timing estimates for the FPGA target.
- Sensitivity to lane count, schedule choice, and arbitration policy.

[Insert benchmark references here: code family, channel model, simulation settings]
[Insert synthesis/implementation references here once available]

## Expected Research Outcome

The expected outcome is a validated FPGA architecture and evaluation framework that demonstrates whether parallel Relay-BP decoding trajectories can reduce tail latency enough to justify their resource cost. If successful, the research will provide a strong basis for a thesis contribution on spatially parallel decoding for real-time quantum LDPC error correction.

## Notes for Future Expansion

- Replace placeholders with exact paper citations and figure/table references.
- Add a comparison table once simulation results are available.
- Expand the methodology section with the specific qLDPC code families, channel assumptions, and FPGA target device.
- Add advisor-approved formatting, abstract, and formal references if this document is promoted to a final proposal.

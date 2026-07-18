# FPGA Architecture for Parallel Relay-BP

This document describes the proposed FPGA architecture for executing multiple Relay-BP decoding trajectories in parallel for quantum LDPC decoding. The design follows a spatial-parallel approach: several decoder lanes receive the same syndrome input, process it concurrently using different gamma schedules, and race toward convergence. The first valid result is selected and returned, which makes the architecture suitable for tail-latency reduction in real-time decoding systems.

## Syndrome Dispatcher

The Syndrome Dispatcher is the entry point of the architecture. Its role is to accept the incoming syndrome, the associated channel information, and any control metadata needed to start a decode attempt, then distribute those inputs to every active Relay-BP lane. In the proposed design, the dispatcher does not perform any decoding logic itself; instead, it acts as a fan-out stage that ensures all lanes observe the same decode instance at the same time. This identical-input behavior is important because the architectural goal is to compare multiple Relay trajectories under the same conditions rather than processing different syndromes independently.

In hardware terms, the dispatcher is a lightweight control and routing block. It can buffer the input syndrome, align the data to the internal clock domain, and broadcast the information through replicated buses or a simple multicast network. Because the design is intended to support multiple lanes without introducing unnecessary serialization, the dispatcher should be implemented as a low-latency front-end with minimal combinational delay. Its output must be stable long enough for every lane to initialize its internal state and begin the first Relay-BP iteration simultaneously.

## Relay-BP Engine

The Relay-BP Engine is the core computational block in each lane. It implements the iterative message-passing behavior of the decoder, including variable-node updates, check-node updates, and the Relay-specific gamma-controlled memory effect that distinguishes the trajectory from plain BP. Each lane executes the same basic decoding algorithm, but the schedules, damping behavior, or initialization seeds may differ from lane to lane. This diversity is what allows the parallel architecture to explore multiple convergence paths at once and reduce the chance that a single slow trajectory dominates the overall decode time.

From an FPGA perspective, the Relay-BP Engine is a streaming iterative pipeline. The lane repeatedly reads the parity-check structure, computes local messages, updates beliefs, and forms a new tentative decoded error estimate. The computation is structured enough to map onto HLS or RTL, yet flexible enough to support different gamma schedules without changing the overall datapath. Because the relay memory term can be implemented as a weighted contribution from the previous iteration, the engine needs access to the current and prior belief state, along with the per-iteration gamma value selected by the schedule controller.

## Local BRAM

Local BRAM stores the lane-private data needed during decoding. This typically includes the current message state, the variable-node beliefs, temporary check-node outputs, and any schedule-dependent constants that are specific to a lane. Keeping these values in local memory allows each lane to operate independently after the initial broadcast, which reduces contention and helps preserve deterministic timing. In a parallel design, local BRAM is essential because it prevents the decoder from re-reading or reconstructing the same ephemeral values from shared memory every cycle.

The use of BRAM also supports throughput by giving each lane fast access to its working set. If the decoder is implemented with several lanes, each lane can have a compact private memory bank sized to the message footprint of that lane. This is especially important when the architecture uses several gamma schedules in parallel, because each lane may evolve differently over time even though they all start from the same syndrome. Local BRAM keeps the lane logic self-contained and makes the design easier to scale by adding or removing lanes.

## Convergence Monitor

The Convergence Monitor checks whether a lane has successfully decoded the current syndrome. Its job is to inspect the decoded candidate produced by the Relay-BP Engine, verify whether the residual syndrome weight has dropped to zero, and assert a done signal when the lane has converged. The monitor therefore acts as the lane-level termination detector and is the source of the success/failure signal used by the selection logic later in the datapath.

In practice, the Convergence Monitor should be lightweight and deterministic. It does not need to perform complex decoding work; it only needs to compute or verify the syndrome residual and determine whether the lane has reached a valid codeword estimate. Because this check is performed repeatedly during decoding, the monitor should be designed so that it can evaluate convergence without introducing a large critical path. When a lane converges, the monitor records that lane’s completion time and can freeze further updates for that lane while the remaining lanes continue running.

## First-Success Selector

The First-Success Selector is the arbitration block that chooses which lane’s result should be returned to the caller. Its primary policy is to select the first lane that converges successfully, because this directly targets the tail-latency problem that motivates the parallel architecture. Once a lane asserts a valid done signal, the selector captures that lane’s decoded output and tags it as the winner. If multiple lanes converge in the same cycle, the selector can use a fixed priority order, a lowest-residual policy, or another deterministic arbitration rule defined at design time.

This block is intentionally simple because it should not become the new source of latency. The selector should be a shallow muxing and control structure rather than a second-stage decoder. Its function is to stop waiting as soon as a reliable result exists, which is the central advantage of running multiple Relay trajectories in parallel. In a bounded-wait variant, the selector may hold the result for a small fixed number of cycles to compare near-simultaneous finishers, but the wait window must remain small enough that it does not recreate the long-tail behavior the architecture is trying to eliminate.

## Output Buffer

The Output Buffer stores the final decoded error estimate before it is sent to the host or downstream error-correction logic. The buffer captures the selected lane’s output, the identity of the winning lane, the number of iterations required, and any other summary metrics needed for logging or debugging. This decouples the internal decoder timing from the external consumer of the result and gives the system a clean handoff point once a successful decode has been chosen.

The buffer also makes the design more robust. If the output interface is temporarily busy, the decoded result can be held briefly without forcing the Relay-BP lanes to repeat work. In research prototypes, the buffer is also a convenient place to store metadata for later analysis, such as convergence latency, lane selection statistics, and residual syndrome information. That makes it useful both as a hardware interface and as an observability point for the simulation and verification workflow.

## Complete Decoding Workflow

The decoding process begins when the Syndrome Dispatcher receives a new syndrome and associated channel information from the system input. The dispatcher broadcasts the same inputs to every Relay-BP lane, and each lane initializes its local BRAM, beliefs, and lane-specific gamma schedule. Once initialization is complete, all lanes begin decoding at the same time and advance through their iterative message-passing updates in parallel.

During each iteration, every Relay-BP Engine performs its local variable-node and check-node updates, applies the gamma-controlled memory term, and produces a new tentative decoded estimate. After the update, the Convergence Monitor checks whether the candidate satisfies the syndrome constraints. Lanes that have not converged continue to the next iteration, while lanes that do converge assert a done signal and record their iteration count and residual weight.

As soon as one or more lanes signal success, the First-Success Selector chooses the winning result. In the simplest version of the architecture, the first lane to converge is returned immediately. In a slightly more conservative version, the selector may wait a small fixed number of cycles to compare a few near-simultaneous finishers, but the final decision remains bounded and deterministic. The winning output is then written into the Output Buffer together with the lane identifier and performance metadata.

The overall effect of this workflow is that the decoder does not depend on a single potentially slow trajectory. Instead, it races several Relay-BP trajectories against each other and returns the first successful decode. This is the architectural mechanism that reduces tail latency while preserving the underlying message-passing structure of the decoder.

## Architectural Summary

The proposed FPGA architecture is built around a simple but important idea: keep the decoding logic local to each lane, keep the syndrome input shared, and make the result selection fast. The Syndrome Dispatcher provides the common starting point, the Relay-BP Engine performs the actual trajectory computation, Local BRAM supports lane-private state, the Convergence Monitor determines when a lane has finished, the First-Success Selector chooses the winner, and the Output Buffer hands the result to the rest of the system. Together, these blocks form a parallel decoding architecture intended to reduce tail latency for quantum LDPC decoding on FPGA hardware.

[Insert architecture figure reference here]
[Insert synthesis or HLS reference here once available]
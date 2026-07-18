# URECA-Ganga

ChatGPT Chats

https://chatgpt.com/share/6a527905-1194-83ec-8654-7112dda90d60

https://chatgpt.com/share/6a527943-97a8-83ec-ad99-f26f872172a7

https://chatgpt.com/share/6a57cbcc-03e0-83ec-8068-d60f793dbd19

Gemini Chats

https://share.gemini.google/UnNLO6ieRnBn

## Repository Structure

The repository is organized around an FPGA-based Parallel Relay-BP research workflow. `Resource-Scalabe and Elastic Relay-BP Acceleration/` contains the project-specific materials, with `docs/` for literature, proposals, architecture notes, diagrams, meeting records, and future work. `simulations/` holds Python-based decoder studies and evaluation results, `relay_models/` captures model variants and scheduling experiments, `fpga/` contains the HLS, RTL, verification, synthesis, implementation, and report artifacts, and `datasets/`, `figures/`, and `scripts/` store shared inputs, visuals, and supporting utilities.

## Current Project Status

The project is currently in the research and architecture design phase. Implementation will begin with Python simulations before moving into FPGA HLS and RTL development.

## Planned Development Roadmap

### Phase 1
- Literature review
- Research proposal
- FPGA architecture design

### Phase 2
- Sequential Relay-BP simulator
- Parallel Relay-BP simulator
- Monte Carlo evaluation

### Phase 3
- FPGA HLS implementation
- RTL implementation
- Verification and synthesis

### Phase 4
- Experimental evaluation
- Resource analysis
- Performance comparison
- Thesis/paper preparation

## Research Goal

The goal is to investigate whether FPGA spatial parallelism can reduce the tail latency of Relay-BP decoding by executing multiple Relay decoding trajectories concurrently while preserving decoding performance for real-time quantum LDPC decoding.

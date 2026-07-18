# Parallel Relay-BP FPGA System Block Diagram

```mermaid
flowchart TD
    QP[Quantum Processor] --> SD[Syndrome Dispatcher]
    SD --> E1[Four Parallel Relay-BP Engines\nEngine 1]
    SD --> E2[Four Parallel Relay-BP Engines\nEngine 2]
    SD --> E3[Four Parallel Relay-BP Engines\nEngine 3]
    SD --> E4[Four Parallel Relay-BP Engines\nEngine 4]
    E1 --> CM[Convergence Monitor]
    E2 --> CM
    E3 --> CM
    E4 --> CM
    CM --> PS[Priority Selector]
    PS --> CO[Correction Output]
```

This diagram shows the high-level dataflow for a Parallel Relay-BP FPGA decoder. The quantum processor produces syndrome information, the syndrome dispatcher broadcasts it to four Relay-BP engines, the convergence monitor checks the lane outputs, the priority selector chooses the best valid result, and the correction output is sent downstream for quantum error correction.
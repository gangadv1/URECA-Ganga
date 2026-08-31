# N=2 stagnation-priority shared-resource model

Historical N=2 uses two independent simultaneous P=4 engines. This separate experiment serializes one complete Relay-BP iteration at a time through one shared BA2 P=4 resource; pauses preserve all state and both trajectories run to natural completion.

The frozen signal is `iterations_since_last_strict_best >= 120` at a completed boundary of leg 3 or later. A new strict best restores 1:1 service immediately. Policies are neutral 1:1, conservative 1:2, and 1:3. Only p=0.003 has reliable paired E0/E1 traces; p=0.002 and p=0.004 archives contain E0 only. This is a resource-scheduling model, not early termination, an FPGA-speedup claim, or a reinterpretation of historical N=2 latency.

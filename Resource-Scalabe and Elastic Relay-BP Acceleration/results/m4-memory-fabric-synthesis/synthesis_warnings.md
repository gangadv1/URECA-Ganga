# Synthesis warnings and risks

No Vivado warning log exists because synthesis was not launched. Architecture-relevant unknowns remain: block-RAM versus LUTRAM inference, true-dual-port mapping, replication, width adaptation, cascade depth, initialization, reset handling, collision mode, unused bits, and timing. Treating the absence of warnings as a pass would be incorrect.

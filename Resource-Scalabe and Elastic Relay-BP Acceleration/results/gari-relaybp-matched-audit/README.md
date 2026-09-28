# GARI-NMS versus Relay-BP matched-comparison audit

This directory records an audit and experiment specification only. No GARI-vs-Relay-BP benchmark was launched, and neither decoder was modified to force agreement.

## Pinned sources

- URECA: commit `c4dc34e560c7af78b7e6397e506ba6d27f3e7eb7`.
- Official GARI-NMS: shallow checkout at commit `6380d52e76d8c9cb0b4eedf3e8d2429b24cef78d`.
- GARI source was inspected read-only from `/tmp/gari-nms-audit`.

## Headline result

The clean comparison is a same-STIM-sample software experiment, but it is **NOT_READY** today. The URECA canonical circuit-level workload is Z-memory, 12 rounds, p=0.003, with 1,728 detectors, 67,752 DEM fault variables, and 12 observables. The official GARI driver can consume the same detector samples and observable labels, but its decoder graph transformation, X/Z detector partition, expanded matrix, prior layout, and output contract must first be validated on that circuit.

The official repository's original [[144,12,12]] path is not one unique dataset. The default driver uses `data/circuits/BB_n144_k12_d12_CL_both_0.002.stim`; the repository also contains Google SI1000 and IBM-family circuits at other p values. These families must not be silently mixed.

## Files

- `gari_configuration.csv`: itemized official implementation audit.
- `relaybp_configuration.csv`: itemized canonical URECA Relay-BP audit, excluding hidden-error legacy simulators.
- `compatibility_matrix.csv`: GREEN/YELLOW/RED comparison matrix.
- `matched_experiment_spec.md`: frozen workload, inputs, outputs, scoring, metrics, and tails.
- `reproduction_plan.md`: original GARI reproduction check, command, expected artifact, cost, and blockers.
- `audit_summary.json`: machine-readable audit record with evidence grades.

## Important quarantine

The code-capacity baseline and historical simulators that construct priors from `true_error` are not the canonical path. This audit uses the committed circuit-level package under `graphs/generated/gross_circuit_level/memory_Z_r12_p0p003`, frozen STIM samples under `results/circuit-level-multiseed/paired_samples.npz`, and `reference/relay_bp_float.py`.

Modeled Relay-BP cycles are software architectural estimates. They are not FPGA nanoseconds and are not compared to GARI's reported software seconds or any FPGA timing.
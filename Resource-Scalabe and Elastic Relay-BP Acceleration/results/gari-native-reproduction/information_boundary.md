# Native GARI information boundary

Pinned source: https://github.com/astra-decoders/gari-nms/tree/6380d52e76d8c9cb0b4eedf3e8d2429b24cef78d

## Finding: PASS — no hidden-information input path found in this command

Reviewed the actual executed driver, ctypes wrapper, C batch routine, C single-decoder routine, and static matrix transformation. Preserved source copies and SHA-256 checks are in `official_source/` and `source_verification.json`.

- `stim_batched_data_v2.py:129-143`: circuit DEM determines check matrix, observable matrix, and physical priors; helper graph expansion uses only these static quantities. Fresh run computes caches rather than trusting prior caches whose filenames omit p.
- `stim_batched_data_v2.py:206-230`: prior type 0 assigns 0.5 to the base variables and DEM probabilities to physical-variable blocks. LLRs and ab scoring priors are constant across shots.
- `stim_batched_data_v2.py:239-246`: `return_errors=True` path is commented out. Executed sampler returns detector bits, observable labels, and an unused third result; no true physical error vector is requested or passed.
- `stim_batched_data_v2.py:252-282`: detector bits are partitioned, padded with static zero constraints, bipolarized and passed with LLRs, graph adjacency, dimensions, schedule parameters, and static dz/l_dz matrices.
- `my_decoders/hbplib_wrapper_v2.py:93-191`: wrapper's input signature has no sampled observable labels or physical error vector. `logical_errors_out` is an output buffer for predicted logical action, not ground truth. Static `l_dz` maps candidate corrections to logical action and is legitimate code information.
- `my_decoders/hbp_decoder_v2.c:535-638`: candidates are decoded with schedule seeds derived from static parameters; selection uses native convergence, returned iteration index, and static LLR score. Only one member is used here. The observed logical answer never participates in member selection.
- `stim_batched_data_v2.py:290-317`: observed logical labels are compared with predictions only after decoding to score logical mismatches and to implement the documented aggregate 100-error stopping condition. Outcome-based experiment stopping is not retrospective candidate selection.
- Passive observer records already-produced outputs and labels after the C call and timer stop. It never supplies labels to the decoder, changes arrays, or retries/selects a candidate.

## Native semantics and limitations (not hidden-information paths)

1. Early stopping checks only rows `dxshape0 .. hshape0-1` of the expanded graph (the B/dz syndrome block), not all graph parity constraints. Reported convergence means **native selected-block convergence**.
2. A C sweep serially updates every expanded-graph check row. Schedule 2 visits bottom identity/correlation constraints, then separately permuted A and B check groups. Each row removes the old check message, forms normalized min-sum messages (alpha 0.96875), adds updated messages into variable LLRs, and updates hard decisions. The selected-block parity check follows the sweep.
3. Loop is `for (loop=0; loop<=Nloop; ++loop)`. A returned index k<400 represents k+1 sweeps. Index 0 can mean convergence after the first sweep. With no accepted convergence, up to 401 sweeps occur. The batch routine accepts only indices <400 and maps nonaccepted outcomes to 400; this includes convergence at index 400 and exhaustion returning 401. Thus returned 400 is a native rejection sentinel, not a precise work count.
4. No accepted ensemble produces zero logical correction and index 400. Driver `n_fail` counts observed/predicted logical mismatches, so some native nonconverged shots can be counted as logically correct. We retain every shot and separately report logical errors, native rejection, their overlap, and their union. We do not rewrite official scoring.
5. All-shot iteration means include sentinel 400. CSV rounds each batch mean to an integer, then Sinter sums `avg_itr` and `base`. `avg_itr/base` is an average of rounded batch means; it is not a total iteration count, and can be biased if batch sizes differ.
6. General multi-member `poi='i'` selection has a source caveat: when a later candidate has fewer iterations, `best_score` is not reset before the score comparison. Consequently it does not unconditionally enforce lexicographic minimum iterations. This does not affect this ens=1 command. No future multi-member configuration is validated here.
7. C has input/allocation error paths with coarse failure indicators and no distinct per-shot status code. No such emitted error is acceptable as successful completion. Full memory-allocation correctness is not proved by this experiment.

A GARI iteration cannot automatically be equated to a Relay-BP iteration: graph expansion, row schedule, stopping predicate, and zero-based/sentinel reporting define different work. No GARI cycle count is derived or asserted.

## Measured graph dimensions

The native DEM has shape 1,728 × 67,752. GARI expands this to 18,432 × 84,456. The A/dx block is 792 × 7,920 and the B/dz block is 936 × 8,784. Native early stopping checks those 936 B/dz rows. These dimensions were recorded from the unchanged driver during the first completed batch.

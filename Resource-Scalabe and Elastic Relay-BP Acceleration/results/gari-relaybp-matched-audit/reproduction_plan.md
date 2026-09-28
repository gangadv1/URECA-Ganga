# Official GARI reproduction plan

## Exact first command

From the official repository root, after installing the documented dependencies and building the C wrapper:

```bash
python3 -m pip install ldpc stim sinter
cd my_decoders && make clean && make && cd ..
python3 stim_batched_data_v2.py 12 0.002 400 0.96875 1 0 2 16 100 0 i 4
```

The twelve arguments are `dist p itrs msf rs priort cs shot_multiplier max_errs ens poi num_threads`. This selects d=12, p=0.002, 400 iterations, alpha=0.96875, schedule seed 1, `priort=0`, custom schedule 2, 16,384 shots per chunk, 100 accumulated errors, one effective decoder (`ens=0`), iteration-based selection, and four threads.

## Expected artifact

The driver loads `data/circuits/BB_n144_k12_d12_CL_both_0.002.stim` and appends a Sinter CSV named approximately:

`data/BB_etB_corr_400_0.96875_1_2_et1_d12_<SLURM_JOB_ID>.csv`

The exact suffix is empty when `SLURM_JOB_ID` is unset. The row has `shots`, `errors`, `seconds`, decoder name, metadata `{d:12,p:0.002,rounds:12}`, and custom `avg_itr`. The program prints a Sinter logical error rate per round after reaching the error target.

## Expected behavior and cost

This is a reproduction check, not the matched benchmark. It is potentially expensive: the driver samples chunks until 100 logical errors and the checked-in d=12 GARI final data includes runs ranging from tens of thousands to tens of millions of shots depending on p and ensemble. Estimate minutes to days depending on CPU, C build, and decoder selection. Do not run it as part of this audit.

## Environment

- Python 3.11 is required by the official README.
- Python packages: `ldpc`, `stim`, `sinter`; the source also imports NumPy, SciPy, NetworkX, Matplotlib, and PyMatching through helper paths.
- A working C compiler and `make` are required under `my_decoders`.
- Four threads are requested by the command; record CPU, compiler, package versions, and OpenMP status.

## Blockers and cautions

1. The original driver does not set an explicit Stim DEM sampler seed, so the original software result is not bit-reproducible from the command alone. Record the generated artifact and treat its statistics as a reproduction envelope, not a frozen sample panel.
2. The official repository contains several [[144,12,12]] circuit families: default CL, Google SI1000, and IBM uniform-circuit. Reproduction must use the default driver file above, not a final-data row selected by filename alone.
3. `ens=0` is converted to one effective decoder. The final data also contains ensemble-24 runs; those are separate configurations.
4. Do not compare the CSV `seconds` field with URECA modeled cycles or FPGA nanoseconds.

## Pass criterion

Pass means the command builds, loads the expected default circuit, produces a valid Sinter CSV with d=12/p=.002/r=12 metadata, and the decoder completes without hidden-error input. Do not require a bit-for-bit match to a final CSV because the original Stim sampling seed is unspecified. Only after this pass should the controlled same-STIM adapter experiment be considered.
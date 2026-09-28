# Dependency and attempt history

## Prior attempt, supplied by user and observed active
- Python 3.13.6 (README requires 3.11), Stim 1.15.0; user reported ldpc 2.4.1 and sinter 1.16.0 installed in workspace venv.
- User reported initial missing ldpc, sinter, networkx, pymatching; dependency installation then succeeded.
- User reported make was first issued from wrong directory and failed; later native Makefile succeeded from my_decoders.
- User reported shell output redirection failed before launch; corrected attempt is PID 16286, timed by /usr/bin/time -p, writing original root run_stdout.txt and run_stderr.txt.
- We did not interrupt or overwrite that attempt. Its raw outputs will be archived separately after completion. No per-shot observer was attached to it.

## This turn
- Default Python is 3.13.6. Installed Python 3.11.2 initially lacked Stim (PackageNotFoundError); isolated venv /tmp/gari-native-py311 created.
- Initial pip install ldpc stim sinter failed with DNS/network sandbox errors (Errno 8; retries exhausted; misleading final 'No matching distribution found'). Not a demonstrated package incompatibility.
- Approved network-enabled retry installed documented dependencies and their transitives successfully. Sinter emitted legacy setup.py-install deprecation because the venv bundled pip 22.3.1 without wheel. No version was changed to improve decoder outcome; official repository provides no dependency pins.
- pip warned its normal user cache was unwritable; cache was disabled. MPLCONFIGDIR points to /tmp/gari-native-mpl to keep Matplotlib cache writable.
- Native make clean && make succeeded unchanged; make -B repeated solely to capture complete build stdout/stderr. Six warnings: unused Hcols/Hcols_c, dz/dz_rows/dz_cols, alloc_1d_int. No source patch or compiler flag substitution.
- Sandboxed process inspection failed ('operation not permitted'); approved process inspection identified the pre-existing exact-command Python 3.13 process.
- Fresh official git archive has no generated matrix caches or output CSV; driver computes both caches normally. Existing prior-run caches are not reused.
- Primary exact command runs under Python 3.11.2 with a documented passive trace observer; PYTHONUNBUFFERED=1 only affects output buffering. Observer saves already-returned native outputs after the native timer ends.

### Retained diagnostic excerpts from this turn

These are excerpts from captured tool output, not fabricated complete log files:

```
importlib.metadata.PackageNotFoundError: No package metadata was found for stim
3.11.2 (v3.11.2:878ead1ac1, Feb 7 2023, 10:02:41)
```

```
WARNING: The directory '/Users/gangadevi.aa/Library/Caches/pip' or its parent directory is not owned or is not writable by the current user. The cache has been disabled.
Failed to establish a new connection: [Errno 8] nodename nor servname provided, or not known
ERROR: Could not find a version that satisfies the requirement ldpc (from versions: none)
ERROR: No matching distribution found for ldpc
```

The network-enabled retry succeeded; this final error from the sandboxed retry sequence does not establish that ldpc was unavailable for Python 3.11.

```
DEPRECATION: sinter is being installed using the legacy 'setup.py install' method, because it does not have a 'pyproject.toml' and the 'wheel' package is not installed.
```

Full subsequent installed package versions are in requirements-freeze.txt. Complete captured native compilation warnings are in build_stderr.txt. No decoder execution failure has been omitted or converted into a success by these setup repairs.

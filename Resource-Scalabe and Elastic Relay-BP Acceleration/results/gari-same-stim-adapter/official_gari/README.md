# GARI-NMS decoder

The code herein is to reproduce the results of [the paper](https://arxiv.org/pdf/2510.14060)

Note: A cleaned-up user-friendly version of this code is in preparation.

Directory structure:
- `data/`
  - `final/`  ← contains the data used for plots in the paper
  - `circuits/` ← contains the stim circuits used
- `my_decoders/`
  - `[hbp_decoder_v2.c](my_decoders/hbp_decoder_v2.c)` ← actual decoder implementation in C
- `stim_batched_data_v2.py` ← main file

Setup (Python 3.11 required)
- `pip install ldpc stim sinter`
- `cd my_decoders && make clean && make && cd ..`

Run:
- python stim_batched_data_v2.py

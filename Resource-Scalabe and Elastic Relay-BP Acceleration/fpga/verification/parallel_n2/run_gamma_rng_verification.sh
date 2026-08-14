#!/bin/sh
set -eu
python3 fpga/verification/parallel_n2/gamma_rng_reference.py
iverilog -g2012 -DRELAY_BP_SIM_ASSERT -s tb_relay_bp_gamma_rng -o /tmp/relay_bp_gamma_rng.vvp fpga/rtl/relay_bp_gamma_rng.sv fpga/testbench/tb_relay_bp_gamma_rng.sv
vvp /tmp/relay_bp_gamma_rng.vvp

#!/bin/sh
set -eu
python3 fpga/verification/small_graph_b18/generate_small_graph_vectors.py
sh fpga/verification/locked_b18/run_primitive_verification.sh
iverilog -g2012 -s tb_relay_bp_single_engine_p4 -o /tmp/relay_bp_single_engine_p4.vvp \
  fpga/rtl/relay_bp_round_div16.sv fpga/rtl/relay_bp_sat18.sv \
  fpga/rtl/relay_bp_bias18.sv fpga/rtl/relay_bp_single_engine_p4.sv \
  fpga/testbench/tb_relay_bp_single_engine_p4.sv
vvp /tmp/relay_bp_single_engine_p4.vvp
PYTHONPATH=reference python3 reference/directed_tests.py

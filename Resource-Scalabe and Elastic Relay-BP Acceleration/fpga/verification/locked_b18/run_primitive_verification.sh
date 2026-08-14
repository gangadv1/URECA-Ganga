#!/bin/sh
set -eu

python3 fpga/verification/locked_b18/generate_vectors.py

iverilog -g2012 -s tb_relay_bp_arithmetic18 -o /tmp/relay_bp_arithmetic18.vvp \
  fpga/rtl/relay_bp_round_div16.sv fpga/rtl/relay_bp_sat18.sv \
  fpga/testbench/tb_relay_bp_arithmetic18.sv
vvp /tmp/relay_bp_arithmetic18.vvp

iverilog -g2012 -s tb_relay_bp_bias18 -o /tmp/relay_bp_bias18.vvp \
  fpga/rtl/relay_bp_round_div16.sv fpga/rtl/relay_bp_sat18.sv \
  fpga/rtl/relay_bp_bias18.sv fpga/testbench/tb_relay_bp_bias18.sv
vvp /tmp/relay_bp_bias18.vvp

iverilog -g2012 -s tb_relay_bp_check_min2_18 -o /tmp/relay_bp_check18.vvp \
  fpga/rtl/relay_bp_check_min2_18.sv fpga/testbench/tb_relay_bp_check_min2_18.sv
vvp /tmp/relay_bp_check18.vvp

iverilog -g2012 -s tb_relay_bp_variable_node_18 -o /tmp/relay_bp_variable18.vvp \
  fpga/rtl/relay_bp_round_div16.sv fpga/rtl/relay_bp_sat18.sv \
  fpga/rtl/relay_bp_bias18.sv fpga/rtl/relay_bp_variable_node_18.sv \
  fpga/testbench/tb_relay_bp_variable_node_18.sv
vvp /tmp/relay_bp_variable18.vvp

# Structural elaboration only: traversal controllers and physical memories are intentionally absent.
iverilog -g2012 -s relay_bp_p4_datapath_shell -o /tmp/relay_bp_p4_shell.vvp \
  fpga/rtl/relay_bp_round_div16.sv fpga/rtl/relay_bp_sat18.sv \
  fpga/rtl/relay_bp_bias18.sv fpga/rtl/relay_bp_check_min2_18.sv \
  fpga/rtl/relay_bp_variable_node_18.sv fpga/rtl/relay_bp_p4_datapath_shell.sv
echo "P4_SHELL_RESULT elaborated=1 failed=0"

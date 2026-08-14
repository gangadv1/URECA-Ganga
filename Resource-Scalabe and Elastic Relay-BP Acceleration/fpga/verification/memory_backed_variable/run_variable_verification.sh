#!/bin/sh
set -eu
python3 fpga/verification/memory_backed_variable/generate_variable_vectors.py
iverilog -g2012 -s tb_relay_bp_variable_controller_p4 -o /tmp/relay_bp_variable_controller.vvp \
 fpga/rtl/relay_bp_round_div16.sv fpga/rtl/relay_bp_sat18.sv fpga/rtl/relay_bp_bias18.sv \
 fpga/rtl/relay_bp_response_memory.sv fpga/rtl/relay_bp_variable_controller_p4.sv \
 fpga/testbench/tb_relay_bp_variable_controller_p4.sv
vvp /tmp/relay_bp_variable_controller.vvp
sh fpga/verification/memory_backed_check/run_check_verification.sh

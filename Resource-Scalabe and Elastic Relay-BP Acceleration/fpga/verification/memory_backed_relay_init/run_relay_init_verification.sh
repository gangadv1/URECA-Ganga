#!/bin/sh
set -eu
python3 fpga/verification/memory_backed_relay_init/generate_relay_vectors.py
iverilog -g2012 -s tb_relay_bp_relay_init_controller_p4 -o /tmp/relay_bp_relay_init.vvp \
 fpga/rtl/relay_bp_response_memory.sv fpga/rtl/relay_bp_relay_init_controller_p4.sv \
 fpga/testbench/tb_relay_bp_relay_init_controller_p4.sv
vvp /tmp/relay_bp_relay_init.vvp
sh fpga/verification/memory_backed_convergence/run_convergence_verification.sh

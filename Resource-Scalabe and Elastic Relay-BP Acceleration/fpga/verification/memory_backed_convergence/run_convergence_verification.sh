#!/bin/sh
set -eu
python3 fpga/verification/memory_backed_convergence/generate_convergence_vectors.py
iverilog -g2012 -s tb_relay_bp_convergence_controller_p4 -o /tmp/relay_bp_convergence_controller.vvp \
 fpga/rtl/relay_bp_response_memory.sv fpga/rtl/relay_bp_convergence_controller_p4.sv \
 fpga/testbench/tb_relay_bp_convergence_controller_p4.sv
vvp /tmp/relay_bp_convergence_controller.vvp
sh fpga/verification/memory_backed_variable/run_variable_verification.sh

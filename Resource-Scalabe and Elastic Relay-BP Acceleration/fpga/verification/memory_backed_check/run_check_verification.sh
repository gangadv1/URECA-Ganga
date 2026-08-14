#!/bin/sh
set -eu
python3 fpga/verification/memory_backed_check/generate_check_vectors.py
iverilog -g2012 -s tb_relay_bp_check_controller_p4 -o /tmp/relay_bp_check_controller.vvp \
 fpga/rtl/relay_bp_response_memory.sv fpga/rtl/relay_bp_check_controller_p4.sv \
 fpga/testbench/tb_relay_bp_check_controller_p4.sv
vvp /tmp/relay_bp_check_controller.vvp
sh fpga/verification/small_graph_b18/run_complete_engine_verification.sh
iverilog -g2012 -s tb_relay_bp_sync_p4_memory -o /tmp/relay_bp_sync_memory.vvp \
 fpga/rtl/relay_bp_sync_p4_memory.sv fpga/testbench/tb_relay_bp_sync_p4_memory.sv
vvp /tmp/relay_bp_sync_memory.vvp
iverilog -g2012 -s tb_relay_bp_sync_banked_gather -o /tmp/relay_bp_banked.vvp \
 fpga/rtl/relay_bp_sync_banked_gather.sv fpga/testbench/tb_relay_bp_sync_banked_gather.sv
vvp /tmp/relay_bp_banked.vvp

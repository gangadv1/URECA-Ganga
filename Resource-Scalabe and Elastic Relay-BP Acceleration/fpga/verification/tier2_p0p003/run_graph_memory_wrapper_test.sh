#!/bin/sh
set -eu
iverilog -g2012 -DRELAY_BP_SIM_ASSERT -s tb_relay_bp_graph_memory_fabric_p4 -o /tmp/relay_bp_graph_memory_fabric.vvp \
 fpga/rtl/relay_bp_four_bank_ram.sv fpga/rtl/relay_bp_packed_sync_ram.sv fpga/rtl/relay_bp_memory_fabric_p4.sv \
 fpga/testbench/tb_relay_bp_graph_memory_fabric_p4.sv
vvp /tmp/relay_bp_graph_memory_fabric.vvp

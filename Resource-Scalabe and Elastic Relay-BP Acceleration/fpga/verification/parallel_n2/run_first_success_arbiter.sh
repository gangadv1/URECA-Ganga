#!/bin/sh
set -eu
iverilog -g2012 -DRELAY_BP_SIM_ASSERT -s tb_relay_bp_first_success_arbiter_n2 -o /tmp/relay_bp_n2_arbiter.vvp fpga/rtl/relay_bp_first_success_arbiter_n2.sv fpga/testbench/tb_relay_bp_first_success_arbiter_n2.sv
vvp /tmp/relay_bp_n2_arbiter.vvp

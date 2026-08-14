#!/bin/sh
set -eu
src="fpga/rtl/relay_bp_gamma_rng.sv fpga/rtl/relay_bp_round_div16.sv fpga/rtl/relay_bp_sat18.sv fpga/rtl/relay_bp_bias18.sv fpga/rtl/relay_bp_four_bank_ram.sv fpga/rtl/relay_bp_packed_sync_ram.sv fpga/rtl/relay_bp_memory_fabric_p4.sv fpga/rtl/relay_bp_check_controller_p4.sv fpga/rtl/relay_bp_variable_controller_p4.sv fpga/rtl/relay_bp_convergence_controller_p4.sv fpga/rtl/relay_bp_relay_init_controller_p4.sv fpga/rtl/relay_bp_single_engine_memory_p4.sv fpga/rtl/relay_bp_first_success_arbiter_n2.sv fpga/rtl/relay_bp_parallel_n2_p4.sv fpga/testbench/tb_relay_bp_tier2_n2_cancellation_structural.sv"
iverilog -g2012 -DRELAY_BP_SIM_ASSERT -s tb_relay_bp_tier2_n2_cancellation_structural -o /tmp/relay_bp_tier2_cancel.vvp $src
vvp /tmp/relay_bp_tier2_cancel.vvp

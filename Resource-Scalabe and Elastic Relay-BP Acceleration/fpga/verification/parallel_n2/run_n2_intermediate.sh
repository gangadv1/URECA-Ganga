#!/bin/sh
set -eu
src="fpga/rtl/relay_bp_gamma_rng.sv fpga/rtl/relay_bp_round_div16.sv fpga/rtl/relay_bp_sat18.sv fpga/rtl/relay_bp_bias18.sv fpga/rtl/relay_bp_four_bank_ram.sv fpga/rtl/relay_bp_packed_sync_ram.sv fpga/rtl/relay_bp_memory_fabric_p4.sv fpga/rtl/relay_bp_check_controller_p4.sv fpga/rtl/relay_bp_variable_controller_p4.sv fpga/rtl/relay_bp_convergence_controller_p4.sv fpga/rtl/relay_bp_relay_init_controller_p4.sv fpga/rtl/relay_bp_single_engine_memory_p4.sv fpga/rtl/relay_bp_first_success_arbiter_n2.sv fpga/rtl/relay_bp_parallel_n2_p4.sv fpga/testbench/relay_bp_deterministic_gamma_source.sv fpga/testbench/tb_relay_bp_parallel_n2_p4.sv"
python3 fpga/verification/memory_backed_engine/generate_engine_vectors.py
for pair in "0 0" "0 7" "7 0";do set -- $pair;iverilog -g2012 -DRELAY_BP_SIM_ASSERT -Ptb_relay_bp_parallel_n2_p4.S0=$1 -Ptb_relay_bp_parallel_n2_p4.S1=$2 -s tb_relay_bp_parallel_n2_p4 -o /tmp/relay_bp_n2.vvp $src;vvp /tmp/relay_bp_n2.vvp;done

#!/bin/sh
set -eu
python3 fpga/verification/memory_backed_engine/generate_engine_vectors.py
sources="fpga/rtl/relay_bp_round_div16.sv fpga/rtl/relay_bp_sat18.sv fpga/rtl/relay_bp_bias18.sv fpga/rtl/relay_bp_four_bank_ram.sv fpga/rtl/relay_bp_packed_sync_ram.sv fpga/rtl/relay_bp_memory_fabric_p4.sv fpga/rtl/relay_bp_check_controller_p4.sv fpga/rtl/relay_bp_variable_controller_p4.sv fpga/rtl/relay_bp_convergence_controller_p4.sv fpga/rtl/relay_bp_relay_init_controller_p4.sv fpga/rtl/relay_bp_single_engine_memory_p4.sv fpga/testbench/relay_bp_deterministic_gamma_source.sv fpga/testbench/tb_relay_bp_single_engine_memory_p4.sv"
# shellcheck disable=SC2086
iverilog -g2012 -DRELAY_BP_SIM_ASSERT -Ptb_relay_bp_single_engine_memory_p4.TB_STALL_PERIOD=0 -s tb_relay_bp_single_engine_memory_p4 -o /tmp/relay_bp_engine_nostall.vvp $sources
vvp /tmp/relay_bp_engine_nostall.vvp
# shellcheck disable=SC2086
iverilog -g2012 -DRELAY_BP_SIM_ASSERT -Ptb_relay_bp_single_engine_memory_p4.TB_STALL_PERIOD=7 -s tb_relay_bp_single_engine_memory_p4 -o /tmp/relay_bp_engine_stall.vvp $sources
vvp /tmp/relay_bp_engine_stall.vvp
sh fpga/verification/memory_backed_relay_init/run_relay_init_verification.sh

#!/bin/sh
set -eu
python3 fpga/verification/memory_backed_engine/generate_engine_vectors.py
src="fpga/rtl/relay_bp_round_div16.sv fpga/rtl/relay_bp_sat18.sv fpga/rtl/relay_bp_bias18.sv fpga/rtl/relay_bp_four_bank_ram.sv fpga/rtl/relay_bp_packed_sync_ram.sv fpga/rtl/relay_bp_memory_fabric_p4.sv fpga/rtl/relay_bp_check_controller_p4.sv fpga/rtl/relay_bp_variable_controller_p4.sv fpga/rtl/relay_bp_convergence_controller_p4.sv fpga/rtl/relay_bp_relay_init_controller_p4.sv fpga/rtl/relay_bp_single_engine_memory_p4.sv fpga/testbench/relay_bp_deterministic_gamma_source.sv fpga/testbench/tb_relay_bp_engine_cancellation_p4.sv"
for target in 1 2 3 4 5 12 13 14;do
  iverilog -g2012 -DRELAY_BP_SIM_ASSERT -Ptb_relay_bp_engine_cancellation_p4.TARGET=$target -s tb_relay_bp_engine_cancellation_p4 -o /tmp/relay_bp_cancel_phase.vvp $src
  vvp /tmp/relay_bp_cancel_phase.vvp
done

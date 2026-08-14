#!/bin/sh
set -eu
python3 fpga/verification/memory_backed_engine/generate_engine_vectors.py
python3 fpga/verification/parallel_n2/generate_rng_decoder_oracle.py
src="fpga/rtl/relay_bp_gamma_rng.sv fpga/rtl/relay_bp_round_div16.sv fpga/rtl/relay_bp_sat18.sv fpga/rtl/relay_bp_bias18.sv fpga/rtl/relay_bp_four_bank_ram.sv fpga/rtl/relay_bp_packed_sync_ram.sv fpga/rtl/relay_bp_memory_fabric_p4.sv fpga/rtl/relay_bp_check_controller_p4.sv fpga/rtl/relay_bp_variable_controller_p4.sv fpga/rtl/relay_bp_convergence_controller_p4.sv fpga/rtl/relay_bp_relay_init_controller_p4.sv fpga/rtl/relay_bp_single_engine_memory_p4.sv fpga/rtl/relay_bp_first_success_arbiter_n2.sv fpga/rtl/relay_bp_parallel_n2_p4.sv fpga/testbench/tb_relay_bp_parallel_n2_rng_p4.sv"
for cancel in 0 1;do
  iverilog -g2012 -DRELAY_BP_SIM_ASSERT -Ptb_relay_bp_parallel_n2_rng_p4.CANCEL=$cancel -s tb_relay_bp_parallel_n2_rng_p4 -o /tmp/relay_bp_n2_rng.vvp $src
  vvp /tmp/relay_bp_n2_rng.vvp
done

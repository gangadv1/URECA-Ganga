#!/bin/sh
set -eu
for tb in tb_relay_bp_gamma_rng_independence tb_relay_bp_gamma_rng_tier2_dual;do
  iverilog -g2012 -DRELAY_BP_SIM_ASSERT -s $tb -o /tmp/$tb.vvp fpga/rtl/relay_bp_gamma_rng.sv fpga/testbench/$tb.sv
  vvp /tmp/$tb.vvp
done

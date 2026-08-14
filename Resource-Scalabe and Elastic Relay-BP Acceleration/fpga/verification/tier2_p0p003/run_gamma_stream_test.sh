#!/bin/sh
set -eu
iverilog -g2012 -s tb_relay_bp_tier2_gamma_stream -o /tmp/relay_bp_tier2_gamma_stream.vvp \
 fpga/testbench/relay_bp_deterministic_gamma_source.sv fpga/testbench/tb_relay_bp_tier2_gamma_stream.sv
vvp /tmp/relay_bp_tier2_gamma_stream.vvp

#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
RTL="$ROOT/fpga/rtl/m4_memory_fabric"; TB="$ROOT/fpga/testbench/m4_memory_fabric"; RES="$ROOT/results/m4-memory-fabric-rtl"; TMP="${TMPDIR:-/tmp}/m4_memory_fabric_test"
mkdir -p "$RES" "$TMP"
python3 "$TB/generate_stress_vectors.py"
python3 "$TB/replay_cycle_trace.py"
cp "$TB/stress_vectors.txt" "$TMP/stress_vectors.txt"
cp "$TB/template_vectors.txt" "$TMP/template_vectors.txt"
for L in 1 2; do
  iverilog -g2012 -s tb_m4_memory_fabric -Ptb_m4_memory_fabric.READ_LATENCY=$L -o "$TMP/fabric_l$L.vvp" "$RTL"/*.sv "$TB/tb_m4_memory_fabric.sv"
  vvp "$TMP/fabric_l$L.vvp" +VECTORS="$TMP/stress_vectors.txt" +TRACE="$TMP/trace_l$L.csv" > "$RES/fabric_l$L.log"
  cp "$TMP/trace_l$L.csv" "$RES/trace_l$L.csv"
  vvp "$TMP/fabric_l$L.vvp" +VECTORS="$TMP/template_vectors.txt" +TRACE="$TMP/template_l$L.csv" > "$RES/template_l$L.log"
  cp "$TMP/template_l$L.csv" "$RES/template_l$L.csv"
  iverilog -g2012 -s tb_m4_message_alias -Ptb_m4_message_alias.READ_LATENCY=$L -o "$TMP/alias_l$L.vvp" "$RTL"/*.sv "$TB/tb_m4_message_alias.sv"
  vvp "$TMP/alias_l$L.vvp" > "$RES/alias_l$L.log"
done

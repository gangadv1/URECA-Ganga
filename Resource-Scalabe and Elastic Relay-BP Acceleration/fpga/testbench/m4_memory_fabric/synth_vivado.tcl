# Prepared standalone inference run. No device or clock is guessed.
if {![info exists ::env(TARGET_PART)] || $::env(TARGET_PART) eq ""} {
  error "TARGET FPGA REQUIRED: set TARGET_PART to the exact complete Vivado part string"
}
if {![info exists ::env(CLOCK_PERIOD_NS)] || $::env(CLOCK_PERIOD_NS) eq ""} {
  error "CLOCK CONSTRAINT REQUIRED: set CLOCK_PERIOD_NS"
}
set part $::env(TARGET_PART)
set period $::env(CLOCK_PERIOD_NS)
read_verilog -sv [glob fpga/rtl/m4_memory_fabric/*.sv]
synth_design -mode out_of_context -top m4_shared_tdp_bank -part $part -generic WIDTH=18 -generic DEPTH=97830 -generic READ_LATENCY=1
create_clock -name clk -period $period [get_ports clk]
report_utilization -file results/m4-memory-fabric-synthesis/reports/vivado_shared_tdp_utilization.rpt
report_timing_summary -file results/m4-memory-fabric-synthesis/reports/vivado_shared_tdp_timing.rpt
report_drc -file results/m4-memory-fabric-synthesis/reports/vivado_shared_tdp_drc.rpt

# Vivado out-of-context M4 memory-class matrix. Requires exact project inputs.
if {![info exists ::env(TARGET_PART)] || $::env(TARGET_PART) eq ""} {error "TARGET FPGA REQUIRED"}
if {![info exists ::env(CLOCK_PERIOD_NS)] || $::env(CLOCK_PERIOD_NS) eq ""} {error "CLOCK CONSTRAINT REQUIRED"}
set part $::env(TARGET_PART);set period $::env(CLOCK_PERIOD_NS)
set root [file normalize [pwd]];set rtl "$root/fpga/rtl/m4_memory_fabric";set out "$root/results/m4-memory-fabric-synthesis/reports";file mkdir $out
set jobs {
  {shared_edge_to_fault m4_shared_tdp_bank WIDTH=17 DEPTH=97830 READ_LATENCY=1}
  {shared_fault_to_edge m4_shared_tdp_bank WIDTH=19 DEPTH=97830 READ_LATENCY=1}
  {shared_check_degree m4_shared_tdp_bank WIDTH=8 DEPTH=432 READ_LATENCY=1}
  {shared_fault_degree m4_shared_tdp_bank WIDTH=4 DEPTH=16938 READ_LATENCY=1}
  {shared_prior m4_shared_tdp_bank WIDTH=18 DEPTH=16938 READ_LATENCY=1}
  {shared_syndrome m4_shared_tdp_bank WIDTH=1 DEPTH=432 READ_LATENCY=1}
  {private_message m4_message_ram WIDTH=18 DEPTH=97830 READ_LATENCY=1}
  {private_marginal m4_private_bank WIDTH=18 DEPTH=16938 READ_LATENCY=1}
  {private_gamma m4_private_bank WIDTH=5 DEPTH=16938 READ_LATENCY=1}
  {private_decision m4_private_bank WIDTH=1 DEPTH=16938 READ_LATENCY=1}
}
read_verilog -sv [glob "$rtl/*.sv"]
foreach job $jobs {
  lassign $job name top g0 g1 g2
  synth_design -mode out_of_context -top $top -part $part -generic $g0 -generic $g1 -generic $g2
  create_clock -name clk -period $period [get_ports clk]
  report_utilization -file "$out/${name}_utilization.rpt"
  report_timing_summary -file "$out/${name}_timing.rpt"
  report_drc -file "$out/${name}_drc.rpt"
  write_checkpoint -force "$out/${name}.dcp"
  close_design
}

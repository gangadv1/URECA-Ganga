`timescale 1ns/1ps
// End-to-end tier-1 graph smoke test using generated gross-code edge maps.
module tb_relay_bp_gross_tier1;
  import gross_code_tier1_graph_pkg::*;
  logic clk = 0, rst = 1, start = 0;
  logic [CHECKS-1:0] syndrome = '0;
  logic signed [3:0] prior [VARIABLES];
  logic [3:0] gamma_int = 0, beta_int = 4;
  logic busy, done, converged;
  logic [VARIABLES-1:0] decoded_error;
  logic [1:0] iterations;
  logic legs;
  logic trace_valid, trace_is_check;
  logic [31:0] trace_node, active_cycles;
  integer variable_index;
  always #5 clk = ~clk;

  relay_bp_gross_tier1_top #(.B(4), .M_SHIFT(3), .MAX_ITERATIONS(2), .MAX_LEGS(1)) dut (.*);

  initial begin
    for (variable_index = 0; variable_index < VARIABLES; variable_index++) prior[variable_index] = 3;
    repeat (2) @(posedge clk); #1 rst = 0; start = 1;
    @(posedge clk); #1 start = 0;
    wait(done); #1;
    if (!converged || decoded_error != '0 || iterations != 1)
      $fatal(1, "tier-1 gross-code decode mismatch");
    if (active_cycles != CHECKS + VARIABLES + 1)
      $fatal(1, "unexpected folded cycle count: %0d", active_cycles);
    $display("tier-1 gross-code full-graph test passed in %0d cycles", active_cycles);
    $finish;
  end
endmodule

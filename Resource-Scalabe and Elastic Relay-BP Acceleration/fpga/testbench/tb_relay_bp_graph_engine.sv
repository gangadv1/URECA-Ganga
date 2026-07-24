`timescale 1ns/1ps
// Small full-graph smoke test. Generated tier-1 edge maps use the same engine.
module tb_relay_bp_graph_engine;
  logic clk = 0, rst = 1, start = 0;
  logic [1:0] syndrome = '0;
  logic signed [3:0] prior [3];
  logic [3:0] gamma_int = 0, beta_int = 4;
  logic [2:0] check_of_edge = 3'b000;
  logic [5:0] variable_of_edge = 6'b10_01_00;
  logic busy, done, converged;
  logic [2:0] decoded_error;
  logic [1:0] iterations;
  logic legs;
  logic trace_valid, trace_is_check;
  logic [31:0] trace_node, active_cycles;
  always #5 clk = ~clk;

  relay_bp_graph_engine #(
    .CHECKS(2), .VARIABLES(3), .EDGES(3), .B(4), .M_SHIFT(3), .CLIP(7),
    .MAX_ITERATIONS(2), .MAX_LEGS(1)
  ) dut (.*);

  initial begin
    prior[0] = 3; prior[1] = 3; prior[2] = 3;
    repeat (2) @(posedge clk); #1 rst = 0; start = 1;
    @(posedge clk); #1 start = 0;
    wait(done); #1;
    if (!converged || decoded_error != '0 || iterations != 1)
      $fatal(1, "full-graph smoke test failed");
    $display("relay_bp_graph_engine smoke test passed in %0d cycles", active_cycles);
    $finish;
  end
endmodule

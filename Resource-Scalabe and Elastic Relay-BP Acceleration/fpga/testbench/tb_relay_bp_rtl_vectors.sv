`timescale 1ns/1ps

module tb_relay_bp_rtl_vectors;
  import gross_code_tier1_graph_pkg::*;

  localparam int B = 4;
  localparam int CASES_TO_TEST = (rtl_vectors_pkg::CASE_COUNT < 4) ? rtl_vectors_pkg::CASE_COUNT : 4;

  logic clk = 0;
  logic rst = 1;
  logic start = 0;
  logic [CHECKS-1:0] syndrome;
  logic signed [3:0] prior [VARIABLES];
  logic [3:0] gamma_int = 0;
  logic [3:0] beta_int = 4;
  logic busy, done, converged;
  logic [VARIABLES-1:0] decoded_error;
  logic [$clog2(7)-1:0] iterations;
  logic [$clog2(3)-1:0] legs;
  logic [CHECKS-1:0] residual_syndrome;
  logic trace_valid, trace_is_check;
  logic [31:0] trace_node, active_cycles;

  relay_bp_golden_tier1_top #(.B(4), .M_SHIFT(3), .MAX_ITERATIONS_PER_LEG(3), .MAX_LEGS(2)) dut (.*);

  always #5 clk = ~clk;

  task automatic load_prior(input int case_index);
    int index;
    begin
      for (index = 0; index < VARIABLES; index++) begin
        prior[index] = rtl_vectors_pkg::prior_word_case(case_index, index);
      end
    end
  endtask

  function automatic logic [CHECKS-1:0] compute_residual(
      input logic [CHECKS-1:0] syn,
      input logic [VARIABLES-1:0] decision);
    int edge_index;
    logic [CHECKS-1:0] residual;
    int check_index;
    int variable_index;
    begin
      residual = syn;
      for (edge_index = 0; edge_index < EDGES; edge_index++) begin
        check_index = check_of_edge(edge_index);
        variable_index = variable_of_edge(edge_index);
        residual[check_index] = residual[check_index] ^ decision[variable_index];
      end
      compute_residual = residual;
    end
  endfunction

  task automatic run_case(input int case_index);
    logic [CHECKS-1:0] expected_syndrome;
    logic [CHECKS-1:0] expected_residual;
    logic [VARIABLES-1:0] expected_decision;
    int expected_converged;
    int expected_iterations;
    int expected_legs;
    begin
      expected_syndrome = rtl_vectors_pkg::syndrome_case(case_index);
      expected_decision = rtl_vectors_pkg::decided_case(case_index);
      expected_residual = rtl_vectors_pkg::residual_case(case_index);
      expected_converged = rtl_vectors_pkg::converged_case(case_index);
      expected_iterations = rtl_vectors_pkg::iterations_case(case_index);
      expected_legs = rtl_vectors_pkg::legs_case(case_index);

      syndrome = expected_syndrome;
      load_prior(case_index);
      repeat (2) @(posedge clk);
      #1 rst = 0;
      start = 1;
      @(posedge clk);
      #1 start = 0;
      wait(done);
      #1;

      if (decoded_error !== expected_decision) begin
        $fatal(1, "case %0d decoded_error mismatch", case_index);
      end
      if (residual_syndrome !== expected_residual) begin
        $fatal(1, "case %0d residual mismatch", case_index);
      end
      if (converged !== expected_converged[0]) begin
        $fatal(1, "case %0d converged mismatch", case_index);
      end
      if (iterations !== expected_iterations) begin
        $fatal(1, "case %0d iteration mismatch", case_index);
      end
      if (legs !== expected_legs) begin
        $fatal(1, "case %0d leg mismatch", case_index);
      end

      $display("case %0d passed: converged=%0d iterations=%0d legs=%0d", case_index, converged, iterations, legs);
      rst = 1;
      start = 0;
      repeat (2) @(posedge clk);
    end
  endtask

  initial begin
    int case_index;
    syndrome = '0;
    for (case_index = 0; case_index < CASES_TO_TEST; case_index++) begin
      run_case(case_index);
    end
    $display("RTL vector smoke test passed for %0d cases", CASES_TO_TEST);
    $finish;
  end
endmodule

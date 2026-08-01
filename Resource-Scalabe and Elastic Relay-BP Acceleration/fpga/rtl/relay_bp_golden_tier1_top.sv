// Tier-1 top-level for the new golden Relay-BP RTL path.
// This wrapper binds the generated graph package and presents the explicit
// output set required by the Prompt 3/4 vector flow.
module relay_bp_golden_tier1_top #(
  parameter int B = 4,
  parameter int M_SHIFT = 3,
  parameter int CLIP = (1 << (B - 1)) - 1,
  parameter int MAX_ITERATIONS_PER_LEG = 3,
  parameter int MAX_LEGS = 2
) (
  input  logic clk,
  input  logic rst,
  input  logic start,
  input  logic [gross_code_tier1_graph_pkg::CHECKS-1:0] syndrome,
  input  logic signed [B-1:0] prior [gross_code_tier1_graph_pkg::VARIABLES],
  input  logic [M_SHIFT:0] gamma_int,
  input  logic [M_SHIFT:0] beta_int,
  output logic busy,
  output logic done,
  output logic converged,
  output logic [gross_code_tier1_graph_pkg::VARIABLES-1:0] decoded_error,
  output logic [gross_code_tier1_graph_pkg::CHECKS-1:0] residual_syndrome,
  output logic [$clog2(MAX_ITERATIONS_PER_LEG*MAX_LEGS+1)-1:0] iterations,
  output logic [$clog2(MAX_LEGS+1)-1:0] legs,
  output logic trace_valid,
  output logic trace_is_check,
  output logic [31:0] trace_node,
  output logic [31:0] active_cycles
);
  localparam int CHECK_W = (gross_code_tier1_graph_pkg::CHECKS <= 1) ? 1 : $clog2(gross_code_tier1_graph_pkg::CHECKS);
  localparam int VARIABLE_W = (gross_code_tier1_graph_pkg::VARIABLES <= 1) ? 1 : $clog2(gross_code_tier1_graph_pkg::VARIABLES);
  logic [gross_code_tier1_graph_pkg::EDGES*CHECK_W-1:0] check_of_edge;
  logic [gross_code_tier1_graph_pkg::EDGES*VARIABLE_W-1:0] variable_of_edge;
  genvar edge_index;
  generate
    for (edge_index = 0; edge_index < gross_code_tier1_graph_pkg::EDGES; edge_index++) begin : MAPS
      assign check_of_edge[edge_index*CHECK_W +: CHECK_W] = gross_code_tier1_graph_pkg::check_of_edge(edge_index);
      assign variable_of_edge[edge_index*VARIABLE_W +: VARIABLE_W] = gross_code_tier1_graph_pkg::variable_of_edge(edge_index);
    end
  endgenerate

  relay_bp_golden_engine #(
    .CHECKS(gross_code_tier1_graph_pkg::CHECKS),
    .VARIABLES(gross_code_tier1_graph_pkg::VARIABLES),
    .EDGES(gross_code_tier1_graph_pkg::EDGES),
    .B(B),
    .M_SHIFT(M_SHIFT),
    .CLIP(CLIP),
    .MAX_ITERATIONS_PER_LEG(MAX_ITERATIONS_PER_LEG),
    .MAX_LEGS(MAX_LEGS)
  ) engine (
    .clk(clk),
    .rst(rst),
    .start(start),
    .syndrome(syndrome),
    .prior(prior),
    .gamma_int(gamma_int),
    .beta_int(beta_int),
    .check_of_edge(check_of_edge),
    .variable_of_edge(variable_of_edge),
    .busy(busy),
    .done(done),
    .converged(converged),
    .decoded_error(decoded_error),
    .residual_syndrome(residual_syndrome),
    .iterations(iterations),
    .legs(legs),
    .trace_valid(trace_valid),
    .trace_is_check(trace_is_check),
    .trace_node(trace_node),
    .active_cycles(active_cycles)
  );
endmodule

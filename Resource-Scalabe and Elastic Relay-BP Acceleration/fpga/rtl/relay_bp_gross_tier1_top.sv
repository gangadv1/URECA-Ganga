// Tier-1 integration wrapper. Compile the generated graph package before this
// file: graphs/generated/gross_code_capacity/schedule_pc8_pv8/gross_code_tier1_graph_pkg.sv
module relay_bp_gross_tier1_top #(
  parameter int B = 8,
  parameter int M_SHIFT = 3,
  parameter int CLIP = (1 << (B - 1)) - 1,
  parameter int MAX_ITERATIONS = 3,
  parameter int MAX_LEGS = 1
) (
  input logic clk, rst, start,
  input logic [gross_code_tier1_graph_pkg::CHECKS-1:0] syndrome,
  input logic signed [B-1:0] prior [gross_code_tier1_graph_pkg::VARIABLES],
  input logic [M_SHIFT:0] gamma_int, beta_int,
  output logic busy, done, converged,
  output logic [gross_code_tier1_graph_pkg::VARIABLES-1:0] decoded_error,
  output logic [$clog2(MAX_ITERATIONS+1)-1:0] iterations,
  output logic [$clog2(MAX_LEGS+1)-1:0] legs,
  output logic trace_valid, trace_is_check,
  output logic [31:0] trace_node, active_cycles
);
  localparam int CHECK_W = $clog2(gross_code_tier1_graph_pkg::CHECKS);
  localparam int VARIABLE_W = $clog2(gross_code_tier1_graph_pkg::VARIABLES);
  logic [gross_code_tier1_graph_pkg::EDGES*CHECK_W-1:0] check_of_edge;
  logic [gross_code_tier1_graph_pkg::EDGES*VARIABLE_W-1:0] variable_of_edge;
  genvar edge_index;
  generate for (edge_index = 0; edge_index < gross_code_tier1_graph_pkg::EDGES; edge_index++) begin : MAPS
    assign check_of_edge[edge_index*CHECK_W +: CHECK_W] = gross_code_tier1_graph_pkg::check_of_edge(edge_index);
    assign variable_of_edge[edge_index*VARIABLE_W +: VARIABLE_W] = gross_code_tier1_graph_pkg::variable_of_edge(edge_index);
  end endgenerate
  relay_bp_graph_engine #(
    .CHECKS(gross_code_tier1_graph_pkg::CHECKS),
    .VARIABLES(gross_code_tier1_graph_pkg::VARIABLES),
    .EDGES(gross_code_tier1_graph_pkg::EDGES), .B(B), .M_SHIFT(M_SHIFT), .CLIP(CLIP),
    .MAX_ITERATIONS(MAX_ITERATIONS), .MAX_LEGS(MAX_LEGS)
  ) engine (.*);
endmodule

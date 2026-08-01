// Deterministic schedule ROM wrapper around the generated gross-code package.
module relay_bp_schedule_rom #(
  parameter int EDGES = gross_code_tier1_graph_pkg::EDGES,
  parameter int CHECKS = gross_code_tier1_graph_pkg::CHECKS,
  parameter int VARIABLES = gross_code_tier1_graph_pkg::VARIABLES
) (
  input  logic [$clog2((EDGES <= 1) ? 1 : EDGES)-1:0] edge_index,
  output logic [$clog2((CHECKS <= 1) ? 1 : CHECKS)-1:0] check_of_edge,
  output logic [$clog2((VARIABLES <= 1) ? 1 : VARIABLES)-1:0] variable_of_edge
);
  always_comb begin
    check_of_edge = gross_code_tier1_graph_pkg::check_of_edge(edge_index);
    variable_of_edge = gross_code_tier1_graph_pkg::variable_of_edge(edge_index);
  end
endmodule

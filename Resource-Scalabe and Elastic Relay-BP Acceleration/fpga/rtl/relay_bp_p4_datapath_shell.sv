// Structural primitive foundation only. Graph traversal, memories, and FSM are external.
module relay_bp_p4_datapath_shell #(
  parameter int P = 4,
  parameter int MAX_CHECK_DEGREE = 242,
  parameter int MAX_VARIABLE_DEGREE = 9,
  parameter int CHECK_INDEX_W = (MAX_CHECK_DEGREE <= 1) ? 1 : $clog2(MAX_CHECK_DEGREE),
  parameter int CHECK_DEGREE_W = $clog2(MAX_CHECK_DEGREE + 1)
) (
  input  logic [CHECK_DEGREE_W-1:0] check_degree [0:P-1],
  input  logic [P-1:0] check_syndrome,
  input  logic signed [17:0] check_nu [0:P-1][0:MAX_CHECK_DEGREE-1],
  output logic signed [17:0] check_mu [0:P-1][0:MAX_CHECK_DEGREE-1],
  input  logic [3:0] variable_degree [0:P-1],
  input  logic signed [17:0] variable_prior [0:P-1],
  input  logic signed [17:0] variable_previous_marginal [0:P-1],
  input  logic signed [4:0] variable_gamma [0:P-1],
  input  logic signed [17:0] variable_mu [0:P-1][0:MAX_VARIABLE_DEGREE-1],
  output logic signed [17:0] variable_bias [0:P-1],
  output logic signed [21:0] variable_sum [0:P-1],
  output logic signed [17:0] variable_marginal [0:P-1],
  output logic [P-1:0] variable_decision,
  output logic signed [17:0] variable_nu [0:P-1][0:MAX_VARIABLE_DEGREE-1],
  output logic signed [17:0] variable_weight [0:P-1]
);
  genvar lane;
  genvar check_edge;
  genvar variable_edge;
  generate for (lane=0; lane<P; lane=lane+1) begin : g_lane
    wire signed [17:0] local_check_nu [0:MAX_CHECK_DEGREE-1];
    wire signed [17:0] local_check_mu [0:MAX_CHECK_DEGREE-1];
    wire signed [17:0] local_variable_mu [0:MAX_VARIABLE_DEGREE-1];
    wire signed [17:0] local_variable_nu [0:MAX_VARIABLE_DEGREE-1];
    logic [18:0] min1, min2;
    logic [CHECK_INDEX_W-1:0] min1_index;
    logic negative_parity, accumulator_saturated, bias_saturated, marginal_saturated;
    logic [MAX_VARIABLE_DEGREE-1:0] nu_saturated;
    for (check_edge=0; check_edge<MAX_CHECK_DEGREE; check_edge=check_edge+1) begin : g_check_edge
      assign local_check_nu[check_edge] = check_nu[lane][check_edge];
      assign check_mu[lane][check_edge] = local_check_mu[check_edge];
    end
    for (variable_edge=0; variable_edge<MAX_VARIABLE_DEGREE; variable_edge=variable_edge+1) begin : g_variable_edge
      assign local_variable_mu[variable_edge] = variable_mu[lane][variable_edge];
      assign variable_nu[lane][variable_edge] = local_variable_nu[variable_edge];
    end
    relay_bp_check_min2_18 #(.MAX_DEGREE(MAX_CHECK_DEGREE), .INDEX_W(CHECK_INDEX_W),
                              .DEGREE_W(CHECK_DEGREE_W)) check_unit(
      .degree(check_degree[lane]), .syndrome_bit(check_syndrome[lane]), .nu_in(local_check_nu),
      .mu_out(local_check_mu), .min1, .min2, .min1_index, .negative_parity);
    relay_bp_variable_node_18 #(.MAX_DEGREE(MAX_VARIABLE_DEGREE)) variable_unit(
      .degree(variable_degree[lane]), .physical_prior(variable_prior[lane]),
      .previous_marginal(variable_previous_marginal[lane]), .gamma_q(variable_gamma[lane]),
      .mu_in(local_variable_mu), .bias(variable_bias[lane]), .incoming_sum(variable_sum[lane]),
      .accumulator_saturated, .marginal(variable_marginal[lane]),
      .hard_decision(variable_decision[lane]), .nu_out(local_variable_nu),
      .weight_contribution(variable_weight[lane]), .bias_saturated, .marginal_saturated, .nu_saturated);
  end endgenerate
endmodule

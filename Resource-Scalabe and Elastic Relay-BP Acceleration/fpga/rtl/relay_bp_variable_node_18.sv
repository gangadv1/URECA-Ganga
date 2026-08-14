module relay_bp_variable_node_18 #(
  parameter int MAX_DEGREE = 9
) (
  input  logic [3:0] degree,
  input  logic signed [17:0] physical_prior,
  input  logic signed [17:0] previous_marginal,
  input  logic signed [4:0] gamma_q,
  input  logic signed [17:0] mu_in [0:MAX_DEGREE-1],
  output logic signed [17:0] bias,
  output logic signed [21:0] incoming_sum,
  output logic accumulator_saturated,
  output logic signed [17:0] marginal,
  output logic hard_decision,
  output logic signed [17:0] nu_out [0:MAX_DEGREE-1],
  output logic signed [17:0] weight_contribution,
  output logic bias_saturated,
  output logic marginal_saturated,
  output logic [MAX_DEGREE-1:0] nu_saturated
);
  integer k;
  logic signed [22:0] sum_wide;
  logic signed [22:0] marginal_wide;
  logic signed [18:0] nu_wide [0:MAX_DEGREE-1];
  logic unused_sat;
  relay_bp_bias18 bias_unit(.physical_prior, .previous_marginal, .gamma_q,
                            .bias, .saturated(bias_saturated));
  always_comb begin
    sum_wide = '0;
    for (k = 0; k < MAX_DEGREE; k++) if (k < degree) sum_wide = sum_wide + $signed(mu_in[k]);
    accumulator_saturated = 1'b0;
    if (sum_wide > 23'sd2097151) begin incoming_sum = 22'sd2097151; accumulator_saturated = 1'b1; end
    else if (sum_wide < -23'sd2097152) begin incoming_sum = -22'sd2097152; accumulator_saturated = 1'b1; end
    else incoming_sum = sum_wide[21:0];
    marginal_wide = $signed(incoming_sum) + $signed(bias);
    hard_decision = (marginal <= 0);
    weight_contribution = hard_decision ? physical_prior : 18'sd0;
    for (k = 0; k < MAX_DEGREE; k++) begin
      nu_wide[k] = $signed(marginal) - $signed(mu_in[k]);
      nu_out[k] = '0; nu_saturated[k] = 1'b0;
      if (k < degree) begin
        if (nu_wide[k] > 19'sd131071) begin nu_out[k] = 18'sd131071; nu_saturated[k] = 1'b1; end
        else if (nu_wide[k] < -19'sd131072) begin nu_out[k] = -18'sd131072; nu_saturated[k] = 1'b1; end
        else nu_out[k] = nu_wide[k][17:0];
      end
    end
  end
  relay_bp_sat18 #(.IN_W(23)) marginal_limiter(
    .value_in(marginal_wide), .value_out(marginal), .saturated(marginal_saturated));
endmodule

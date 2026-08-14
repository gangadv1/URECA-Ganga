module relay_bp_bias18 (
  input  logic signed [17:0] physical_prior,
  input  logic signed [17:0] previous_marginal,
  input  logic signed [4:0] gamma_q,
  output logic signed [17:0] bias,
  output logic saturated
);
  logic signed [18:0] difference;
  logic signed [23:0] product;
  logic signed [24:0] numerator;
  logic signed [24:0] rounded;
  always_comb begin
    difference = $signed(previous_marginal) - $signed(physical_prior);
    product = $signed(difference) * $signed(gamma_q);
    numerator = ($signed(physical_prior) <<< 4) + $signed(product);
  end
  relay_bp_round_div16 #(.W(25)) rounder(.numerator(numerator), .quotient(rounded));
  relay_bp_sat18 #(.IN_W(25)) limiter(.value_in(rounded), .value_out(bias), .saturated(saturated));
endmodule

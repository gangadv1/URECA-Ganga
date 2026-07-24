// One variable-node operation with explicit widened sum and saturation.
module variable_node_tile #(
  parameter int B = 8,
  parameter int MAX_DEGREE = 16,
  parameter int CLIP = (1 << (B - 1)) - 1
) (
  input  logic [MAX_DEGREE-1:0] valid,
  input  logic [$clog2(MAX_DEGREE+1)-1:0] degree,
  input  logic signed [B-1:0] prior,
  input  logic signed [B-1:0] relay_term,
  input  logic signed [B-1:0] incoming [MAX_DEGREE],
  output logic signed [B-1:0] belief,
  output logic signed [B-1:0] outgoing [MAX_DEGREE],
  output logic hard_decision
);
  import fixedpoint_relay_pkg::*;
  integer i;
  longint signed sum_value;
  always_comb begin
    sum_value = $signed(prior) + $signed(relay_term);
    for (i = 0; i < MAX_DEGREE; i++)
      if (valid[i] && i < degree) sum_value = sum_value + $signed(incoming[i]);
    belief = saturate_signed(sum_value, B, CLIP);
    hard_decision = belief < 0;
    for (i = 0; i < MAX_DEGREE; i++) begin
      outgoing[i] = '0;
      if (valid[i] && i < degree)
        outgoing[i] = saturate_signed($signed(belief) - $signed(incoming[i]), B, CLIP);
    end
  end
endmodule

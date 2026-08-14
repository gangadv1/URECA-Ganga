module relay_bp_sat18 #(
  parameter int IN_W = 25
) (
  input  logic signed [IN_W-1:0] value_in,
  output logic signed [17:0] value_out,
  output logic saturated
);
  localparam logic signed [IN_W-1:0] MAX18 = 131071;
  localparam logic signed [IN_W-1:0] MIN18 = -131072;
  always_comb begin
    saturated = 1'b0;
    if (value_in > MAX18) begin value_out = 18'sd131071; saturated = 1'b1; end
    else if (value_in < MIN18) begin value_out = -18'sd131072; saturated = 1'b1; end
    else value_out = value_in[17:0];
  end
endmodule

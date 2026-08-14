module relay_bp_round_div16 #(
  parameter int W = 25
) (
  input  logic signed [W-1:0] numerator,
  output logic signed [W-1:0] quotient
);
  logic signed [W:0] wide;
  logic [W:0] magnitude;
  always_comb begin
    wide = numerator;
    magnitude = (wide < 0) ? -wide : wide;
    magnitude = (magnitude + 8) >> 4;
    quotient = (wide < 0) ? -$signed(magnitude) : $signed(magnitude);
  end
endmodule

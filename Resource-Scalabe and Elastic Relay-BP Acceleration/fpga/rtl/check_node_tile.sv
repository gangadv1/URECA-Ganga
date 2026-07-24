// One exact min-sum check-node operation.  The controller reuses this tile
// across graph checks; unused lanes are ignored by `degree`.
module check_node_tile #(
  parameter int B = 8,
  parameter int MAX_DEGREE = 16,
  parameter int CLIP = (1 << (B - 1)) - 1
) (
  input  logic [MAX_DEGREE-1:0] valid,
  input  logic [$clog2(MAX_DEGREE+1)-1:0] degree,
  input  logic syndrome_bit,
  input  logic signed [B-1:0] incoming [MAX_DEGREE],
  output logic signed [B-1:0] outgoing [MAX_DEGREE]
);
  import fixedpoint_relay_pkg::*;
  integer i, j;
  longint signed sign_value, magnitude, minimum;
  always_comb begin
    for (i = 0; i < MAX_DEGREE; i++) begin
      outgoing[i] = '0;
      if (valid[i] && i < degree) begin
        sign_value = syndrome_bit ? -1 : 1;
        minimum = CLIP;
        for (j = 0; j < MAX_DEGREE; j++) begin
          if (valid[j] && j < degree && j != i) begin
            if (incoming[j] < 0) sign_value = -sign_value;
            magnitude = incoming[j] < 0 ? -$signed(incoming[j]) : $signed(incoming[j]);
            if (magnitude < minimum) minimum = magnitude;
          end
        end
        // A degree-one check has no other incoming message, matching Python.
        if (degree > 1) outgoing[i] = saturate_signed(sign_value * minimum, B, CLIP);
      end
    end
  end
endmodule

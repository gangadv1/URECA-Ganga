module relay_bp_check_min2_18 #(
  parameter int MAX_DEGREE = 16,
  parameter int INDEX_W = (MAX_DEGREE <= 1) ? 1 : $clog2(MAX_DEGREE),
  parameter int DEGREE_W = $clog2(MAX_DEGREE + 1)
) (
  input  logic [DEGREE_W-1:0] degree,
  input  logic syndrome_bit,
  input  logic signed [17:0] nu_in [0:MAX_DEGREE-1],
  output logic signed [17:0] mu_out [0:MAX_DEGREE-1],
  output logic [18:0] min1,
  output logic [18:0] min2,
  output logic [INDEX_W-1:0] min1_index,
  output logic negative_parity
);
  integer k;
  logic [18:0] magnitude;
  logic [18:0] selected_magnitude;
  logic outgoing_negative;
  always_comb begin
    min1 = 19'h3ffff;
    min2 = 19'h3ffff;
    min1_index = '0;
    negative_parity = 1'b0;
    for (k = 0; k < MAX_DEGREE; k++) begin
      if (k < degree) begin
        magnitude = nu_in[k][17] ? -$signed({nu_in[k][17], nu_in[k]}) : $signed({1'b0, nu_in[k]});
        negative_parity = negative_parity ^ nu_in[k][17];
        if (magnitude < min1) begin
          min2 = min1; min1 = magnitude; min1_index = k[INDEX_W-1:0];
        end else if (magnitude < min2) min2 = magnitude;
      end
    end
    for (k = 0; k < MAX_DEGREE; k++) begin
      mu_out[k] = '0;
      if (k < degree) begin
        if (degree == 1) begin
          mu_out[k] = syndrome_bit ? -18'sd131071 : 18'sd131071;
        end else begin
          selected_magnitude = (k[INDEX_W-1:0] == min1_index) ? min2 : min1;
          outgoing_negative = syndrome_bit ^ negative_parity ^ nu_in[k][17];
          if (outgoing_negative)
            mu_out[k] = (selected_magnitude >= 19'd131072) ? -18'sd131072 : -$signed(selected_magnitude[17:0]);
          else
            mu_out[k] = (selected_magnitude > 19'd131071) ? 18'sd131071 : $signed(selected_magnitude[17:0]);
        end
      end
    end
  end
endmodule

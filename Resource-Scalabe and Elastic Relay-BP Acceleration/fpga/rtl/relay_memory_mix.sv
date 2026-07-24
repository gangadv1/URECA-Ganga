module relay_memory_mix #(
  parameter int B = 8,
  parameter int M_SHIFT = 3,
  parameter int CLIP = (1 << (B - 1)) - 1
) (
  input  logic signed [B-1:0] previous_state,
  input  logic signed [B-1:0] new_state,
  input  logic [M_SHIFT:0] beta_int,
  output logic signed [B-1:0] mixed_state,
  output logic saturated
);
  import fixedpoint_relay_pkg::*;
  longint signed raw_result;
  longint signed numerator;
  longint signed beta_value;
  always_comb begin
    beta_value = beta_int;
    numerator = beta_value * $signed(previous_state)
              + ((64'sd1 <<< M_SHIFT) - beta_value) * $signed(new_state);
    raw_result = round_shift_away(numerator, M_SHIFT);
    mixed_state = saturate_signed(raw_result, B, CLIP);
    saturated = raw_result != mixed_state;
  end
endmodule

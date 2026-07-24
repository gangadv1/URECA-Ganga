`timescale 1ns/1ps
module tb_fixedpoint_arithmetic;
  logic signed [3:0] previous_state, new_state, mixed_state;
  logic [3:0] beta_int;
  logic saturated;
  relay_memory_mix #(.B(4), .M_SHIFT(3), .CLIP(7)) dut (
    .previous_state(previous_state), .new_state(new_state), .beta_int(beta_int),
    .mixed_state(mixed_state), .saturated(saturated)
  );
  initial begin
    previous_state = 3; new_state = -5; beta_int = 0; #1;
    if (mixed_state !== -5) $fatal(1, "beta=0 mismatch: %0d", mixed_state);
    beta_int = 8; #1;
    if (mixed_state !== 3) $fatal(1, "beta=M mismatch: %0d", mixed_state);
    beta_int = 4; #1;
    if (mixed_state !== -1) $fatal(1, "middle mix mismatch: %0d", mixed_state);
    $display("fixed-point arithmetic test passed");
    $finish;
  end
endmodule

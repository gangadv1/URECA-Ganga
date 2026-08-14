`timescale 1ns/1ps
module tb_relay_bp_arithmetic18;
  logic signed [24:0] value_in;
  logic signed [17:0] saturated_value;
  logic saturated;
  logic signed [24:0] rounded_value;
  integer fd, count, failed, rc;
  integer value, expected_sat, expected_flag, expected_round;

  relay_bp_sat18 #(.IN_W(25)) sat_dut(
    .value_in(value_in), .value_out(saturated_value), .saturated(saturated));
  relay_bp_round_div16 #(.W(25)) round_dut(
    .numerator(value_in), .quotient(rounded_value));

  initial begin
    count = 0; failed = 0;
    fd = $fopen("fpga/verification/locked_b18/arithmetic_vectors.txt", "r");
    if (!fd) $fatal(1, "cannot open arithmetic vectors");
    while (!$feof(fd)) begin
      rc = $fscanf(fd, "%d %d %d %d\n", value, expected_sat, expected_flag, expected_round);
      if (rc == 4) begin
        value_in = value; #1; count = count + 1;
        if ($signed(saturated_value) !== expected_sat || saturated !== expected_flag[0] ||
            $signed(rounded_value) !== expected_round) begin
          failed = failed + 1;
          $display("ARITH_FAIL vec=%0d input=%0d sat=%0d/%0d flag=%0d/%0d round=%0d/%0d",
                   count, value, $signed(saturated_value), expected_sat, saturated,
                   expected_flag, $signed(rounded_value), expected_round);
        end
      end
    end
    $display("ARITH_RESULT tested=%0d passed=%0d failed=%0d", count, count-failed, failed);
    if (failed) $fatal(1, "arithmetic mismatches");
    $finish;
  end
endmodule

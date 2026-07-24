`timescale 1ns/1ps
module tb_node_tiles;
  logic [2:0] valid = 3'b111;
  logic [1:0] degree = 3;
  logic syndrome_bit = 0;
  logic signed [4:0] check_in [3], check_out [3];
  logic signed [4:0] prior = 2, relay_term = 1, variable_in [3], belief, variable_out [3];
  logic hard_decision;
  check_node_tile #(.B(5), .MAX_DEGREE(3), .CLIP(15)) check_dut (
    .valid(valid), .degree(degree), .syndrome_bit(syndrome_bit), .incoming(check_in), .outgoing(check_out));
  variable_node_tile #(.B(5), .MAX_DEGREE(3), .CLIP(15)) variable_dut (
    .valid(valid), .degree(degree), .prior(prior), .relay_term(relay_term),
    .incoming(variable_in), .belief(belief), .outgoing(variable_out), .hard_decision(hard_decision));
  initial begin
    check_in[0] = 3; check_in[1] = -3; check_in[2] = 3;
    variable_in[0] = -1; variable_in[1] = 2; variable_in[2] = 0;
    #1;
    if (check_out[0] !== -3 || check_out[1] !== 3 || check_out[2] !== -3)
      $fatal(1, "check-node vector mismatch");
    if (belief !== 4 || hard_decision || variable_out[0] !== 5 || variable_out[1] !== 2 || variable_out[2] !== 4)
      $fatal(1, "variable-node vector mismatch");
    $display("check and variable node vectors passed");
    $finish;
  end
endmodule

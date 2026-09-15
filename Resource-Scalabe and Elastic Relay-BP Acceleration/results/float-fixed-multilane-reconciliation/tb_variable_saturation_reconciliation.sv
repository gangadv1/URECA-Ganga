`timescale 1ns/1ps
module tb_variable_saturation_reconciliation;
 reg [3:0] degree=2; reg signed [17:0] physical_prior=0,previous_marginal=0;
 reg signed [4:0] gamma_q=0; reg signed [17:0] mu_in[0:1];
 wire signed [17:0] bias,marginal,nu_out[0:1],weight_contribution;
 wire signed [21:0] incoming_sum; wire hard_decision,accumulator_saturated,bias_saturated,marginal_saturated;
 wire [1:0] nu_saturated;
 relay_bp_variable_node_18 #(.MAX_DEGREE(2)) dut(.*);
 initial begin
  physical_prior=8;previous_marginal=8;mu_in[0]=2;mu_in[1]=3;
  #10; $display("NUMERIC 0 %0d %0d %0d %0d %0d",bias,incoming_sum,marginal,nu_out[0],nu_out[1]);
  physical_prior=131000;previous_marginal=131000;mu_in[0]=100;mu_in[1]=100;
  #10; $display("NUMERIC 1 %0d %0d %0d %0d %0d",bias,incoming_sum,marginal,nu_out[0],nu_out[1]);
  physical_prior=-131000;previous_marginal=-131000;mu_in[0]=-100;mu_in[1]=-100;
  #10; $display("NUMERIC 2 %0d %0d %0d %0d %0d",bias,incoming_sum,marginal,nu_out[0],nu_out[1]);
  $finish;
 end
endmodule

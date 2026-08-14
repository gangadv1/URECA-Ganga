`timescale 1ns/1ps
// Controlled structural test: candidate0 is injected at the arbiter boundary.
// This is not claimed as a naturally converged Tier-2 decode.
module tb_relay_bp_tier2_n2_cancellation_structural;
 localparam C=1728,V=67752,E=391320,L=1;logic clk=0,rst=1,start=0,cfg_we=0;logic[3:0]cfg_kind=0;logic[31:0]cfg_addr=0;logic signed[31:0]cfg_data=0;
 logic b0,b1,cx0,cx1,pq,gd,gcv,win,ca0,ca1;logic[31:0]crq,cak,cqu;integer timeout;
 always #5 clk=~clk;
 relay_bp_parallel_n2_p4 #(.C(C),.V(V),.E(E),.L(L),
  .CP_INIT("fpga/verification/tier2_p0p003/images/check_row_ptr.memh"),.VP_INIT("fpga/verification/tier2_p0p003/images/variable_row_ptr.memh"),
  .EV_B0_INIT("fpga/verification/tier2_p0p003/images/check_edge_fault_ids_b0.memh"),.EV_B1_INIT("fpga/verification/tier2_p0p003/images/check_edge_fault_ids_b1.memh"),.EV_B2_INIT("fpga/verification/tier2_p0p003/images/check_edge_fault_ids_b2.memh"),.EV_B3_INIT("fpga/verification/tier2_p0p003/images/check_edge_fault_ids_b3.memh"),
  .VE_B0_INIT("fpga/verification/tier2_p0p003/images/variable_to_edge_b0.memh"),.VE_B1_INIT("fpga/verification/tier2_p0p003/images/variable_to_edge_b1.memh"),.VE_B2_INIT("fpga/verification/tier2_p0p003/images/variable_to_edge_b2.memh"),.VE_B3_INIT("fpga/verification/tier2_p0p003/images/variable_to_edge_b3.memh"),
  .PRIOR_B0_INIT("fpga/verification/tier2_p0p003/images/priors_b0.memh"),.PRIOR_B1_INIT("fpga/verification/tier2_p0p003/images/priors_b1.memh"),.PRIOR_B2_INIT("fpga/verification/tier2_p0p003/images/priors_b2.memh"),.PRIOR_B3_INIT("fpga/verification/tier2_p0p003/images/priors_b3.memh"),
  .MARG_B0_INIT("fpga/verification/tier2_p0p003/images/priors_b0.memh"),.MARG_B1_INIT("fpga/verification/tier2_p0p003/images/priors_b1.memh"),.MARG_B2_INIT("fpga/verification/tier2_p0p003/images/priors_b2.memh"),.MARG_B3_INIT("fpga/verification/tier2_p0p003/images/priors_b3.memh"),
  .SYN_B0_INIT("fpga/verification/tier2_p0p003/images/syndrome_shot0_b0.memh"),.SYN_B1_INIT("fpga/verification/tier2_p0p003/images/syndrome_shot0_b1.memh"),.SYN_B2_INIT("fpga/verification/tier2_p0p003/images/syndrome_shot0_b2.memh"),.SYN_B3_INIT("fpga/verification/tier2_p0p003/images/syndrome_shot0_b3.memh"))dut(
  .clk,.rst,.start,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,.first_limit(16'd1),.later_limit(16'd1),.first_gamma(5'sd2),.frame_id(32'd99),
  .gamma0_valid(1'b0),.gamma0_variable_index(17'd0),.gamma0_value(5'sd0),.gamma0_done(1'b0),.gamma0_seed_valid(1'b0),.gamma0_seed(64'd0),.gamma0_updated_state(64'd0),
  .gamma1_valid(1'b0),.gamma1_variable_index(17'd0),.gamma1_value(5'sd0),.gamma1_done(1'b0),.gamma1_seed_valid(1'b0),.gamma1_seed(64'd1),.gamma1_updated_state(64'd1),
  .engine0_busy(b0),.engine1_busy(b1),.global_done(gd),.global_candidate_valid(gcv),.winning_engine_id(win),.engine0_cancel_ack(ca0),.engine1_cancel_ack(ca1),.engine0_cancelled(cx0),.engine1_cancelled(cx1),.pair_quiescent(pq),.loser_cancel_request_cycle(crq),.loser_cancel_ack_cycle(cak),.loser_quiescent_cycle(cqu),.correction_req(1'b0),.correction_word(0));
 initial begin repeat(2)@(posedge clk);rst=0;@(negedge clk)start=1;@(negedge clk)start=0;repeat(32)@(posedge clk);
  force dut.engine0_candidate_valid=1'b1;force dut.engine0_weight=-32'sd7;force dut.engine0_iterations=32'd1;force dut.engine0_legs=1'b1;@(posedge clk);#1;release dut.engine0_candidate_valid;release dut.engine0_weight;release dut.engine0_iterations;release dut.engine0_legs;
  timeout=0;while(!cx1&&timeout<1000)begin @(posedge clk);timeout=timeout+1;end
  if(!gd||!gcv||win||!cx1||ca0||b1)$fatal(1,"Tier2 cancellation structure failed");
  repeat(5)begin @(posedge clk);if(b1||dut.engine_1.req_valid||dut.engine_1.rsp_valid)$fatal(1,"Tier2 loser activity after cancellation");end
  $display("TIER2_N2_CANCELLATION_STRUCTURAL_RESULT dimensions=1728/67752/391320 phase=gamma_load winner=0 loser=1 cancel_req=%0d cancel_ack=%0d quiescent=%0d pass=1 controlled=1",crq,cak,cqu);$finish;
 end
endmodule

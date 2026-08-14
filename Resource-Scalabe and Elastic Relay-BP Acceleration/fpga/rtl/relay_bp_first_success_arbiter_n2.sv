`ifdef RELAY_BP_SIM_ASSERT
`define RELAY_BP_ASSERT_FAIL(msg) $fatal(1,msg)
`else
`define RELAY_BP_ASSERT_FAIL(msg)
`endif
module relay_bp_first_success_arbiter_n2 #(parameter int LW=2)(
 input logic clk,rst,start,input logic[31:0]cycle_count,frame_id,
 input logic candidate0,candidate1,failed0,failed1,input logic signed[31:0]weight0,weight1,
 input logic[31:0]iterations0,iterations1,input logic[LW-1:0]legs0,legs1,
 output logic global_done,global_failed,global_candidate_valid,winning_engine_id,
 output logic signed[31:0]winning_weight,output logic[31:0]winning_iteration_count,
 output logic[LW-1:0]winning_leg_count,output logic[31:0]first_success_cycle,winning_frame_id,
 output logic same_cycle_success);
 logic winner_locked;logic locked_id;logic signed[31:0]locked_weight;logic[31:0]locked_iterations,locked_cycle,locked_frame;logic[LW-1:0]locked_legs;
 always_ff @(posedge clk)begin
  if(rst)begin global_done<=0;global_failed<=0;global_candidate_valid<=0;winner_locked<=0;same_cycle_success<=0;end
  else if(start)begin global_done<=0;global_failed<=0;global_candidate_valid<=0;winner_locked<=0;same_cycle_success<=0;winning_frame_id<=frame_id;end
  else if(!global_done)begin
   if(candidate0||candidate1)begin
    winner_locked<=1;global_done<=1;global_candidate_valid<=1;global_failed<=0;
    winning_engine_id<=candidate0?1'b0:1'b1;winning_weight<=candidate0?weight0:weight1;
    winning_iteration_count<=candidate0?iterations0:iterations1;winning_leg_count<=candidate0?legs0:legs1;
    first_success_cycle<=cycle_count;same_cycle_success<=candidate0&&candidate1;winning_frame_id<=frame_id;
    locked_id<=candidate0?1'b0:1'b1;locked_weight<=candidate0?weight0:weight1;locked_iterations<=candidate0?iterations0:iterations1;locked_legs<=candidate0?legs0:legs1;locked_cycle<=cycle_count;locked_frame<=frame_id;
   end else if(failed0&&failed1)begin global_done<=1;global_failed<=1;global_candidate_valid<=0;end
  end
`ifdef RELAY_BP_SIM_ASSERT
  if(!start&&global_failed&&(!failed0||!failed1||global_candidate_valid))`RELAY_BP_ASSERT_FAIL("invalid global failure");
  if(!start&&global_candidate_valid&&!winner_locked)`RELAY_BP_ASSERT_FAIL("candidate valid without locked winner");
  if(!start&&same_cycle_success&&winning_engine_id)`RELAY_BP_ASSERT_FAIL("same-cycle priority was not engine 0");
  if(!start&&winner_locked)begin
   if(winning_engine_id!=locked_id||winning_weight!=locked_weight||winning_iteration_count!=locked_iterations||winning_leg_count!=locked_legs||first_success_cycle!=locked_cycle||winning_frame_id!=locked_frame)`RELAY_BP_ASSERT_FAIL("winner metadata changed after commit");
  end
`endif
 end
endmodule
`undef RELAY_BP_ASSERT_FAIL

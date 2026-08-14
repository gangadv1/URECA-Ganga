`ifdef RELAY_BP_SIM_ASSERT
`define RELAY_BP_ASSERT_FAIL(msg) $fatal(1,msg)
`else
`define RELAY_BP_ASSERT_FAIL(msg)
`endif
module relay_bp_parallel_n2_p4 #(
 parameter int C=12,V=20,E=76,L=2,P=4,IW=16,LW=$clog2(L+1),VW=(V<=1)?1:$clog2(V),STALL0=0,STALL1=0,CANCEL_ENABLE=1,USE_INTERNAL_RNG=0,
 parameter CP_INIT="",EV_B0_INIT="",EV_B1_INIT="",EV_B2_INIT="",EV_B3_INIT="",VP_INIT="",VE_B0_INIT="",VE_B1_INIT="",VE_B2_INIT="",VE_B3_INIT="",
 parameter PRIOR_B0_INIT="",PRIOR_B1_INIT="",PRIOR_B2_INIT="",PRIOR_B3_INIT="",SYN_B0_INIT="",SYN_B1_INIT="",SYN_B2_INIT="",SYN_B3_INIT="",
 parameter MARG_B0_INIT="",MARG_B1_INIT="",MARG_B2_INIT="",MARG_B3_INIT=""
)(input logic clk,rst,start,input logic cfg_we,input logic[3:0]cfg_kind,input logic[31:0]cfg_addr,input logic signed[31:0]cfg_data,
 input logic[IW-1:0]first_limit,later_limit,input logic signed[4:0]first_gamma,input logic[31:0]frame_id,
 input logic gamma0_valid,input logic[VW-1:0]gamma0_variable_index,input logic signed[4:0]gamma0_value,input logic gamma0_done,input logic gamma0_seed_valid,input logic[63:0]gamma0_seed,gamma0_updated_state,
 output logic gamma0_start,gamma0_abort,output logic[LW-1:0]gamma0_leg_index,output logic[31:0]gamma0_variable_count,output logic gamma0_ready,gamma0_seed_load,output logic[63:0]gamma0_seed_state,
 input logic gamma1_valid,input logic[VW-1:0]gamma1_variable_index,input logic signed[4:0]gamma1_value,input logic gamma1_done,input logic gamma1_seed_valid,input logic[63:0]gamma1_seed,gamma1_updated_state,
 output logic gamma1_start,gamma1_abort,output logic[LW-1:0]gamma1_leg_index,output logic[31:0]gamma1_variable_count,output logic gamma1_ready,gamma1_seed_load,output logic[63:0]gamma1_seed_state,
 output logic start_accepted,output logic[31:0]active_frame_id,
 output logic engine0_busy,engine1_busy,engine0_done,engine1_done,engine0_failed,engine1_failed,engine0_candidate_valid,engine1_candidate_valid,
 output logic signed[31:0]engine0_weight,engine1_weight,output logic[31:0]engine0_iterations,engine1_iterations,output logic[LW-1:0]engine0_legs,engine1_legs,
 output logic global_done,global_failed,global_candidate_valid,winning_engine_id,output logic signed[31:0]winning_weight,output logic[31:0]winning_iteration_count,output logic[LW-1:0]winning_leg_count,
 output logic same_cycle_success,output logic[31:0]first_success_cycle,winning_frame_id,engine0_completion_cycle,engine1_completion_cycle,
 output logic engine0_cancel_ack,engine1_cancel_ack,engine0_cancelled,engine1_cancelled,pair_quiescent,loser_cancel_pending,
 output logic[31:0]loser_cancel_request_cycle,loser_cancel_ack_cycle,loser_quiescent_cycle,
 output logic[63:0]rng0_state,rng1_state,output logic[31:0]rng0_words,rng1_words,rng0_rejected,rng1_rejected,
 input logic correction_req,input logic[31:0]correction_word,output logic correction_ready,correction_rsp_valid,output logic[P-1:0]correction_bits,correction_mask);
 logic launch,attempt_active,engine0_done_seen,engine1_done_seen;logic[31:0]parallel_cycle;logic e0_corr_ready,e1_corr_ready,e0_corr_valid,e1_corr_valid;logic[P-1:0]e0_corr_bits,e1_corr_bits,e0_corr_mask,e1_corr_mask;
 logic e0_conv,e1_conv,e0_iter_done,e1_iter_done,e0_quiescent,e1_quiescent,loser_quiescent,e0_cancel_req,e1_cancel_req,cancel_req_seen,cancel_ack_seen,cancel_quiet_seen;logic[3:0]e0_phase,e1_phase;logic[LW-1:0]e0_trace_leg,e1_trace_leg;logic[IW-1:0]e0_trace_iter,e1_trace_iter;logic e0_trace_conv,e1_trace_conv;logic signed[31:0]e0_trace_weight,e1_trace_weight;logic[31:0]unused00,unused01,unused02,unused03,unused04,unused10,unused11,unused12,unused13,unused14;
 logic rg0_valid,rg1_valid,rg0_done,rg1_done,rg0_abort_done,rg1_abort_done,rg0_idle,rg1_idle;logic[VW-1:0]rg0_index,rg1_index;logic signed[4:0]rg0_value,rg1_value;logic[63:0]rg0_raw,rg1_raw;
 wire g0_valid_mux=USE_INTERNAL_RNG?rg0_valid:gamma0_valid;wire g1_valid_mux=USE_INTERNAL_RNG?rg1_valid:gamma1_valid;
 wire[VW-1:0]g0_index_mux=USE_INTERNAL_RNG?rg0_index:gamma0_variable_index;wire[VW-1:0]g1_index_mux=USE_INTERNAL_RNG?rg1_index:gamma1_variable_index;
 wire signed[4:0]g0_value_mux=USE_INTERNAL_RNG?rg0_value:gamma0_value;wire signed[4:0]g1_value_mux=USE_INTERNAL_RNG?rg1_value:gamma1_value;
 wire g0_done_mux=USE_INTERNAL_RNG?rg0_done:gamma0_done;wire g1_done_mux=USE_INTERNAL_RNG?rg1_done:gamma1_done;
 assign pair_quiescent=e0_quiescent&&e1_quiescent;
 assign loser_quiescent=global_candidate_valid&&(winning_engine_id?e0_quiescent:e1_quiescent);
 assign launch=start&&pair_quiescent&&!attempt_active;
 assign e0_cancel_req=CANCEL_ENABLE&&global_candidate_valid&&winning_engine_id&&!engine0_cancelled;
 assign e1_cancel_req=CANCEL_ENABLE&&global_candidate_valid&&!winning_engine_id&&!engine1_cancelled;
 assign loser_cancel_pending=global_candidate_valid&&(winning_engine_id?!engine0_cancelled:!engine1_cancelled);
 relay_bp_gamma_rng #(.VW(VW),.LW(LW))gamma_rng_0(.clk,.rst,.seed_load(gamma0_seed_valid),.seed_value(gamma0_seed),.gamma_start(gamma0_start),.leg_index(gamma0_leg_index),.variable_count(gamma0_variable_count),.gamma_ready(gamma0_ready),.gamma_abort(gamma0_abort),.gamma_valid(rg0_valid),.gamma_variable_index(rg0_index),.gamma_value(rg0_value),.gamma_done(rg0_done),.abort_done(rg0_abort_done),.idle(rg0_idle),.rng_state(rng0_state),.raw_random_word(rg0_raw),.words_consumed(rng0_words),.rejected_words(rng0_rejected));
 relay_bp_gamma_rng #(.VW(VW),.LW(LW))gamma_rng_1(.clk,.rst,.seed_load(gamma1_seed_valid),.seed_value(gamma1_seed),.gamma_start(gamma1_start),.leg_index(gamma1_leg_index),.variable_count(gamma1_variable_count),.gamma_ready(gamma1_ready),.gamma_abort(gamma1_abort),.gamma_valid(rg1_valid),.gamma_variable_index(rg1_index),.gamma_value(rg1_value),.gamma_done(rg1_done),.abort_done(rg1_abort_done),.idle(rg1_idle),.rng_state(rng1_state),.raw_random_word(rg1_raw),.words_consumed(rng1_words),.rejected_words(rng1_rejected));
 assign correction_ready=global_candidate_valid?(winning_engine_id?e1_corr_ready:e0_corr_ready):1'b0;
 assign correction_rsp_valid=global_candidate_valid?(winning_engine_id?e1_corr_valid:e0_corr_valid):1'b0;
 assign correction_bits=winning_engine_id?e1_corr_bits:e0_corr_bits;
 assign correction_mask=global_candidate_valid?(winning_engine_id?e1_corr_mask:e0_corr_mask):'0;
 relay_bp_single_engine_memory_p4 #(.C(C),.V(V),.E(E),.L(L),.P(P),.STALL_PERIOD(STALL0),.CP_INIT(CP_INIT),.EV_B0_INIT(EV_B0_INIT),.EV_B1_INIT(EV_B1_INIT),.EV_B2_INIT(EV_B2_INIT),.EV_B3_INIT(EV_B3_INIT),.VP_INIT(VP_INIT),.VE_B0_INIT(VE_B0_INIT),.VE_B1_INIT(VE_B1_INIT),.VE_B2_INIT(VE_B2_INIT),.VE_B3_INIT(VE_B3_INIT),.PRIOR_B0_INIT(PRIOR_B0_INIT),.PRIOR_B1_INIT(PRIOR_B1_INIT),.PRIOR_B2_INIT(PRIOR_B2_INIT),.PRIOR_B3_INIT(PRIOR_B3_INIT),.SYN_B0_INIT(SYN_B0_INIT),.SYN_B1_INIT(SYN_B1_INIT),.SYN_B2_INIT(SYN_B2_INIT),.SYN_B3_INIT(SYN_B3_INIT),.MARG_B0_INIT(MARG_B0_INIT),.MARG_B1_INIT(MARG_B1_INIT),.MARG_B2_INIT(MARG_B2_INIT),.MARG_B3_INIT(MARG_B3_INIT)) engine_0(
  .clk,.rst,.start(launch),.cancel_request(e0_cancel_req),.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,.first_limit,.later_limit,.first_gamma,.gamma_valid(g0_valid_mux),.gamma_variable_index(g0_index_mux),.gamma_value(g0_value_mux),.gamma_done(g0_done_mux),.gamma_seed_valid(gamma0_seed_valid),.gamma_seed(gamma0_seed),.gamma_updated_state(USE_INTERNAL_RNG?rng0_state:gamma0_updated_state),.gamma_start(gamma0_start),.gamma_abort(gamma0_abort),.gamma_leg_index(gamma0_leg_index),.gamma_variable_count(gamma0_variable_count),.gamma_ready(gamma0_ready),.gamma_seed_load(gamma0_seed_load),.gamma_seed_state(gamma0_seed_state),.busy(engine0_busy),.done(engine0_done),.converged(e0_conv),.failed(engine0_failed),.candidate_valid(engine0_candidate_valid),.total_iterations(engine0_iterations),.cancel_ack(engine0_cancel_ack),.cancelled(engine0_cancelled),.quiescent(e0_quiescent),.phase_state(e0_phase),.relay_legs(engine0_legs),.selected_weight(engine0_weight),.total_cycles(),.iteration_done(e0_iter_done),.trace_leg(e0_trace_leg),.trace_iteration(e0_trace_iter),.trace_converged(e0_trace_conv),.trace_weight(e0_trace_weight),.correction_req(correction_req&&global_candidate_valid&&!winning_engine_id),.correction_word,.correction_ready(e0_corr_ready),.correction_rsp_valid(e0_corr_valid),.correction_bits(e0_corr_bits),.correction_mask(e0_corr_mask),.check_cycles(unused00),.variable_cycles(unused01),.convergence_cycles(unused02),.relay_cycles(unused03),.wait_cycles(unused04));
 relay_bp_single_engine_memory_p4 #(.C(C),.V(V),.E(E),.L(L),.P(P),.STALL_PERIOD(STALL1),.CP_INIT(CP_INIT),.EV_B0_INIT(EV_B0_INIT),.EV_B1_INIT(EV_B1_INIT),.EV_B2_INIT(EV_B2_INIT),.EV_B3_INIT(EV_B3_INIT),.VP_INIT(VP_INIT),.VE_B0_INIT(VE_B0_INIT),.VE_B1_INIT(VE_B1_INIT),.VE_B2_INIT(VE_B2_INIT),.VE_B3_INIT(VE_B3_INIT),.PRIOR_B0_INIT(PRIOR_B0_INIT),.PRIOR_B1_INIT(PRIOR_B1_INIT),.PRIOR_B2_INIT(PRIOR_B2_INIT),.PRIOR_B3_INIT(PRIOR_B3_INIT),.SYN_B0_INIT(SYN_B0_INIT),.SYN_B1_INIT(SYN_B1_INIT),.SYN_B2_INIT(SYN_B2_INIT),.SYN_B3_INIT(SYN_B3_INIT),.MARG_B0_INIT(MARG_B0_INIT),.MARG_B1_INIT(MARG_B1_INIT),.MARG_B2_INIT(MARG_B2_INIT),.MARG_B3_INIT(MARG_B3_INIT)) engine_1(
  .clk,.rst,.start(launch),.cancel_request(e1_cancel_req),.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,.first_limit,.later_limit,.first_gamma,.gamma_valid(g1_valid_mux),.gamma_variable_index(g1_index_mux),.gamma_value(g1_value_mux),.gamma_done(g1_done_mux),.gamma_seed_valid(gamma1_seed_valid),.gamma_seed(gamma1_seed),.gamma_updated_state(USE_INTERNAL_RNG?rng1_state:gamma1_updated_state),.gamma_start(gamma1_start),.gamma_abort(gamma1_abort),.gamma_leg_index(gamma1_leg_index),.gamma_variable_count(gamma1_variable_count),.gamma_ready(gamma1_ready),.gamma_seed_load(gamma1_seed_load),.gamma_seed_state(gamma1_seed_state),.busy(engine1_busy),.done(engine1_done),.converged(e1_conv),.failed(engine1_failed),.candidate_valid(engine1_candidate_valid),.total_iterations(engine1_iterations),.cancel_ack(engine1_cancel_ack),.cancelled(engine1_cancelled),.quiescent(e1_quiescent),.phase_state(e1_phase),.relay_legs(engine1_legs),.selected_weight(engine1_weight),.total_cycles(),.iteration_done(e1_iter_done),.trace_leg(e1_trace_leg),.trace_iteration(e1_trace_iter),.trace_converged(e1_trace_conv),.trace_weight(e1_trace_weight),.correction_req(correction_req&&global_candidate_valid&&winning_engine_id),.correction_word,.correction_ready(e1_corr_ready),.correction_rsp_valid(e1_corr_valid),.correction_bits(e1_corr_bits),.correction_mask(e1_corr_mask),.check_cycles(unused10),.variable_cycles(unused11),.convergence_cycles(unused12),.relay_cycles(unused13),.wait_cycles(unused14));
 relay_bp_first_success_arbiter_n2 #(.LW(LW)) result_arbiter(.clk,.rst,.start(launch),.cycle_count(parallel_cycle),.frame_id,.candidate0(engine0_candidate_valid),.candidate1(engine1_candidate_valid),.failed0(engine0_failed),.failed1(engine1_failed),.weight0(engine0_weight),.weight1(engine1_weight),.iterations0(engine0_iterations),.iterations1(engine1_iterations),.legs0(engine0_legs),.legs1(engine1_legs),.global_done,.global_failed,.global_candidate_valid,.winning_engine_id,.winning_weight,.winning_iteration_count,.winning_leg_count,.first_success_cycle,.winning_frame_id,.same_cycle_success);
 always_ff @(posedge clk)begin
  if(rst)begin start_accepted<=0;attempt_active<=0;parallel_cycle<=0;engine0_done_seen<=0;engine1_done_seen<=0;engine0_completion_cycle<=0;engine1_completion_cycle<=0;loser_cancel_request_cycle<=0;loser_cancel_ack_cycle<=0;loser_quiescent_cycle<=0;cancel_req_seen<=0;cancel_ack_seen<=0;cancel_quiet_seen<=0;end else begin
   start_accepted<=0;if(launch)begin start_accepted<=1;attempt_active<=1;active_frame_id<=frame_id;parallel_cycle<=0;engine0_done_seen<=0;engine1_done_seen<=0;engine0_completion_cycle<=0;engine1_completion_cycle<=0;cancel_req_seen<=0;cancel_ack_seen<=0;cancel_quiet_seen<=0;loser_cancel_request_cycle<=0;loser_cancel_ack_cycle<=0;loser_quiescent_cycle<=0;end
   else if(attempt_active)parallel_cycle<=parallel_cycle+1;
   if(attempt_active&&engine0_done)begin engine0_completion_cycle<=parallel_cycle;engine0_done_seen<=1;end
   if(attempt_active&&engine1_done)begin engine1_completion_cycle<=parallel_cycle;engine1_done_seen<=1;end
   if((e0_cancel_req||e1_cancel_req)&&!cancel_req_seen)begin loser_cancel_request_cycle<=parallel_cycle;cancel_req_seen<=1;end
   if((engine0_cancel_ack||engine1_cancel_ack)&&!cancel_ack_seen)begin loser_cancel_ack_cycle<=parallel_cycle;cancel_ack_seen<=1;end
   if(loser_quiescent&&(cancel_ack_seen||engine0_cancel_ack||engine1_cancel_ack)&&!cancel_quiet_seen)begin loser_quiescent_cycle<=parallel_cycle;cancel_quiet_seen<=1;end
   if(attempt_active&&global_done&&pair_quiescent)attempt_active<=0;
  end
 end
`ifdef RELAY_BP_SIM_ASSERT
 always_ff @(posedge clk)if(start_accepted&&(engine0_busy!==engine1_busy))`RELAY_BP_ASSERT_FAIL("N=2 launch skew");
 always_ff @(posedge clk)if(correction_req&&!global_candidate_valid)`RELAY_BP_ASSERT_FAIL("global correction requested without winner");
 always_ff @(posedge clk)if(e0_cancel_req&&!winning_engine_id)`RELAY_BP_ASSERT_FAIL("cancel sent to engine 0 winner");
 always_ff @(posedge clk)if(e1_cancel_req&&winning_engine_id)`RELAY_BP_ASSERT_FAIL("cancel sent to engine 1 winner");
 always_ff @(posedge clk)if(pair_quiescent&&(engine0_busy||engine1_busy))`RELAY_BP_ASSERT_FAIL("pair quiescent while engine busy");
 always_ff @(posedge clk)if(launch&&!pair_quiescent)`RELAY_BP_ASSERT_FAIL("new frame launched before pair quiescence");
 always_ff @(posedge clk)if(engine0_cancelled&&engine0_candidate_valid)`RELAY_BP_ASSERT_FAIL("cancelled engine 0 exposed candidate");
 always_ff @(posedge clk)if(engine1_cancelled&&engine1_candidate_valid)`RELAY_BP_ASSERT_FAIL("cancelled engine 1 exposed candidate");
`endif
endmodule
`undef RELAY_BP_ASSERT_FAIL

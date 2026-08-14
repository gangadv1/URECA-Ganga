`ifdef RELAY_BP_SIM_ASSERT
`define RELAY_BP_ASSERT_FAIL(msg) $fatal(1,msg)
`else
`define RELAY_BP_ASSERT_FAIL(msg)
`endif
// Complete S=1 response-memory-backed Relay-BP trajectory engine.
module relay_bp_single_engine_memory_p4 #(
 parameter int C=12,V=20,E=76,L=2,P=4,IW=16,LW=$clog2(L+1),VW=(V<=1)?1:$clog2(V),STALL_PERIOD=0,
 parameter CP_INIT="",EV_B0_INIT="",EV_B1_INIT="",EV_B2_INIT="",EV_B3_INIT="",VP_INIT="",VE_B0_INIT="",VE_B1_INIT="",VE_B2_INIT="",VE_B3_INIT="",
 parameter PRIOR_B0_INIT="",PRIOR_B1_INIT="",PRIOR_B2_INIT="",PRIOR_B3_INIT="",SYN_B0_INIT="",SYN_B1_INIT="",SYN_B2_INIT="",SYN_B3_INIT="",
 parameter MARG_B0_INIT="",MARG_B1_INIT="",MARG_B2_INIT="",MARG_B3_INIT=""
)(input logic clk,rst,start,input logic cancel_request,input logic cfg_we,input logic[3:0]cfg_kind,input logic[31:0]cfg_addr,input logic signed[31:0]cfg_data,
 input logic[IW-1:0]first_limit,later_limit,
 input logic signed[4:0]first_gamma,input logic gamma_valid,input logic[VW-1:0]gamma_variable_index,input logic signed[4:0]gamma_value,input logic gamma_done,
 input logic gamma_seed_valid,input logic[63:0]gamma_seed,input logic[63:0]gamma_updated_state,
 output logic gamma_start,output logic gamma_abort,output logic[LW-1:0]gamma_leg_index,output logic[31:0]gamma_variable_count,output logic gamma_ready,output logic gamma_seed_load,output logic[63:0]gamma_seed_state,
 output logic busy,done,converged,failed,candidate_valid,output logic[31:0]total_iterations,
 output logic cancel_ack,cancelled,quiescent,output logic[3:0]phase_state,
 output logic[LW-1:0]relay_legs,output logic signed[31:0]selected_weight,output logic[31:0]total_cycles,
 output logic iteration_done,output logic[LW-1:0]trace_leg,output logic[IW-1:0]trace_iteration,
 output logic trace_converged,output logic signed[31:0]trace_weight,
 input logic correction_req,input logic[31:0]correction_word,output logic correction_ready,correction_rsp_valid,output logic[P-1:0]correction_bits,correction_mask,
 output logic[31:0]check_cycles,variable_cycles,convergence_cycles,relay_cycles,wait_cycles);
 localparam OWN_NONE=0,OWN_CHECK=1,OWN_VAR=2,OWN_CONV=3,OWN_RELAY=4,OWN_GAMMA=5;
 typedef enum logic[3:0]{IDLE,GAMMA_LOAD,INIT_FIRST_LEG,CHECK_UPDATE,VARIABLE_UPDATE,CONVERGENCE_CHECK,
  CANDIDATE_UPDATE,NEXT_ITERATION,RELAY_INIT,DONE_S,FAIL_S,CANCELLED_S}state_t;
 state_t state;logic[2:0]owner;logic[IW-1:0]leg_iteration;logic[LW-1:0]leg_index;
 logic cancel_pending;
 logic check_start,var_start,conv_start,relay_start,check_done,var_done,conv_done,relay_done;
 logic[VW-1:0]gamma_fill_index;logic gamma_external_done;
 logic check_busy,var_busy,conv_busy,relay_busy,conv_result;logic[31:0]conv_residual;
 logic signed[31:0]var_weight;logic mu_valid;
 // Per-controller transaction buses.
 wire cv,cw,vv,vw,xv,xw,rv,rw;wire[3:0]ck,vk,xk,rk;wire[3:0]cm,vm,xm,rm;
 wire[31:0]ca[0:3],va[0:3],xa[0:3],ra[0:3];wire signed[21:0]cd[0:3],vd[0:3],xd[0:3],rd[0:3];
 logic req_valid,req_write,req_ready,rsp_valid;logic[3:0]req_kind,rsp_kind,req_mask,rsp_mask;
 logic[31:0]req_addr[0:3],rsp_addr[0:3];logic signed[21:0]req_wdata[0:3],rsp_data[0:3];
 wire[31:0]ccyc,cread,crsp,cwrite,cwait,vcyc,vread,vrsp,vwrite,vwait,v_misc0,v_misc1,v_misc2;
 wire[31:0]xcyc,xread,xrsp,xwait,xconf,xretry,rlycyc,rlyread,rlyrsp,rlywrite,rlywait,rlypc,rlync,rlyretry,rlygw;
 wire[31:0]memrc,memwc;wire variable_pulse;wire[VW-1:0]var_id;wire signed[17:0]vb,vmarg,vweight;wire signed[21:0]vsum;wire vdec;
 assign phase_state=state;
 assign quiescent=!busy&&!check_busy&&!var_busy&&!conv_busy&&!relay_busy&&!req_valid&&!rsp_valid;
 relay_bp_memory_fabric_p4 #(.C(C),.V(V),.E(E),.L(L),.STALL_PERIOD(STALL_PERIOD),.CP_INIT(CP_INIT),.EV_B0_INIT(EV_B0_INIT),.EV_B1_INIT(EV_B1_INIT),.EV_B2_INIT(EV_B2_INIT),.EV_B3_INIT(EV_B3_INIT),
  .VP_INIT(VP_INIT),.VE_B0_INIT(VE_B0_INIT),.VE_B1_INIT(VE_B1_INIT),.VE_B2_INIT(VE_B2_INIT),.VE_B3_INIT(VE_B3_INIT),.PRIOR_B0_INIT(PRIOR_B0_INIT),.PRIOR_B1_INIT(PRIOR_B1_INIT),.PRIOR_B2_INIT(PRIOR_B2_INIT),.PRIOR_B3_INIT(PRIOR_B3_INIT),
  .MARG_B0_INIT(MARG_B0_INIT),.MARG_B1_INIT(MARG_B1_INIT),.MARG_B2_INIT(MARG_B2_INIT),.MARG_B3_INIT(MARG_B3_INIT),
  .SYN_B0_INIT(SYN_B0_INIT),.SYN_B1_INIT(SYN_B1_INIT),.SYN_B2_INIT(SYN_B2_INIT),.SYN_B3_INIT(SYN_B3_INIT)) memory(.clk,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.read_conflicts(memrc),.write_conflicts(memwc),
  .correction_req(correction_req&&candidate_valid&&!busy),.correction_word,.correction_ready,.correction_rsp_valid,.correction_bits,.correction_mask);
 relay_bp_check_controller_p4 #(.CHECKS(C),.EDGES(E)) check_u(.clk,.rst,.start(check_start),.busy(check_busy),.done(check_done),
  .req_valid(cv),.req_write(cw),.req_kind(ck),.req_mask(cm),.req_addr(ca),.req_wdata(cd),.req_ready(owner==OWN_CHECK?req_ready:1'b0),
  .rsp_valid(owner==OWN_CHECK?rsp_valid:1'b0),.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.cycle_count(ccyc),.read_requests(cread),.response_count(crsp),.mu_write_requests(cwrite),.wait_cycles(cwait),.debug_check(),.debug_position(),.debug_state());
 relay_bp_variable_controller_p4 #(.VARIABLES(V),.EDGES(E)) var_u(.clk,.rst,.start(var_start),.gamma_base(0),.busy(var_busy),.done(var_done),
  .req_valid(vv),.req_write(vw),.req_kind(vk),.req_mask(vm),.req_addr(va),.req_wdata(vd),.req_ready(owner==OWN_VAR?req_ready:1'b0),
  .rsp_valid(owner==OWN_VAR?rsp_valid:1'b0),.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.variable_done(variable_pulse),.trace_variable(var_id),
  .trace_bias(vb),.trace_marginal(vmarg),.trace_sum(vsum),.trace_decision(vdec),.trace_weight_contribution(vweight),.candidate_weight(var_weight),
  .cycle_count(vcyc),.read_requests(vread),.response_count(vrsp),.write_requests(vwrite),.wait_cycles(vwait),.mu_conflicts(v_misc0),.nu_conflicts(v_misc1),.retry_subsets(v_misc2));
 relay_bp_convergence_controller_p4 #(.CHECKS(C),.VARIABLES(V),.EDGES(E)) conv_u(.clk,.rst,.start(conv_start),.busy(conv_busy),.done(conv_done),.converged(conv_result),.residual_weight(conv_residual),
  .req_valid(xv),.req_write(xw),.req_kind(xk),.req_mask(xm),.req_addr(xa),.req_wdata(xd),.req_ready(owner==OWN_CONV?req_ready:1'b0),
  .rsp_valid(owner==OWN_CONV?rsp_valid:1'b0),.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.check_done(),.trace_check(),.trace_predicted(),.trace_expected(),.trace_mismatch(),
  .cycle_count(xcyc),.read_requests(xread),.response_count(xrsp),.wait_cycles(xwait),.decision_conflicts(xconf),.retry_subsets(xretry));
 relay_bp_relay_init_controller_p4 #(.VARIABLES(V),.EDGES(E)) relay_u(.clk,.rst,.start(relay_start),.busy(relay_busy),.done(relay_done),.mu_valid(),.leg_state_reset(),
  .req_valid(rv),.req_write(rw),.req_kind(rk),.req_mask(rm),.req_addr(ra),.req_wdata(rd),.req_ready(owner==OWN_RELAY?req_ready:1'b0),
  .rsp_valid(owner==OWN_RELAY?rsp_valid:1'b0),.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.cycle_count(rlycyc),.read_requests(rlyread),.response_count(rlyrsp),.write_requests(rlywrite),.wait_cycles(rlywait),.prior_conflicts(rlypc),.nu_conflicts(rlync),.retry_subsets(rlyretry),.gamma_writes(rlygw));
 integer lane;
 always_comb begin req_valid=0;req_write=0;req_kind=0;req_mask=0;gamma_ready=0;gamma_variable_count=V;gamma_leg_index=leg_index;for(lane=0;lane<P;lane=lane+1)begin req_addr[lane]=0;req_wdata[lane]=0;end
  case(owner)OWN_CHECK:begin req_valid=cv;req_write=cw;req_kind=ck;req_mask=cm;for(lane=0;lane<P;lane=lane+1)begin req_addr[lane]=ca[lane];req_wdata[lane]=cd[lane];end end
   OWN_VAR:begin req_valid=vv;req_write=vw;req_kind=vk;req_mask=vm;for(lane=0;lane<P;lane=lane+1)begin req_addr[lane]=va[lane];req_wdata[lane]=vd[lane];end end
   OWN_CONV:begin req_valid=xv;req_write=xw;req_kind=xk;req_mask=xm;for(lane=0;lane<P;lane=lane+1)begin req_addr[lane]=xa[lane];req_wdata[lane]=xd[lane];end end
   OWN_RELAY:begin req_valid=rv;req_write=rw;req_kind=rk;req_mask=rm;for(lane=0;lane<P;lane=lane+1)begin req_addr[lane]=ra[lane];req_wdata[lane]=rd[lane];end end
   OWN_GAMMA:begin req_write=1;req_kind=6;req_mask=1;if(leg_index==0)begin req_valid=1;req_addr[0]=gamma_fill_index;req_wdata[0]=first_gamma;end else begin gamma_ready=req_ready;req_valid=gamma_valid;req_addr[0]=gamma_variable_index;req_wdata[0]=gamma_value;end end endcase end
 always_ff @(posedge clk)begin
  if(rst)begin state<=IDLE;owner<=OWN_NONE;busy<=0;done<=0;converged<=0;failed<=0;candidate_valid<=0;total_cycles<=0;cancel_pending<=0;cancel_ack<=0;cancelled<=0;gamma_abort<=0;end else begin
   done<=0;cancel_ack<=0;gamma_abort<=0;check_start<=0;var_start<=0;conv_start<=0;relay_start<=0;gamma_start<=0;gamma_seed_load<=0;iteration_done<=0;if(busy)total_cycles<=total_cycles+1;
   if(busy&&cancel_request)cancel_pending<=1;
   case(state)
    IDLE:begin if(gamma_seed_valid)begin gamma_seed_state<=gamma_seed;gamma_seed_load<=1;end if(cancel_request)begin candidate_valid<=0;cancelled<=1;cancel_ack<=1;cancel_pending<=0;end else if(start)begin busy<=1;converged<=0;failed<=0;candidate_valid<=0;cancelled<=0;cancel_pending<=0;total_iterations<=0;total_cycles<=0;check_cycles<=0;variable_cycles<=0;convergence_cycles<=0;relay_cycles<=0;wait_cycles<=0;leg_index<=0;relay_legs<=1;leg_iteration<=0;mu_valid<=0;gamma_fill_index<=0;gamma_external_done<=0;owner<=OWN_GAMMA;state<=GAMMA_LOAD;end end
    GAMMA_LOAD:if(cancel_pending||cancel_request)begin owner<=OWN_NONE;busy<=0;candidate_valid<=0;cancelled<=1;cancel_ack<=1;cancel_pending<=0;gamma_abort<=1;state<=CANCELLED_S;end else if(leg_index==0)begin if(req_valid&&req_ready)begin if(gamma_fill_index==V-1)begin owner<=OWN_RELAY;relay_start<=1;state<=INIT_FIRST_LEG;end else gamma_fill_index<=gamma_fill_index+1;end end else begin
      if(gamma_valid&&gamma_ready&&gamma_variable_index==V-1)gamma_external_done<=1;
      if(gamma_done&&(gamma_external_done||(gamma_valid&&gamma_ready&&gamma_variable_index==V-1)))begin gamma_seed_state<=gamma_updated_state;owner<=OWN_RELAY;relay_start<=1;state<=INIT_FIRST_LEG;end end
    INIT_FIRST_LEG:if(relay_done)begin relay_cycles<=relay_cycles+rlycyc;wait_cycles<=wait_cycles+rlywait;if(cancel_pending||cancel_request)begin owner<=OWN_NONE;busy<=0;candidate_valid<=0;cancelled<=1;cancel_ack<=1;cancel_pending<=0;state<=CANCELLED_S;end else begin owner<=OWN_CHECK;check_start<=1;state<=CHECK_UPDATE;end end
    CHECK_UPDATE:if(check_done)begin check_cycles<=check_cycles+ccyc;wait_cycles<=wait_cycles+cwait;mu_valid<=1;if(cancel_pending||cancel_request)begin owner<=OWN_NONE;busy<=0;candidate_valid<=0;cancelled<=1;cancel_ack<=1;cancel_pending<=0;state<=CANCELLED_S;end else begin owner<=OWN_VAR;var_start<=1;state<=VARIABLE_UPDATE;end end
    VARIABLE_UPDATE:if(var_done)begin variable_cycles<=variable_cycles+vcyc;wait_cycles<=wait_cycles+vwait;if(cancel_pending||cancel_request)begin owner<=OWN_NONE;busy<=0;candidate_valid<=0;cancelled<=1;cancel_ack<=1;cancel_pending<=0;state<=CANCELLED_S;end else begin owner<=OWN_CONV;conv_start<=1;state<=CONVERGENCE_CHECK;end end
    CONVERGENCE_CHECK:if(conv_done)begin convergence_cycles<=convergence_cycles+xcyc;wait_cycles<=wait_cycles+xwait;total_iterations<=total_iterations+1;leg_iteration<=leg_iteration+1;iteration_done<=1;trace_leg<=leg_index+1;trace_iteration<=leg_iteration+1;trace_converged<=conv_result;trace_weight<=var_weight;owner<=OWN_NONE;
      if(cancel_pending||cancel_request)begin busy<=0;candidate_valid<=0;cancelled<=1;cancel_ack<=1;cancel_pending<=0;state<=CANCELLED_S;end else if(conv_result)state<=CANDIDATE_UPDATE;else if(leg_iteration+1>=((leg_index==0)?first_limit:later_limit))begin if(leg_index+1<L)state<=RELAY_INIT;else state<=FAIL_S;end else state<=NEXT_ITERATION;end
    CANDIDATE_UPDATE:if(cancel_pending||cancel_request)begin busy<=0;candidate_valid<=0;cancelled<=1;cancel_ack<=1;cancel_pending<=0;owner<=OWN_NONE;state<=CANCELLED_S;end else begin candidate_valid<=1;selected_weight<=var_weight;converged<=1;state<=DONE_S;end
    NEXT_ITERATION:if(cancel_pending||cancel_request)begin busy<=0;candidate_valid<=0;cancelled<=1;cancel_ack<=1;cancel_pending<=0;owner<=OWN_NONE;state<=CANCELLED_S;end else begin owner<=OWN_CHECK;check_start<=1;state<=CHECK_UPDATE;end
    RELAY_INIT:if(cancel_pending||cancel_request)begin busy<=0;candidate_valid<=0;cancelled<=1;cancel_ack<=1;cancel_pending<=0;owner<=OWN_NONE;state<=CANCELLED_S;end else begin leg_index<=leg_index+1;relay_legs<=relay_legs+1;leg_iteration<=0;mu_valid<=0;gamma_external_done<=0;owner<=OWN_GAMMA;gamma_start<=1;state<=GAMMA_LOAD;end
    DONE_S:if(cancel_pending||cancel_request)begin busy<=0;candidate_valid<=0;cancelled<=1;cancel_ack<=1;cancel_pending<=0;owner<=OWN_NONE;state<=CANCELLED_S;end else begin busy<=0;done<=1;owner<=OWN_NONE;state<=IDLE;end
    FAIL_S:begin busy<=0;failed<=1;done<=1;owner<=OWN_NONE;state<=IDLE;end
    CANCELLED_S:begin busy<=0;owner<=OWN_NONE;state<=IDLE;end
   endcase
`ifdef RELAY_BP_SIM_ASSERT
   if(var_start&&!mu_valid)`RELAY_BP_ASSERT_FAIL("variable phase started with invalid mu");
   if((check_busy+var_busy+conv_busy+relay_busy)>1)`RELAY_BP_ASSERT_FAIL("multiple phase controllers busy");
   if(rsp_valid&&owner==OWN_NONE)`RELAY_BP_ASSERT_FAIL("response without owner");
   if(cancelled&&candidate_valid)`RELAY_BP_ASSERT_FAIL("cancelled engine exposed candidate");
   if(cancelled&&req_valid)`RELAY_BP_ASSERT_FAIL("cancelled engine issued transaction");
   if(quiescent&&(check_busy||var_busy||conv_busy||relay_busy||req_valid||rsp_valid))`RELAY_BP_ASSERT_FAIL("quiescent engine has outstanding activity");
`endif
  end
 end
endmodule
`undef RELAY_BP_ASSERT_FAIL

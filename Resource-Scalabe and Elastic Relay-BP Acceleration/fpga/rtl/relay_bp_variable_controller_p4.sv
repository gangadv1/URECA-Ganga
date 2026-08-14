`ifdef RELAY_BP_SIM_ASSERT
`define RELAY_BP_ASSERT_FAIL(msg) $fatal(1,msg)
`else
`define RELAY_BP_ASSERT_FAIL(msg)
`endif
// Standalone response-valid P=4 variable-update controller, degree <= 9.
module relay_bp_variable_controller_p4 #(
 parameter int VARIABLES=20,EDGES=76,P=4,MAX_DEGREE=9,
 parameter int VW=(VARIABLES<=1)?1:$clog2(VARIABLES),EW=(EDGES<=1)?1:$clog2(EDGES),PW=$clog2(EDGES+1)
)(input logic clk,rst,start,input logic[31:0]gamma_base,
 output logic busy,done,
 output logic req_valid,req_write,output logic[3:0]req_kind,output logic[P-1:0]req_mask,
 output logic[31:0]req_addr[0:P-1],output logic signed[21:0]req_wdata[0:P-1],input logic req_ready,
 input logic rsp_valid,input logic[3:0]rsp_kind,input logic[P-1:0]rsp_mask,
 input logic[31:0]rsp_addr[0:P-1],input logic signed[21:0]rsp_data[0:P-1],
 output logic variable_done,output logic[VW-1:0]trace_variable,
 output logic signed[17:0]trace_bias,trace_marginal,output logic signed[21:0]trace_sum,
 output logic trace_decision,output logic signed[17:0]trace_weight_contribution,
 output logic signed[31:0]candidate_weight,
 output logic[31:0]cycle_count,read_requests,response_count,write_requests,wait_cycles,
 output logic[31:0]mu_conflicts,nu_conflicts,retry_subsets
);
 localparam K_VP=2,K_VE=3,K_PRIOR=4,K_GAMMA=6,K_NU=8,K_MU=9,K_MARG=10,K_DEC=11;
 typedef enum logic[5:0]{IDLE,VP0_REQ,VP0_WAIT,VP1_REQ,VP1_WAIT,PRIOR_REQ,PRIOR_WAIT,
  MARG_REQ,MARG_WAIT,GAMMA_REQ,GAMMA_WAIT,PERM_REQ,PERM_WAIT,MU_SELECT,MU_REQ,MU_WAIT,
  NEXT_CHUNK,COMPUTE,MARG_WRITE,DEC_WRITE,NU_SELECT,NU_WRITE,NEXT_VARIABLE,DONE_S}state_t;
 state_t state;
 logic[VW-1:0]variable_index;logic[PW-1:0]row_start,row_end,position;
 logic[3:0]degree,chunk_base;logic[P-1:0]chunk_mask,pending_mask,selected_mask;
 logic[EW-1:0]edge_cache[0:MAX_DEGREE-1];logic signed[17:0]mu_cache[0:MAX_DEGREE-1];
 logic signed[17:0]prior_cache,previous_cache,gamma_signext,bias_value,marginal_value;
 logic signed[4:0]gamma_cache;logic signed[21:0]sum_mu;
 logic decision_value,bias_saturated;logic signed[17:0]nu_cache[0:MAX_DEGREE-1];
 integer lane,k,bank,local_index;logic[3:0]seen_banks;logic signed[22:0]wide;logic signed[18:0]nu_wide;
 relay_bp_bias18 bias_u(.physical_prior(prior_cache),.previous_marginal(previous_cache),
  .gamma_q(gamma_cache),.bias(bias_value),.saturated(bias_saturated));
 function automatic signed[17:0]sat18(input signed[22:0]x);if(x>131071)sat18=131071;else if(x< -131072)sat18=-131072;else sat18=x[17:0];endfunction

 always_comb begin
  req_valid=0;req_write=0;req_kind=0;req_mask=0;selected_mask=0;seen_banks=0;
  for(lane=0;lane<P;lane=lane+1)begin req_addr[lane]=0;req_wdata[lane]=0;end
  chunk_mask=0;for(lane=0;lane<P;lane=lane+1)if(position+lane<row_end)chunk_mask[lane]=1;
  // Greedy stable subset: first pending lane for each bank wins.
  for(lane=0;lane<P;lane=lane+1)if(pending_mask[lane])begin
   bank=edge_cache[chunk_base+lane]%P;if(!seen_banks[bank])begin selected_mask[lane]=1;seen_banks[bank]=1;end
  end
  case(state)
   VP0_REQ:begin req_valid=1;req_kind=K_VP;req_mask=1;req_addr[0]=variable_index;end
   VP1_REQ:begin req_valid=1;req_kind=K_VP;req_mask=1;req_addr[0]=variable_index+1;end
   PRIOR_REQ:begin req_valid=1;req_kind=K_PRIOR;req_mask=1;req_addr[0]=variable_index;end
   MARG_REQ:begin req_valid=1;req_kind=K_MARG;req_mask=1;req_addr[0]=variable_index;end
   GAMMA_REQ:begin req_valid=1;req_kind=K_GAMMA;req_mask=1;req_addr[0]=gamma_base+variable_index;end
   PERM_REQ:begin req_valid=1;req_kind=K_VE;req_mask=chunk_mask;for(lane=0;lane<P;lane=lane+1)req_addr[lane]=position+lane;end
   MU_REQ:begin req_valid=1;req_kind=K_MU;req_mask=selected_mask;for(lane=0;lane<P;lane=lane+1)req_addr[lane]=edge_cache[chunk_base+lane];end
   MARG_WRITE:begin req_valid=1;req_write=1;req_kind=K_MARG;req_mask=1;req_addr[0]=variable_index;req_wdata[0]=marginal_value;end
   DEC_WRITE:begin req_valid=1;req_write=1;req_kind=K_DEC;req_mask=1;req_addr[0]=variable_index;req_wdata[0]=decision_value;end
   NU_WRITE:begin req_valid=1;req_write=1;req_kind=K_NU;req_mask=selected_mask;
    for(lane=0;lane<P;lane=lane+1)begin req_addr[lane]=edge_cache[chunk_base+lane];req_wdata[lane]=nu_cache[chunk_base+lane];end end
  endcase
 end

 always_ff @(posedge clk)begin
  if(rst)begin state<=IDLE;busy<=0;done<=0;variable_done<=0;cycle_count<=0;candidate_weight<=0;
   read_requests<=0;response_count<=0;write_requests<=0;wait_cycles<=0;mu_conflicts<=0;nu_conflicts<=0;retry_subsets<=0;end
  else begin
   done<=0;variable_done<=0;if(busy)cycle_count<=cycle_count+1;
   if(req_valid&&!req_ready)wait_cycles<=wait_cycles+1;
   if(req_valid&&req_ready&&!req_write)read_requests<=read_requests+1;
   if(req_valid&&req_ready&&req_write)write_requests<=write_requests+1;
   if(rsp_valid)response_count<=response_count+1;
   case(state)
    IDLE:if(start)begin busy<=1;cycle_count<=0;candidate_weight<=0;read_requests<=0;response_count<=0;
     write_requests<=0;wait_cycles<=0;mu_conflicts<=0;nu_conflicts<=0;retry_subsets<=0;variable_index<=0;state<=VP0_REQ;end
    VP0_REQ:if(req_ready)state<=VP0_WAIT;
    VP0_WAIT:if(rsp_valid)begin if(rsp_kind!=K_VP||rsp_addr[0]!=variable_index)`RELAY_BP_ASSERT_FAIL("variable start pointer response mismatch");row_start<=rsp_data[0][PW-1:0];state<=VP1_REQ;end
    VP1_REQ:if(req_ready)state<=VP1_WAIT;
    VP1_WAIT:if(rsp_valid)begin if(rsp_kind!=K_VP||rsp_addr[0]!=variable_index+1)`RELAY_BP_ASSERT_FAIL("variable end pointer response mismatch");row_end<=rsp_data[0][PW-1:0];degree<=rsp_data[0]-row_start;state<=PRIOR_REQ;end
    PRIOR_REQ:if(req_ready)state<=PRIOR_WAIT;
    PRIOR_WAIT:if(rsp_valid)begin if(rsp_kind!=K_PRIOR||rsp_addr[0]!=variable_index)`RELAY_BP_ASSERT_FAIL("prior response mismatch");prior_cache<=rsp_data[0];state<=MARG_REQ;end
    MARG_REQ:if(req_ready)state<=MARG_WAIT;
    MARG_WAIT:if(rsp_valid)begin if(rsp_kind!=K_MARG||rsp_addr[0]!=variable_index)`RELAY_BP_ASSERT_FAIL("marginal response mismatch");previous_cache<=rsp_data[0];state<=GAMMA_REQ;end
    GAMMA_REQ:if(req_ready)state<=GAMMA_WAIT;
    GAMMA_WAIT:if(rsp_valid)begin if(rsp_kind!=K_GAMMA||rsp_addr[0]!=gamma_base+variable_index)`RELAY_BP_ASSERT_FAIL("gamma response mismatch");gamma_cache<=rsp_data[0][4:0];position<=row_start;chunk_base<=0;sum_mu<=0;state<=PERM_REQ;end
    PERM_REQ:if(req_ready)state<=PERM_WAIT;
    PERM_WAIT:if(rsp_valid)begin
     if(rsp_kind!=K_VE||rsp_mask!=chunk_mask)`RELAY_BP_ASSERT_FAIL("permutation response mismatch");
     for(lane=0;lane<P;lane=lane+1)if(rsp_mask[lane])begin if(rsp_addr[lane]!=position+lane)`RELAY_BP_ASSERT_FAIL("stale permutation response");edge_cache[chunk_base+lane]<=rsp_data[lane][EW-1:0];end
     pending_mask<=rsp_mask;state<=MU_SELECT;
    end
    MU_SELECT:begin seen_banks=0;selected_mask=0;for(lane=0;lane<P;lane=lane+1)if(pending_mask[lane])begin bank=edge_cache[chunk_base+lane]%P;if(!seen_banks[bank])begin selected_mask[lane]=1;seen_banks[bank]=1;end end
     if(selected_mask!=pending_mask)begin mu_conflicts<=mu_conflicts+1;retry_subsets<=retry_subsets+1;end state<=MU_REQ;end
    MU_REQ:if(req_ready)state<=MU_WAIT;
    MU_WAIT:if(rsp_valid)begin
     if(rsp_kind!=K_MU||rsp_mask!=selected_mask)`RELAY_BP_ASSERT_FAIL("mu gather response mismatch");wide=$signed(sum_mu);
     for(lane=0;lane<P;lane=lane+1)if(rsp_mask[lane])begin if(rsp_addr[lane]!=edge_cache[chunk_base+lane])`RELAY_BP_ASSERT_FAIL("mu gather address mismatch");mu_cache[chunk_base+lane]<=rsp_data[lane][17:0];wide=wide+$signed(rsp_data[lane][17:0]);end
     if(wide>2097151)sum_mu<=2097151;else if(wide< -2097152)sum_mu<=-2097152;else sum_mu<=wide[21:0];
     pending_mask<=pending_mask&~rsp_mask;if((pending_mask&~rsp_mask)!=0)state<=MU_SELECT;else state<=NEXT_CHUNK;
    end
    NEXT_CHUNK:if(position+P<row_end)begin position<=position+P;chunk_base<=chunk_base+P;state<=PERM_REQ;end else state<=COMPUTE;
    COMPUTE:begin wide=$signed(bias_value)+$signed(sum_mu);marginal_value<=sat18(wide);decision_value<=sat18(wide)<=0;
     trace_variable<=variable_index;trace_bias<=bias_value;trace_sum<=sum_mu;trace_marginal<=sat18(wide);trace_decision<=sat18(wide)<=0;
     trace_weight_contribution<=(sat18(wide)<=0)?prior_cache:0;if(sat18(wide)<=0)candidate_weight<=candidate_weight+$signed(prior_cache);
     for(k=0;k<MAX_DEGREE;k=k+1)if(k<degree)begin nu_wide=$signed(sat18(wide))-$signed(mu_cache[k]);nu_cache[k]<=sat18(nu_wide);end state<=MARG_WRITE;
    end
    MARG_WRITE:if(req_ready)state<=DEC_WRITE;
    DEC_WRITE:if(req_ready)begin chunk_base<=0;pending_mask<=(degree>=P)?4'b1111:((1<<degree)-1);state<=NU_SELECT;end
    NU_SELECT:begin seen_banks=0;selected_mask=0;for(lane=0;lane<P;lane=lane+1)if(pending_mask[lane])begin bank=edge_cache[chunk_base+lane]%P;if(!seen_banks[bank])begin selected_mask[lane]=1;seen_banks[bank]=1;end end
     if(selected_mask!=pending_mask)begin nu_conflicts<=nu_conflicts+1;retry_subsets<=retry_subsets+1;end state<=NU_WRITE;end
    NU_WRITE:if(req_ready)begin pending_mask<=pending_mask&~selected_mask;if((pending_mask&~selected_mask)!=0)state<=NU_SELECT;
     else if(chunk_base+P<degree)begin chunk_base<=chunk_base+P;pending_mask<=((degree-(chunk_base+P))>=P)?4'b1111:((1<<(degree-(chunk_base+P)))-1);state<=NU_SELECT;end
     else state<=NEXT_VARIABLE;end
    NEXT_VARIABLE:begin variable_done<=1;if(variable_index==VARIABLES-1)state<=DONE_S;else begin variable_index<=variable_index+1;state<=VP0_REQ;end end
    DONE_S:begin busy<=0;done<=1;state<=IDLE;end
    default:state<=IDLE;
   endcase
   if(rsp_valid&&state!=VP0_WAIT&&state!=VP1_WAIT&&state!=PRIOR_WAIT&&state!=MARG_WAIT&&state!=GAMMA_WAIT&&state!=PERM_WAIT&&state!=MU_WAIT)`RELAY_BP_ASSERT_FAIL("response outside wait state");
  end
 end
endmodule
`undef RELAY_BP_ASSERT_FAIL

`ifdef RELAY_BP_SIM_ASSERT
`define RELAY_BP_ASSERT_FAIL(msg) $fatal(1,msg)
`else
`define RELAY_BP_ASSERT_FAIL(msg)
`endif
// Standalone response-valid P=4 sparse H*decision convergence controller.
module relay_bp_convergence_controller_p4 #(
 parameter int CHECKS=12,VARIABLES=20,EDGES=76,P=4,
 parameter int CW=(CHECKS<=1)?1:$clog2(CHECKS),VW=(VARIABLES<=1)?1:$clog2(VARIABLES),PW=$clog2(EDGES+1)
)(input logic clk,rst,start,
 output logic busy,done,converged,output logic[31:0]residual_weight,
 output logic req_valid,req_write,output logic[3:0]req_kind,output logic[P-1:0]req_mask,
 output logic[31:0]req_addr[0:P-1],output logic signed[21:0]req_wdata[0:P-1],input logic req_ready,
 input logic rsp_valid,input logic[3:0]rsp_kind,input logic[P-1:0]rsp_mask,
 input logic[31:0]rsp_addr[0:P-1],input logic signed[21:0]rsp_data[0:P-1],
 output logic check_done,output logic[CW-1:0]trace_check,output logic trace_predicted,trace_expected,trace_mismatch,
 output logic[31:0]cycle_count,read_requests,response_count,wait_cycles,decision_conflicts,retry_subsets
);
 localparam K_CP=0,K_EV=1,K_SYN=5,K_DEC=11;
 typedef enum logic[5:0]{IDLE,CP0_REQ,CP0_WAIT,CP1_REQ,CP1_WAIT,SYN_REQ,SYN_WAIT,
  EDGE_REQ,EDGE_WAIT,DEC_SELECT,DEC_REQ,DEC_WAIT,NEXT_CHUNK,CHECK_FINISH,NEXT_CHECK,DONE_S}state_t;
 state_t state;logic[CW-1:0]check_index;logic[PW-1:0]row_start,row_end,position;
 logic syndrome_bit,parity;logic[P-1:0]chunk_mask,pending_mask,selected_mask;
 logic[VW-1:0]fault_cache[0:P-1];logic[3:0]seen_banks;integer lane,bank;
 always_comb begin
  req_valid=0;req_write=0;req_kind=0;req_mask=0;selected_mask=0;seen_banks=0;
  for(lane=0;lane<P;lane=lane+1)begin req_addr[lane]=0;req_wdata[lane]=0;end
  chunk_mask=0;for(lane=0;lane<P;lane=lane+1)if(position+lane<row_end)chunk_mask[lane]=1;
  for(lane=0;lane<P;lane=lane+1)if(pending_mask[lane])begin bank=fault_cache[lane]%P;if(!seen_banks[bank])begin selected_mask[lane]=1;seen_banks[bank]=1;end end
  case(state)
   CP0_REQ:begin req_valid=1;req_kind=K_CP;req_mask=1;req_addr[0]=check_index;end
   CP1_REQ:begin req_valid=1;req_kind=K_CP;req_mask=1;req_addr[0]=check_index+1;end
   SYN_REQ:begin req_valid=1;req_kind=K_SYN;req_mask=1;req_addr[0]=check_index;end
   EDGE_REQ:begin req_valid=1;req_kind=K_EV;req_mask=chunk_mask;for(lane=0;lane<P;lane=lane+1)req_addr[lane]=position+lane;end
   DEC_REQ:begin req_valid=1;req_kind=K_DEC;req_mask=selected_mask;for(lane=0;lane<P;lane=lane+1)req_addr[lane]=fault_cache[lane];end
  endcase
 end
 always_ff @(posedge clk)begin
  if(rst)begin state<=IDLE;busy<=0;done<=0;converged<=0;residual_weight<=0;check_done<=0;
   cycle_count<=0;read_requests<=0;response_count<=0;wait_cycles<=0;decision_conflicts<=0;retry_subsets<=0;end
  else begin
   done<=0;check_done<=0;if(busy)cycle_count<=cycle_count+1;
   if(req_valid&&!req_ready)wait_cycles<=wait_cycles+1;
   if(req_valid&&req_ready)read_requests<=read_requests+1;if(rsp_valid)response_count<=response_count+1;
   case(state)
    IDLE:if(start)begin busy<=1;converged<=0;residual_weight<=0;cycle_count<=0;read_requests<=0;response_count<=0;
     wait_cycles<=0;decision_conflicts<=0;retry_subsets<=0;check_index<=0;state<=CP0_REQ;end
    CP0_REQ:if(req_ready)state<=CP0_WAIT;
    CP0_WAIT:if(rsp_valid)begin if(rsp_kind!=K_CP||rsp_mask!=1||rsp_addr[0]!=check_index)`RELAY_BP_ASSERT_FAIL("check start pointer response mismatch");row_start<=rsp_data[0][PW-1:0];state<=CP1_REQ;end
    CP1_REQ:if(req_ready)state<=CP1_WAIT;
    CP1_WAIT:if(rsp_valid)begin if(rsp_kind!=K_CP||rsp_mask!=1||rsp_addr[0]!=check_index+1)`RELAY_BP_ASSERT_FAIL("check end pointer response mismatch");row_end<=rsp_data[0][PW-1:0];state<=SYN_REQ;end
    SYN_REQ:if(req_ready)state<=SYN_WAIT;
    SYN_WAIT:if(rsp_valid)begin if(rsp_kind!=K_SYN||rsp_mask!=1||rsp_addr[0]!=check_index)`RELAY_BP_ASSERT_FAIL("syndrome response mismatch");syndrome_bit<=rsp_data[0][0];position<=row_start;parity<=0;state<=EDGE_REQ;end
    EDGE_REQ:if(req_ready)state<=EDGE_WAIT;
    EDGE_WAIT:if(rsp_valid)begin if(rsp_kind!=K_EV||rsp_mask!=chunk_mask)`RELAY_BP_ASSERT_FAIL("edge metadata response mask mismatch");
     for(lane=0;lane<P;lane=lane+1)if(rsp_mask[lane])begin if(rsp_addr[lane]!=position+lane)`RELAY_BP_ASSERT_FAIL("edge metadata address mismatch");fault_cache[lane]<=rsp_data[lane][VW-1:0];end
     pending_mask<=rsp_mask;state<=DEC_SELECT;end
    DEC_SELECT:begin seen_banks=0;selected_mask=0;for(lane=0;lane<P;lane=lane+1)if(pending_mask[lane])begin bank=fault_cache[lane]%P;if(!seen_banks[bank])begin selected_mask[lane]=1;seen_banks[bank]=1;end end
     if(selected_mask!=pending_mask)begin decision_conflicts<=decision_conflicts+1;retry_subsets<=retry_subsets+1;end state<=DEC_REQ;end
    DEC_REQ:if(req_ready)state<=DEC_WAIT;
    DEC_WAIT:if(rsp_valid)begin if(rsp_kind!=K_DEC||rsp_mask!=selected_mask)`RELAY_BP_ASSERT_FAIL("decision response mask mismatch");
     for(lane=0;lane<P;lane=lane+1)if(rsp_mask[lane])begin if(rsp_addr[lane]!=fault_cache[lane])`RELAY_BP_ASSERT_FAIL("decision response address mismatch");parity=parity^rsp_data[lane][0];end
     pending_mask<=pending_mask&~rsp_mask;if((pending_mask&~rsp_mask)!=0)state<=DEC_SELECT;else state<=NEXT_CHUNK;end
    NEXT_CHUNK:if(position+P<row_end)begin position<=position+P;state<=EDGE_REQ;end else state<=CHECK_FINISH;
    CHECK_FINISH:begin check_done<=1;trace_check<=check_index;trace_predicted<=parity;trace_expected<=syndrome_bit;trace_mismatch<=parity^syndrome_bit;
     if(parity^syndrome_bit)residual_weight<=residual_weight+1;state<=NEXT_CHECK;end
    NEXT_CHECK:if(check_index==CHECKS-1)begin converged<=(residual_weight==0);state<=DONE_S;end else begin check_index<=check_index+1;state<=CP0_REQ;end
    DONE_S:begin busy<=0;done<=1;state<=IDLE;end
    default:state<=IDLE;
   endcase
   if(rsp_valid&&state!=CP0_WAIT&&state!=CP1_WAIT&&state!=SYN_WAIT&&state!=EDGE_WAIT&&state!=DEC_WAIT)`RELAY_BP_ASSERT_FAIL("response outside matching wait state");
  end
 end
endmodule
`undef RELAY_BP_ASSERT_FAIL

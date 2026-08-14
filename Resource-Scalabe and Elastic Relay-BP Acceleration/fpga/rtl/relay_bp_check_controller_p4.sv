`ifdef RELAY_BP_SIM_ASSERT
`define RELAY_BP_ASSERT_FAIL(msg) $fatal(1,msg)
`else
`define RELAY_BP_ASSERT_FAIL(msg)
`endif
// Standalone response-valid, two-pass P=4 min-sum check-update controller.
module relay_bp_check_controller_p4 #(
 parameter int CHECKS=12, EDGES=76, P=4,
 parameter int CW=(CHECKS<=1)?1:$clog2(CHECKS),
 parameter int PW=$clog2(EDGES+1)
)(
 input logic clk,rst,start,
 output logic busy,done,
 output logic req_valid,req_write,output logic[3:0]req_kind,
 output logic[P-1:0]req_mask,output logic[31:0]req_addr[0:P-1],
 output logic signed[21:0]req_wdata[0:P-1],input logic req_ready,
 input logic rsp_valid,input logic[3:0]rsp_kind,input logic[P-1:0]rsp_mask,
 input logic[31:0]rsp_addr[0:P-1],input logic signed[21:0]rsp_data[0:P-1],
 output logic[31:0]cycle_count,read_requests,response_count,mu_write_requests,wait_cycles,
 output logic[CW-1:0]debug_check,output logic[PW-1:0]debug_position,
 output logic[5:0]debug_state
);
 localparam K_CP=0,K_SYN=5,K_NU=8,K_MU=9;
 typedef enum logic[5:0]{IDLE,CP_START_REQ,CP_START_WAIT,CP_END_REQ,CP_END_WAIT,
  SYN_REQ,SYN_WAIT,PASS1_INIT,PASS1_REQ,PASS1_WAIT,PASS2_INIT,PASS2_REQ,
  PASS2_WAIT,PASS2_WRITE,NEXT_CHECK,DONE_S}state_t;
 state_t state;
 logic[CW-1:0]check_index;
 logic[PW-1:0]row_start,row_end,position,min1_edge;
 logic syndrome_bit,negative_parity;
 logic[18:0]min1,min2;
 logic[P-1:0]chunk_mask,held_mask;
 logic signed[17:0]held_nu[0:P-1],held_mu[0:P-1];
 integer lane;logic[18:0]magnitude,selected_magnitude;logic outgoing_negative;

 always_comb begin
  req_valid=0;req_write=0;req_kind=0;req_mask=0;
  for(lane=0;lane<P;lane=lane+1)begin req_addr[lane]=0;req_wdata[lane]=0;end
  chunk_mask=0;for(lane=0;lane<P;lane=lane+1)if(position+lane<row_end)chunk_mask[lane]=1;
  case(state)
   CP_START_REQ:begin req_valid=1;req_kind=K_CP;req_mask=1;req_addr[0]=check_index;end
   CP_END_REQ:begin req_valid=1;req_kind=K_CP;req_mask=1;req_addr[0]=check_index+1;end
   SYN_REQ:begin req_valid=1;req_kind=K_SYN;req_mask=1;req_addr[0]=check_index;end
   PASS1_REQ,PASS2_REQ:begin req_valid=1;req_kind=K_NU;req_mask=chunk_mask;
    for(lane=0;lane<P;lane=lane+1)req_addr[lane]=position+lane;end
   PASS2_WRITE:begin req_valid=1;req_write=1;req_kind=K_MU;req_mask=held_mask;
    for(lane=0;lane<P;lane=lane+1)begin req_addr[lane]=position+lane;req_wdata[lane]=held_mu[lane];end end
  endcase
 end

 assign debug_check=check_index;assign debug_position=position;assign debug_state=state;
 always_ff @(posedge clk)begin
  if(rst)begin state<=IDLE;busy<=0;done<=0;cycle_count<=0;read_requests<=0;
   response_count<=0;mu_write_requests<=0;wait_cycles<=0;check_index<=0;end
  else begin
   done<=0;if(busy)cycle_count<=cycle_count+1;
   if(req_valid&&!req_ready)wait_cycles<=wait_cycles+1;
   if(req_valid&&req_ready&&!req_write)read_requests<=read_requests+1;
   if(req_valid&&req_ready&&req_write)mu_write_requests<=mu_write_requests+1;
   if(rsp_valid)response_count<=response_count+1;
   case(state)
    IDLE:if(start)begin busy<=1;cycle_count<=0;read_requests<=0;response_count<=0;
      mu_write_requests<=0;wait_cycles<=0;check_index<=0;state<=CP_START_REQ;end
    CP_START_REQ:if(req_ready)state<=CP_START_WAIT;
    CP_START_WAIT:if(rsp_valid)begin
      if(rsp_kind!=K_CP||!rsp_mask[0]||rsp_addr[0]!=check_index)`RELAY_BP_ASSERT_FAIL("stale start pointer response");
      row_start<=rsp_data[0][PW-1:0];state<=CP_END_REQ;end
    CP_END_REQ:if(req_ready)state<=CP_END_WAIT;
    CP_END_WAIT:if(rsp_valid)begin
      if(rsp_kind!=K_CP||!rsp_mask[0]||rsp_addr[0]!=check_index+1)`RELAY_BP_ASSERT_FAIL("stale end pointer response");
      row_end<=rsp_data[0][PW-1:0];state<=SYN_REQ;end
    SYN_REQ:if(req_ready)state<=SYN_WAIT;
    SYN_WAIT:if(rsp_valid)begin
      if(rsp_kind!=K_SYN||!rsp_mask[0]||rsp_addr[0]!=check_index)`RELAY_BP_ASSERT_FAIL("stale syndrome response");
      syndrome_bit<=rsp_data[0][0];state<=PASS1_INIT;end
    PASS1_INIT:begin position<=row_start;min1<=19'h3ffff;min2<=19'h3ffff;
      min1_edge<=row_start;negative_parity<=0;state<=PASS1_REQ;end
    PASS1_REQ:if(req_ready)state<=PASS1_WAIT;
    PASS1_WAIT:if(rsp_valid)begin
      if(rsp_kind!=K_NU||rsp_mask!=chunk_mask)`RELAY_BP_ASSERT_FAIL("pass1 response mask/kind mismatch");
      for(lane=0;lane<P;lane=lane+1)if(rsp_mask[lane])begin
       if(rsp_addr[lane]!=position+lane)`RELAY_BP_ASSERT_FAIL("pass1 stale address");
       magnitude=rsp_data[lane][17] ? -$signed({rsp_data[lane][17],rsp_data[lane][17:0]}):{1'b0,rsp_data[lane][17:0]};
       negative_parity=negative_parity^rsp_data[lane][17];
       if(magnitude<min1)begin min2=min1;min1=magnitude;min1_edge=position+lane;end
       else if(magnitude<min2)min2=magnitude;
      end
      if(position+P>=row_end)state<=PASS2_INIT;else begin position<=position+P;state<=PASS1_REQ;end
    end
    PASS2_INIT:begin position<=row_start;state<=PASS2_REQ;end
    PASS2_REQ:if(req_ready)state<=PASS2_WAIT;
    PASS2_WAIT:if(rsp_valid)begin
      if(rsp_kind!=K_NU||rsp_mask!=chunk_mask)`RELAY_BP_ASSERT_FAIL("pass2 response mask/kind mismatch");
      held_mask<=rsp_mask;
      for(lane=0;lane<P;lane=lane+1)if(rsp_mask[lane])begin
       if(rsp_addr[lane]!=position+lane)`RELAY_BP_ASSERT_FAIL("pass2 stale address");
       held_nu[lane]<=rsp_data[lane][17:0];
       if(row_end-row_start==1)held_mu[lane]<=syndrome_bit ? -18'sd131071:18'sd131071;
       else begin selected_magnitude=(position+lane==min1_edge)?min2:min1;
        outgoing_negative=syndrome_bit^negative_parity^rsp_data[lane][17];
        if(outgoing_negative)held_mu[lane]<=selected_magnitude>=131072 ? -18'sd131072:-$signed(selected_magnitude[17:0]);
        else held_mu[lane]<=selected_magnitude>131071 ? 18'sd131071:$signed(selected_magnitude[17:0]);
       end
      end state<=PASS2_WRITE;
    end
    PASS2_WRITE:if(req_ready)begin
      if(position+P>=row_end)state<=NEXT_CHECK;else begin position<=position+P;state<=PASS2_REQ;end
    end
    NEXT_CHECK:begin if(check_index==CHECKS-1)state<=DONE_S;else begin check_index<=check_index+1;state<=CP_START_REQ;end end
    DONE_S:begin busy<=0;done<=1;state<=IDLE;end
    default:state<=IDLE;
   endcase
   // No response is legal outside a matching WAIT state.
   if(rsp_valid&&state!=CP_START_WAIT&&state!=CP_END_WAIT&&state!=SYN_WAIT&&state!=PASS1_WAIT&&state!=PASS2_WAIT)
    `RELAY_BP_ASSERT_FAIL("response arrived outside wait state");
  end
 end
endmodule
`undef RELAY_BP_ASSERT_FAIL

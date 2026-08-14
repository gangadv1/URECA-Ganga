`ifdef RELAY_BP_SIM_ASSERT
`define RELAY_BP_ASSERT_FAIL(msg) $fatal(1,msg)
`else
`define RELAY_BP_ASSERT_FAIL(msg)
`endif
// Standalone canonical relay-leg initialization through response-valid memory.
module relay_bp_relay_init_controller_p4 #(
 parameter int VARIABLES=20,EDGES=76,P=4,
 parameter int VW=(VARIABLES<=1)?1:$clog2(VARIABLES),EW=(EDGES<=1)?1:$clog2(EDGES)
)(input logic clk,rst,start,
 output logic busy,done,mu_valid,leg_state_reset,
 output logic req_valid,req_write,output logic[3:0]req_kind,output logic[P-1:0]req_mask,
 output logic[31:0]req_addr[0:P-1],output logic signed[21:0]req_wdata[0:P-1],input logic req_ready,
 input logic rsp_valid,input logic[3:0]rsp_kind,input logic[P-1:0]rsp_mask,
 input logic[31:0]rsp_addr[0:P-1],input logic signed[21:0]rsp_data[0:P-1],
 output logic[31:0]cycle_count,read_requests,response_count,write_requests,wait_cycles,
 output logic[31:0]prior_conflicts,nu_conflicts,retry_subsets,gamma_writes
);
 localparam K_EV=1,K_PRIOR=4,K_NU=8;
 typedef enum logic[3:0]{IDLE,EDGE_REQ,EDGE_WAIT,PRIOR_SELECT,PRIOR_REQ,PRIOR_WAIT,
  NU_SELECT,NU_WRITE,NEXT_EDGE_CHUNK,DONE_S}state_t;
 state_t state;logic[EW-1:0]position;logic[VW-1:0]variable_index;
 logic[P-1:0]chunk_mask,pending_mask,selected_mask,issued_mask;logic[VW-1:0]fault_cache[0:P-1];
 logic signed[17:0]prior_cache[0:P-1];
 logic[3:0]seen_banks;integer lane,bank;
 always_comb begin
  req_valid=0;req_write=0;req_kind=0;req_mask=0;selected_mask=0;seen_banks=0;
  for(lane=0;lane<P;lane=lane+1)begin req_addr[lane]=0;req_wdata[lane]=0;end
  chunk_mask=0;for(lane=0;lane<P;lane=lane+1)if(position+lane<EDGES)chunk_mask[lane]=1;
  if(state==PRIOR_SELECT||state==PRIOR_REQ)for(lane=0;lane<P;lane=lane+1)if(pending_mask[lane])begin
   bank=fault_cache[lane]%P;if(!seen_banks[bank])begin selected_mask[lane]=1;seen_banks[bank]=1;end end
  case(state)
   EDGE_REQ:begin req_valid=1;req_kind=K_EV;req_mask=chunk_mask;for(lane=0;lane<P;lane=lane+1)req_addr[lane]=position+lane;end
   PRIOR_REQ:begin req_valid=1;req_kind=K_PRIOR;req_mask=selected_mask;for(lane=0;lane<P;lane=lane+1)req_addr[lane]=fault_cache[lane];end
   NU_WRITE:begin req_valid=1;req_write=1;req_kind=K_NU;req_mask=pending_mask;
    for(lane=0;lane<P;lane=lane+1)begin req_addr[lane]=position+lane;req_wdata[lane]=prior_cache[lane];end end
  endcase
 end
 always_ff @(posedge clk)begin
  if(rst)begin state<=IDLE;busy<=0;done<=0;mu_valid<=0;leg_state_reset<=0;cycle_count<=0;
   read_requests<=0;response_count<=0;write_requests<=0;wait_cycles<=0;prior_conflicts<=0;nu_conflicts<=0;retry_subsets<=0;gamma_writes<=0;end
  else begin
   done<=0;if(busy)cycle_count<=cycle_count+1;
   if(req_valid&&!req_ready)wait_cycles<=wait_cycles+1;
   if(req_valid&&req_ready&&!req_write)read_requests<=read_requests+1;
   if(req_valid&&req_ready&&req_write)write_requests<=write_requests+1;
   if(rsp_valid)response_count<=response_count+1;
   case(state)
    IDLE:if(start)begin busy<=1;mu_valid<=0;leg_state_reset<=0;cycle_count<=0;read_requests<=0;response_count<=0;
     write_requests<=0;wait_cycles<=0;prior_conflicts<=0;nu_conflicts<=0;retry_subsets<=0;gamma_writes<=0;position<=0;state<=EDGE_REQ;end
    EDGE_REQ:if(req_ready)state<=EDGE_WAIT;
    EDGE_WAIT:if(rsp_valid)begin if(rsp_kind!=K_EV||rsp_mask!=chunk_mask)`RELAY_BP_ASSERT_FAIL("edge metadata response mismatch");
     for(lane=0;lane<P;lane=lane+1)if(rsp_mask[lane])begin if(rsp_addr[lane]!=position+lane)`RELAY_BP_ASSERT_FAIL("edge response address mismatch");fault_cache[lane]<=rsp_data[lane][VW-1:0];end
     pending_mask<=rsp_mask;state<=PRIOR_SELECT;end
    PRIOR_SELECT:begin
     if(selected_mask!=pending_mask)begin prior_conflicts<=prior_conflicts+1;retry_subsets<=retry_subsets+1;end state<=PRIOR_REQ;end
    PRIOR_REQ:if(req_ready)begin issued_mask<=selected_mask;state<=PRIOR_WAIT;end
    PRIOR_WAIT:if(rsp_valid)begin if(rsp_kind!=K_PRIOR||rsp_mask!=issued_mask)`RELAY_BP_ASSERT_FAIL("prior gather response mismatch");
     for(lane=0;lane<P;lane=lane+1)if(rsp_mask[lane])begin if(rsp_addr[lane]!=fault_cache[lane])`RELAY_BP_ASSERT_FAIL("prior gather address mismatch");prior_cache[lane]<=rsp_data[lane][17:0];end
     pending_mask<=pending_mask&~rsp_mask;if((pending_mask&~rsp_mask)!=0)state<=PRIOR_SELECT;else begin pending_mask<=chunk_mask;state<=NU_SELECT;end end
    NU_SELECT:state<=NU_WRITE;
    NU_WRITE:if(req_ready)begin pending_mask<=0;state<=NEXT_EDGE_CHUNK;end
    NEXT_EDGE_CHUNK:if(position+P<EDGES)begin position<=position+P;state<=EDGE_REQ;end else begin leg_state_reset<=1;state<=DONE_S;end
    DONE_S:begin busy<=0;done<=1;state<=IDLE;end
    default:state<=IDLE;
   endcase
   if(req_valid&&req_write&&(req_kind==K_PRIOR||req_kind==10))`RELAY_BP_ASSERT_FAIL("relay init attempted prior/marginal write");
   if(rsp_valid&&state!=EDGE_WAIT&&state!=PRIOR_WAIT)`RELAY_BP_ASSERT_FAIL("response outside matching wait state");
  end
 end
endmodule
`undef RELAY_BP_ASSERT_FAIL

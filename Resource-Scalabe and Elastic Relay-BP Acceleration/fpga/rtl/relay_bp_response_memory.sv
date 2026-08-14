// Verification-oriented sparse-graph memory service. The decoder sees only
// registered request/response transactions; storage is generic synthesizable RTL.
module relay_bp_response_memory #(
 parameter int C=1,V=1,E=1,L=2,P=4,
 parameter int EW=(E<=1)?1:$clog2(E),VW=(V<=1)?1:$clog2(V),CW=(C<=1)?1:$clog2(C),
 parameter int PW=$clog2(E+1), STALL_PERIOD=0
)(
 input logic clk,
 input logic cfg_we,input logic[3:0]cfg_kind,input logic[31:0]cfg_addr,input logic signed[31:0]cfg_data,
 input logic req_valid,input logic req_write,input logic[3:0]req_kind,
 input logic[P-1:0]req_mask,input logic[31:0]req_addr[0:P-1],
 input logic signed[21:0]req_wdata[0:P-1],output logic req_ready,
 output logic rsp_valid,output logic[3:0]rsp_kind,output logic[P-1:0]rsp_mask,
 output logic[31:0]rsp_addr[0:P-1],output logic signed[21:0]rsp_data[0:P-1],
 output logic[31:0]read_conflicts,output logic[31:0]write_conflicts
);
 localparam K_CP=0,K_EV=1,K_VP=2,K_VE=3,K_PRIOR=4,K_SYN=5,K_GAMMA=6,K_LIM=7,
            K_NU=8,K_MU=9,K_MARG=10,K_DEC=11,K_NEXT_GAMMA=12;
 logic[PW-1:0] cp[0:C],vp[0:V];logic[VW-1:0]ev[0:E-1];logic[EW-1:0]ve[0:E-1];
 logic signed[17:0]prior[0:V-1],nu[0:E-1],mu[0:E-1],marg[0:V-1];
 logic signed[4:0]gamma[0:L*V-1],next_gamma[0:L*V-1];logic syndrome[0:C-1],decision[0:V-1];logic[15:0]limit[0:L-1];
 integer i,j;logic conflict;logic[31:0]service_cycle;
 always_comb begin
  conflict=0;
  // Edge/node message arrays are four-bank logical memories. Scalar tables are serialized.
  if(req_kind==K_NU||req_kind==K_MU||req_kind==K_MARG||req_kind==K_DEC||req_kind==K_PRIOR||req_kind==K_GAMMA||req_kind==K_NEXT_GAMMA)
   for(i=0;i<P;i=i+1)for(j=i+1;j<P;j=j+1)
    if(req_mask[i]&&req_mask[j]&&(req_addr[i]%P)==(req_addr[j]%P))conflict=1;
  req_ready=!conflict&&((STALL_PERIOD==0)||(service_cycle%STALL_PERIOD!=STALL_PERIOD-1));
 end
 always_ff @(posedge clk) begin
  service_cycle<=service_cycle+1;
  rsp_valid<=req_valid&&req_ready&&!req_write;rsp_kind<=req_kind;rsp_mask<=req_mask;
  if(req_valid&&!req_ready)begin if(req_write)write_conflicts<=write_conflicts+1;else read_conflicts<=read_conflicts+1;end
  if(cfg_we)case(cfg_kind)
   K_CP:cp[cfg_addr]<=cfg_data[PW-1:0];K_EV:ev[cfg_addr]<=cfg_data[VW-1:0];
   K_VP:vp[cfg_addr]<=cfg_data[PW-1:0];K_VE:ve[cfg_addr]<=cfg_data[EW-1:0];
   K_PRIOR:prior[cfg_addr]<=cfg_data[17:0];K_SYN:syndrome[cfg_addr]<=cfg_data[0];
   K_GAMMA:gamma[cfg_addr]<=cfg_data[4:0];K_LIM:limit[cfg_addr]<=cfg_data[15:0];
   K_NU:nu[cfg_addr]<=cfg_data[17:0];K_MU:mu[cfg_addr]<=cfg_data[17:0];
   K_MARG:marg[cfg_addr]<=cfg_data[17:0];K_DEC:decision[cfg_addr]<=cfg_data[0];
   K_NEXT_GAMMA:next_gamma[cfg_addr]<=cfg_data[4:0];
  endcase
  if(req_valid&&req_ready)for(i=0;i<P;i=i+1)if(req_mask[i])begin
   rsp_addr[i]<=req_addr[i];
   if(req_write)case(req_kind)
    K_NU:nu[req_addr[i]]<=req_wdata[i][17:0];K_MU:mu[req_addr[i]]<=req_wdata[i][17:0];
    K_MARG:marg[req_addr[i]]<=req_wdata[i][17:0];K_DEC:decision[req_addr[i]]<=req_wdata[i][0];
    K_GAMMA:gamma[req_addr[i]]<=req_wdata[i][4:0];
   endcase else case(req_kind)
    K_CP:rsp_data[i]<=$signed({1'b0,cp[req_addr[i]]});K_EV:rsp_data[i]<=$signed({1'b0,ev[req_addr[i]]});
    K_VP:rsp_data[i]<=$signed({1'b0,vp[req_addr[i]]});K_VE:rsp_data[i]<=$signed({1'b0,ve[req_addr[i]]});
    K_PRIOR:rsp_data[i]<=$signed(prior[req_addr[i]]);K_SYN:rsp_data[i]<=syndrome[req_addr[i]];
    K_GAMMA:rsp_data[i]<=$signed(gamma[req_addr[i]]);K_LIM:rsp_data[i]<=limit[req_addr[i]];
    K_NU:rsp_data[i]<=$signed(nu[req_addr[i]]);K_MU:rsp_data[i]<=$signed(mu[req_addr[i]]);
    K_MARG:rsp_data[i]<=$signed(marg[req_addr[i]]);K_DEC:rsp_data[i]<=decision[req_addr[i]];
    K_NEXT_GAMMA:rsp_data[i]<=$signed(next_gamma[req_addr[i]]);
   endcase
  end
 end
 initial begin read_conflicts=0;write_conflicts=0;rsp_valid=0;service_cycle=0;end
endmodule

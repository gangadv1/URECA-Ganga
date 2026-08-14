// Synthesis-oriented four-bank memory fabric for the Relay-BP P=4 controllers.
// Logical address a maps to bank a[1:0], row a>>2. Controllers retry conflicts.
// Gamma coefficients enter through the engine's external source handshake and
// are written into active gamma RAM; no future-vector fixture is stored here.
module relay_bp_memory_fabric_p4 #(
 parameter int C=1,V=1,E=1,L=2,P=4,STALL_PERIOD=0,
 parameter int PW=$clog2(E+1),VW=(V<=1)?1:$clog2(V),EW=(E<=1)?1:$clog2(E),
 parameter int CD=(C+P-1)/P,VD=(V+P-1)/P,ED=(E+P-1)/P,
 parameter CP_INIT="",EV_B0_INIT="",EV_B1_INIT="",EV_B2_INIT="",EV_B3_INIT="",
 parameter VP_INIT="",VE_B0_INIT="",VE_B1_INIT="",VE_B2_INIT="",VE_B3_INIT="",
 parameter PRIOR_B0_INIT="",PRIOR_B1_INIT="",PRIOR_B2_INIT="",PRIOR_B3_INIT="",
 parameter MARG_B0_INIT="",MARG_B1_INIT="",MARG_B2_INIT="",MARG_B3_INIT="",
 parameter SYN_B0_INIT="",SYN_B1_INIT="",SYN_B2_INIT="",SYN_B3_INIT=""
)(input logic clk,
 input logic cfg_we,input logic[3:0]cfg_kind,input logic[31:0]cfg_addr,input logic signed[31:0]cfg_data,
 input logic req_valid,input logic req_write,input logic[3:0]req_kind,input logic[P-1:0]req_mask,
 input logic[31:0]req_addr[0:P-1],input logic signed[21:0]req_wdata[0:P-1],output logic req_ready,
 output logic rsp_valid,output logic[3:0]rsp_kind,output logic[P-1:0]rsp_mask,
 output logic[31:0]rsp_addr[0:P-1],output logic signed[21:0]rsp_data[0:P-1],
 output logic[31:0]read_conflicts,write_conflicts,
 input logic correction_req,input logic[31:0]correction_word,output logic correction_ready,
 output logic correction_rsp_valid,output logic[P-1:0]correction_bits,correction_mask);
 localparam K_CP=0,K_EV=1,K_VP=2,K_VE=3,K_PRIOR=4,K_SYN=5,K_GAMMA=6,K_LIM=7,K_NU=8,K_MU=9,K_MARG=10,K_DEC=11;
 logic[15:0]limit[0:L-1];
 logic conflict;logic[31:0]service_cycle;integer i;
 logic[P-1:0]nu_rd_en,nu_wr_en,mu_rd_en,mu_wr_en;logic[31:0]nu_rd_row[0:P-1],nu_wr_row[0:P-1],mu_rd_row[0:P-1],mu_wr_row[0:P-1];
 logic[17:0]nu_rd_data[0:P-1],nu_wr_data[0:P-1],mu_rd_data[0:P-1],mu_wr_data[0:P-1];logic signed[21:0]rsp_data_reg[0:P-1];
 relay_bp_four_bank_ram #(.WIDTH(18),.DEPTH(ED)) nu_memory(.clk,.rd_en(nu_rd_en),.rd_row(nu_rd_row),.rd_data(nu_rd_data),.wr_en(nu_wr_en),.wr_row(nu_wr_row),.wr_data(nu_wr_data));
 relay_bp_four_bank_ram #(.WIDTH(18),.DEPTH(ED)) mu_memory(.clk,.rd_en(mu_rd_en),.rd_row(mu_rd_row),.rd_data(mu_rd_data),.wr_en(mu_wr_en),.wr_row(mu_wr_row),.wr_data(mu_wr_data));
 logic[P-1:0]prior_rd_en,prior_wr_en,marg_rd_en,marg_wr_en,gamma_rd_en,gamma_wr_en,dec_rd_en,dec_wr_en;
 logic[31:0]prior_rd_row[0:P-1],prior_wr_row[0:P-1],marg_rd_row[0:P-1],marg_wr_row[0:P-1],gamma_rd_row[0:P-1],gamma_wr_row[0:P-1],dec_rd_row[0:P-1],dec_wr_row[0:P-1];
 logic[17:0]prior_rd_data[0:P-1],prior_wr_data[0:P-1],marg_rd_data[0:P-1],marg_wr_data[0:P-1];logic[4:0]gamma_rd_data[0:P-1],gamma_wr_data[0:P-1];logic[0:0]dec_rd_data[0:P-1],dec_wr_data[0:P-1];
 relay_bp_four_bank_ram #(.WIDTH(18),.DEPTH(VD),.INIT0(PRIOR_B0_INIT),.INIT1(PRIOR_B1_INIT),.INIT2(PRIOR_B2_INIT),.INIT3(PRIOR_B3_INIT)) prior_memory(.clk,.rd_en(prior_rd_en),.rd_row(prior_rd_row),.rd_data(prior_rd_data),.wr_en(prior_wr_en),.wr_row(prior_wr_row),.wr_data(prior_wr_data));
 relay_bp_four_bank_ram #(.WIDTH(18),.DEPTH(VD),.INIT0(MARG_B0_INIT),.INIT1(MARG_B1_INIT),.INIT2(MARG_B2_INIT),.INIT3(MARG_B3_INIT)) marginal_memory(.clk,.rd_en(marg_rd_en),.rd_row(marg_rd_row),.rd_data(marg_rd_data),.wr_en(marg_wr_en),.wr_row(marg_wr_row),.wr_data(marg_wr_data));
 relay_bp_four_bank_ram #(.WIDTH(5),.DEPTH(VD)) gamma_memory(.clk,.rd_en(gamma_rd_en),.rd_row(gamma_rd_row),.rd_data(gamma_rd_data),.wr_en(gamma_wr_en),.wr_row(gamma_wr_row),.wr_data(gamma_wr_data));
 relay_bp_four_bank_ram #(.WIDTH(1),.DEPTH(VD)) decision_memory(.clk,.rd_en(dec_rd_en),.rd_row(dec_rd_row),.rd_data(dec_rd_data),.wr_en(dec_wr_en),.wr_row(dec_wr_row),.wr_data(dec_wr_data));
 logic[P-1:0]ev_rd_en,ev_wr_en,ve_rd_en,ve_wr_en;
 logic[31:0]ev_rd_row[0:P-1],ev_wr_row[0:P-1],ve_rd_row[0:P-1],ve_wr_row[0:P-1];
 logic[VW-1:0]ev_rd_data[0:P-1],ev_wr_data[0:P-1];logic[EW-1:0]ve_rd_data[0:P-1],ve_wr_data[0:P-1];
 relay_bp_four_bank_ram #(.WIDTH(VW),.DEPTH(ED),.INIT0(EV_B0_INIT),.INIT1(EV_B1_INIT),.INIT2(EV_B2_INIT),.INIT3(EV_B3_INIT)) edge_fault_memory(.clk,.rd_en(ev_rd_en),.rd_row(ev_rd_row),.rd_data(ev_rd_data),.wr_en(ev_wr_en),.wr_row(ev_wr_row),.wr_data(ev_wr_data));
 relay_bp_four_bank_ram #(.WIDTH(EW),.DEPTH(ED),.INIT0(VE_B0_INIT),.INIT1(VE_B1_INIT),.INIT2(VE_B2_INIT),.INIT3(VE_B3_INIT)) permutation_memory(.clk,.rd_en(ve_rd_en),.rd_row(ve_rd_row),.rd_data(ve_rd_data),.wr_en(ve_wr_en),.wr_row(ve_wr_row),.wr_data(ve_wr_data));
 localparam int CAW=(C+1<=1)?1:$clog2(C+1),VAW=(V+1<=1)?1:$clog2(V+1);
 logic cp_rd_en,cp_wr_en,vp_rd_en,vp_wr_en;logic[CAW-1:0]cp_rd_addr,cp_wr_addr;logic[VAW-1:0]vp_rd_addr,vp_wr_addr;logic[PW-1:0]cp_rd_data,cp_wr_data,vp_rd_data,vp_wr_data;logic cp_rsp_unused,vp_rsp_unused;
 relay_bp_scalar_sync_ram #(.WIDTH(PW),.DEPTH(C+1),.INIT_FILE(CP_INIT)) check_pointer_memory(.clk,.rd_req(cp_rd_en),.rd_addr(cp_rd_addr),.rsp_valid(cp_rsp_unused),.rsp_data(cp_rd_data),.wr_req(cp_wr_en),.wr_addr(cp_wr_addr),.wr_data(cp_wr_data));
 relay_bp_scalar_sync_ram #(.WIDTH(PW),.DEPTH(V+1),.INIT_FILE(VP_INIT)) variable_pointer_memory(.clk,.rd_req(vp_rd_en),.rd_addr(vp_rd_addr),.rsp_valid(vp_rsp_unused),.rsp_data(vp_rd_data),.wr_req(vp_wr_en),.wr_addr(vp_wr_addr),.wr_data(vp_wr_data));
 logic[P-1:0]syn_rd_en,syn_wr_en;logic[31:0]syn_rd_row[0:P-1],syn_wr_row[0:P-1];logic[0:0]syn_rd_data[0:P-1],syn_wr_data[0:P-1];
 relay_bp_four_bank_ram #(.WIDTH(1),.DEPTH(CD),.INIT0(SYN_B0_INIT),.INIT1(SYN_B1_INIT),.INIT2(SYN_B2_INIT),.INIT3(SYN_B3_INIT)) syndrome_memory(.clk,.rd_en(syn_rd_en),.rd_row(syn_rd_row),.rd_data(syn_rd_data),.wr_en(syn_wr_en),.wr_row(syn_wr_row),.wr_data(syn_wr_data));
 function automatic logic gather_kind(input logic[3:0]k);begin
  gather_kind=(k==K_EV)||(k==K_VE)||(k==K_PRIOR)||(k==K_SYN)||(k==K_GAMMA)||(k==K_NU)||(k==K_MU)||(k==K_MARG)||(k==K_DEC);
 end endfunction
 // Fixed P=4 priority-independent conflict check. Controllers select retries.
 always_comb begin
  conflict=1'b0;
  if(gather_kind(req_kind))begin
   if(req_mask[0]&&req_mask[1]&&req_addr[0][1:0]==req_addr[1][1:0])conflict=1;
   if(req_mask[0]&&req_mask[2]&&req_addr[0][1:0]==req_addr[2][1:0])conflict=1;
   if(req_mask[0]&&req_mask[3]&&req_addr[0][1:0]==req_addr[3][1:0])conflict=1;
   if(req_mask[1]&&req_mask[2]&&req_addr[1][1:0]==req_addr[2][1:0])conflict=1;
   if(req_mask[1]&&req_mask[3]&&req_addr[1][1:0]==req_addr[3][1:0])conflict=1;
   if(req_mask[2]&&req_mask[3]&&req_addr[2][1:0]==req_addr[3][1:0])conflict=1;
  end
  req_ready=!conflict&&((STALL_PERIOD==0)||(service_cycle%STALL_PERIOD!=STALL_PERIOD-1));
  correction_ready=!req_valid;
 end
 always_comb begin
  nu_rd_en='0;nu_wr_en='0;mu_rd_en='0;mu_wr_en='0;prior_rd_en='0;prior_wr_en='0;marg_rd_en='0;marg_wr_en='0;gamma_rd_en='0;gamma_wr_en='0;dec_rd_en='0;dec_wr_en='0;ev_rd_en='0;ev_wr_en='0;ve_rd_en='0;ve_wr_en='0;syn_rd_en='0;syn_wr_en='0;
  cp_rd_en=0;cp_wr_en=0;vp_rd_en=0;vp_wr_en=0;cp_rd_addr=0;cp_wr_addr=0;vp_rd_addr=0;vp_wr_addr=0;cp_wr_data=0;vp_wr_data=0;
  for(i=0;i<P;i=i+1)begin
   nu_rd_row[i]=0;nu_wr_row[i]=0;mu_rd_row[i]=0;mu_wr_row[i]=0;nu_wr_data[i]=0;mu_wr_data[i]=0;
   prior_rd_row[i]=0;prior_wr_row[i]=0;marg_rd_row[i]=0;marg_wr_row[i]=0;gamma_rd_row[i]=0;gamma_wr_row[i]=0;dec_rd_row[i]=0;dec_wr_row[i]=0;
   prior_wr_data[i]=0;marg_wr_data[i]=0;gamma_wr_data[i]=0;dec_wr_data[i]=0;
   ev_rd_row[i]=0;ev_wr_row[i]=0;ve_rd_row[i]=0;ve_wr_row[i]=0;ev_wr_data[i]=0;ve_wr_data[i]=0;
   syn_rd_row[i]=0;syn_wr_row[i]=0;syn_wr_data[i]=0;
  end
  if(cfg_we&&(cfg_kind==K_CP||cfg_kind==K_VP||cfg_kind==K_SYN))case(cfg_kind)
   K_CP:begin cp_wr_en=1;cp_wr_addr=cfg_addr[CAW-1:0];cp_wr_data=cfg_data[PW-1:0];end
   K_VP:begin vp_wr_en=1;vp_wr_addr=cfg_addr[VAW-1:0];vp_wr_data=cfg_data[PW-1:0];end
   K_SYN:begin syn_wr_en[cfg_addr[1:0]]=1;syn_wr_row[cfg_addr[1:0]]=cfg_addr>>2;syn_wr_data[cfg_addr[1:0]]=cfg_data[0];end
  endcase
  else if(req_valid&&req_ready&&!req_write&&(req_kind==K_CP||req_kind==K_VP||req_kind==K_SYN))begin
   if(req_kind==K_CP)begin cp_rd_en=req_mask[0];cp_rd_addr=req_addr[0][CAW-1:0];end
   else if(req_kind==K_VP)begin vp_rd_en=req_mask[0];vp_rd_addr=req_addr[0][VAW-1:0];end
   else for(i=0;i<P;i=i+1)if(req_mask[i])begin syn_rd_en[req_addr[i][1:0]]=1;syn_rd_row[req_addr[i][1:0]]=req_addr[i]>>2;end
  end
  if(cfg_we&&(cfg_kind==K_EV||cfg_kind==K_VE))begin
   if(cfg_kind==K_EV)begin ev_wr_en[cfg_addr[1:0]]=1;ev_wr_row[cfg_addr[1:0]]=cfg_addr>>2;ev_wr_data[cfg_addr[1:0]]=cfg_data[VW-1:0];end
   else begin ve_wr_en[cfg_addr[1:0]]=1;ve_wr_row[cfg_addr[1:0]]=cfg_addr>>2;ve_wr_data[cfg_addr[1:0]]=cfg_data[EW-1:0];end
  end else if(req_valid&&req_ready&&!req_write&&(req_kind==K_EV||req_kind==K_VE))for(i=0;i<P;i=i+1)if(req_mask[i])begin
   if(req_kind==K_EV)begin ev_rd_en[req_addr[i][1:0]]=1;ev_rd_row[req_addr[i][1:0]]=req_addr[i]>>2;end
   else begin ve_rd_en[req_addr[i][1:0]]=1;ve_rd_row[req_addr[i][1:0]]=req_addr[i]>>2;end
  end
  if(cfg_we&&(cfg_kind==K_NU||cfg_kind==K_MU))begin
   if(cfg_kind==K_NU)begin nu_wr_en[cfg_addr[1:0]]=1;nu_wr_row[cfg_addr[1:0]]=cfg_addr>>2;nu_wr_data[cfg_addr[1:0]]=cfg_data[17:0];end
   else begin mu_wr_en[cfg_addr[1:0]]=1;mu_wr_row[cfg_addr[1:0]]=cfg_addr>>2;mu_wr_data[cfg_addr[1:0]]=cfg_data[17:0];end
  end else if(req_valid&&req_ready&&(req_kind==K_NU||req_kind==K_MU))for(i=0;i<P;i=i+1)if(req_mask[i])begin
   if(req_kind==K_NU)begin
    if(req_write)begin nu_wr_en[req_addr[i][1:0]]=1;nu_wr_row[req_addr[i][1:0]]=req_addr[i]>>2;nu_wr_data[req_addr[i][1:0]]=req_wdata[i][17:0];end
    else begin nu_rd_en[req_addr[i][1:0]]=1;nu_rd_row[req_addr[i][1:0]]=req_addr[i]>>2;end
   end else begin
    if(req_write)begin mu_wr_en[req_addr[i][1:0]]=1;mu_wr_row[req_addr[i][1:0]]=req_addr[i]>>2;mu_wr_data[req_addr[i][1:0]]=req_wdata[i][17:0];end
    else begin mu_rd_en[req_addr[i][1:0]]=1;mu_rd_row[req_addr[i][1:0]]=req_addr[i]>>2;end
   end
  end
  if(cfg_we&&(cfg_kind==K_PRIOR||cfg_kind==K_MARG||cfg_kind==K_GAMMA||cfg_kind==K_DEC))begin
   case(cfg_kind)
    K_PRIOR:begin prior_wr_en[cfg_addr[1:0]]=1;prior_wr_row[cfg_addr[1:0]]=cfg_addr>>2;prior_wr_data[cfg_addr[1:0]]=cfg_data[17:0];end
    K_MARG:begin marg_wr_en[cfg_addr[1:0]]=1;marg_wr_row[cfg_addr[1:0]]=cfg_addr>>2;marg_wr_data[cfg_addr[1:0]]=cfg_data[17:0];end
    K_GAMMA:begin gamma_wr_en[cfg_addr[1:0]]=1;gamma_wr_row[cfg_addr[1:0]]=cfg_addr>>2;gamma_wr_data[cfg_addr[1:0]]=cfg_data[4:0];end
    K_DEC:begin dec_wr_en[cfg_addr[1:0]]=1;dec_wr_row[cfg_addr[1:0]]=cfg_addr>>2;dec_wr_data[cfg_addr[1:0]]=cfg_data[0];end
   endcase
  end else if(req_valid&&req_ready&&(req_kind==K_PRIOR||req_kind==K_MARG||req_kind==K_GAMMA||req_kind==K_DEC))for(i=0;i<P;i=i+1)if(req_mask[i])case(req_kind)
   K_PRIOR:begin prior_rd_en[req_addr[i][1:0]]=!req_write;prior_rd_row[req_addr[i][1:0]]=req_addr[i]>>2;end
   K_MARG:begin if(req_write)begin marg_wr_en[req_addr[i][1:0]]=1;marg_wr_row[req_addr[i][1:0]]=req_addr[i]>>2;marg_wr_data[req_addr[i][1:0]]=req_wdata[i][17:0];end else begin marg_rd_en[req_addr[i][1:0]]=1;marg_rd_row[req_addr[i][1:0]]=req_addr[i]>>2;end end
   K_GAMMA:begin if(req_write)begin gamma_wr_en[req_addr[i][1:0]]=1;gamma_wr_row[req_addr[i][1:0]]=req_addr[i]>>2;gamma_wr_data[req_addr[i][1:0]]=req_wdata[i][4:0];end else begin gamma_rd_en[req_addr[i][1:0]]=1;gamma_rd_row[req_addr[i][1:0]]=req_addr[i]>>2;end end
   K_DEC:begin if(req_write)begin dec_wr_en[req_addr[i][1:0]]=1;dec_wr_row[req_addr[i][1:0]]=req_addr[i]>>2;dec_wr_data[req_addr[i][1:0]]=req_wdata[i][0];end else begin dec_rd_en[req_addr[i][1:0]]=1;dec_rd_row[req_addr[i][1:0]]=req_addr[i]>>2;end end
  endcase
  if(correction_req&&correction_ready)for(i=0;i<P;i=i+1)begin dec_rd_en[i]=1;dec_rd_row[i]=correction_word;end
  for(i=0;i<P;i=i+1)begin
   rsp_data[i]=rsp_data_reg[i];
   correction_bits[i]=dec_rd_data[i][0];
   if(rsp_kind==K_NU)rsp_data[i]={{4{nu_rd_data[rsp_addr[i][1:0]][17]}},nu_rd_data[rsp_addr[i][1:0]]};
   else if(rsp_kind==K_MU)rsp_data[i]={{4{mu_rd_data[rsp_addr[i][1:0]][17]}},mu_rd_data[rsp_addr[i][1:0]]};
   else if(rsp_kind==K_PRIOR)rsp_data[i]={{4{prior_rd_data[rsp_addr[i][1:0]][17]}},prior_rd_data[rsp_addr[i][1:0]]};
   else if(rsp_kind==K_MARG)rsp_data[i]={{4{marg_rd_data[rsp_addr[i][1:0]][17]}},marg_rd_data[rsp_addr[i][1:0]]};
   else if(rsp_kind==K_GAMMA)rsp_data[i]={{17{gamma_rd_data[rsp_addr[i][1:0]][4]}},gamma_rd_data[rsp_addr[i][1:0]]};
   else if(rsp_kind==K_DEC)rsp_data[i]={{21{1'b0}},dec_rd_data[rsp_addr[i][1:0]]};
   else if(rsp_kind==K_EV)rsp_data[i]={{(22-VW){1'b0}},ev_rd_data[rsp_addr[i][1:0]]};
   else if(rsp_kind==K_VE)rsp_data[i]={{(22-EW){1'b0}},ve_rd_data[rsp_addr[i][1:0]]};
   else if(rsp_kind==K_CP)rsp_data[i]={{(22-PW){1'b0}},cp_rd_data};
   else if(rsp_kind==K_VP)rsp_data[i]={{(22-PW){1'b0}},vp_rd_data};
   else if(rsp_kind==K_SYN)rsp_data[i]={{21{1'b0}},syn_rd_data[rsp_addr[i][1:0]]};
  end
 end
 initial begin
  read_conflicts=0;write_conflicts=0;rsp_valid=0;correction_rsp_valid=0;service_cycle=0;
 end
 always_ff @(posedge clk)begin
  service_cycle<=service_cycle+1;rsp_valid<=req_valid&&req_ready&&!req_write;correction_rsp_valid<=correction_req&&correction_ready;
  if(req_valid&&!req_ready)begin if(req_write)write_conflicts<=write_conflicts+1;else read_conflicts<=read_conflicts+1;end
  if(cfg_we)case(cfg_kind)
   K_LIM:limit[cfg_addr]<=cfg_data[15:0];
  endcase
  rsp_kind<=req_kind;rsp_mask<=req_mask;
  if(req_valid&&req_ready)for(i=0;i<P;i=i+1)if(req_mask[i])begin
   rsp_addr[i]<=req_addr[i];
   if(!req_write)case(req_kind)
    K_LIM:rsp_data_reg[i]<=limit[req_addr[i]];
   endcase
  end
  if(correction_req&&correction_ready)for(i=0;i<P;i=i+1)begin
   correction_mask[i]<=correction_word*P+i<V;
  end
 end
`ifdef RELAY_BP_SIM_ASSERT
 // Verification mirrors preserve legacy trace access and are absent from synthesis.
 logic signed[17:0]mu[0:E-1],nu[0:E-1],marg[0:V-1];logic signed[4:0]gamma[0:V-1];logic decision[0:V-1];
 always_ff @(posedge clk)begin
  if(cfg_we)case(cfg_kind)K_MU:mu[cfg_addr]<=cfg_data[17:0];K_NU:nu[cfg_addr]<=cfg_data[17:0];K_MARG:marg[cfg_addr]<=cfg_data[17:0];K_GAMMA:gamma[cfg_addr]<=cfg_data[4:0];K_DEC:decision[cfg_addr]<=cfg_data[0];endcase
  if(req_valid&&req_ready&&req_write)for(integer z=0;z<P;z=z+1)if(req_mask[z])case(req_kind)
   K_MU:mu[req_addr[z]]<=req_wdata[z][17:0];K_NU:nu[req_addr[z]]<=req_wdata[z][17:0];K_MARG:marg[req_addr[z]]<=req_wdata[z][17:0];K_GAMMA:gamma[req_addr[z]]<=req_wdata[z][4:0];K_DEC:decision[req_addr[z]]<=req_wdata[z][0];endcase
 end
`endif
endmodule

// Generic packed P-lane synchronous memory; no vendor primitive dependency.
module relay_bp_packed_sync_ram #(
 parameter int FIELD_W=18,LOGICAL_DEPTH=1,P=4,READ_LATENCY=1,
 parameter int WORDS=(LOGICAL_DEPTH+P-1)/P,AW=(WORDS<=1)?1:$clog2(WORDS),
 parameter string INIT_FILE=""
)(input logic clk,input logic rd_req,input logic[AW-1:0]rd_word,output logic rsp_valid,
 output logic signed[FIELD_W-1:0]rsp_lane[0:P-1],input logic wr_req,input logic[AW-1:0]wr_word,
 input logic[P-1:0]wr_mask,input logic signed[FIELD_W-1:0]wr_lane[0:P-1]);
 logic[FIELD_W*P-1:0]mem[0:WORDS-1];integer k;
 initial if(INIT_FILE!="")$readmemh(INIT_FILE,mem);
 always_ff @(posedge clk)begin
  rsp_valid<=rd_req;if(rd_req)for(k=0;k<P;k=k+1)rsp_lane[k]<=mem[rd_word][k*FIELD_W+:FIELD_W];
  if(wr_req)for(k=0;k<P;k=k+1)if(wr_mask[k])mem[wr_word][k*FIELD_W+:FIELD_W]<=wr_lane[k];
 end
endmodule

module relay_bp_scalar_sync_ram #(
 parameter int WIDTH=19,DEPTH=1,AW=(DEPTH<=1)?1:$clog2(DEPTH),parameter INIT_FILE=""
)(input logic clk,input logic rd_req,input logic[AW-1:0]rd_addr,output logic rsp_valid,
 output logic[WIDTH-1:0]rsp_data,input logic wr_req,input logic[AW-1:0]wr_addr,input logic[WIDTH-1:0]wr_data);
 logic[WIDTH-1:0]mem[0:DEPTH-1];initial if(INIT_FILE!="")$readmemh(INIT_FILE,mem);
 always_ff @(posedge clk)begin rsp_valid<=rd_req;if(rd_req)rsp_data<=mem[rd_addr];if(wr_req)mem[wr_addr]<=wr_data;end
endmodule

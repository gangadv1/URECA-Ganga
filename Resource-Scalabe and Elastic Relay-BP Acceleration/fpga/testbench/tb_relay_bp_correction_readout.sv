`timescale 1ns/1ps
module tb_relay_bp_correction_readout;
 localparam V=20,P=4,W=5,AW=3;logic clk=0,candidate_valid=0,rd_req=0,rd_ready,rsp_valid,decision_rsp_valid=0,decision_rd_req;logic[AW-1:0]rd_word,decision_rd_word;logic[P-1:0]rsp_bits,rsp_mask;logic signed[0:0]decision_rsp[0:P-1];logic bits[0:V-1];integer w,k,fail;
 always #5 clk=~clk;
 relay_bp_correction_readout #(.VARIABLES(V))dut(.*);
 always_ff @(posedge clk)begin decision_rsp_valid<=decision_rd_req;if(decision_rd_req)for(k=0;k<P;k=k+1)decision_rsp[k]<=bits[decision_rd_word*P+k];end
 initial begin for(k=0;k<V;k=k+1)bits[k]=(k%3)==0;repeat(2)@(posedge clk);candidate_valid=1;fail=0;
  for(w=0;w<W;w=w+1)begin @(negedge clk)rd_word=w;rd_req=1;@(negedge clk)rd_req=0;wait(rsp_valid);#1;for(k=0;k<P;k=k+1)if(!rsp_mask[k]||rsp_bits[k]!==bits[w*P+k])fail=fail+1;end
  candidate_valid=0;@(negedge clk)rd_req=1;#1;if(rd_ready||decision_rd_req)fail=fail+1;
  $display("CORRECTION_READOUT_RESULT words=%0d bits=%0d failures=%0d",W,V,fail);if(fail)$fatal(1,"correction readout failed");$finish;
 end
endmodule

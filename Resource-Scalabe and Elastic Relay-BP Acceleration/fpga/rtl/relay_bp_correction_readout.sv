// Scalable packed winning-correction readout (four decision bits per word).
module relay_bp_correction_readout #(
 parameter int VARIABLES=67752,P=4,WORDS=(VARIABLES+P-1)/P,AW=(WORDS<=1)?1:$clog2(WORDS)
)(input logic clk,input logic candidate_valid,input logic rd_req,input logic[AW-1:0]rd_word,
 output logic rd_ready,output logic rsp_valid,output logic[P-1:0]rsp_bits,output logic[P-1:0]rsp_mask,
 input logic decision_rsp_valid,input logic signed[0:0]decision_rsp[0:P-1],
 output logic decision_rd_req,output logic[AW-1:0]decision_rd_word);
 logic[AW-1:0]pending_word;integer k;
 always_comb begin rd_ready=candidate_valid;decision_rd_req=rd_req&&rd_ready;decision_rd_word=rd_word;end
 always_ff @(posedge clk)begin
  if(decision_rd_req)pending_word<=rd_word;
  rsp_valid<=decision_rsp_valid;
  if(decision_rsp_valid)for(k=0;k<P;k=k+1)begin
   rsp_bits[k]<=decision_rsp[k][0];rsp_mask[k]<=((pending_word*P+k)<VARIABLES);
  end
 end
endmodule

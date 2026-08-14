// Four independent inference-friendly 1R/1W banks.  At most one lane may
// address each bank in a cycle; the fabric's fixed conflict logic enforces it.
module relay_bp_four_bank_ram #(
 parameter int WIDTH=18,DEPTH=1,P=4,
 parameter INIT0="",INIT1="",INIT2="",INIT3=""
)(input logic clk,input logic[P-1:0]rd_en,input logic[31:0]rd_row[0:P-1],
 output logic[WIDTH-1:0]rd_data[0:P-1],input logic[P-1:0]wr_en,
 input logic[31:0]wr_row[0:P-1],input logic[WIDTH-1:0]wr_data[0:P-1]);
 logic[WIDTH-1:0]bank0[0:DEPTH-1],bank1[0:DEPTH-1],bank2[0:DEPTH-1],bank3[0:DEPTH-1];
 initial begin
  if(INIT0!="")$readmemh(INIT0,bank0);if(INIT1!="")$readmemh(INIT1,bank1);
  if(INIT2!="")$readmemh(INIT2,bank2);if(INIT3!="")$readmemh(INIT3,bank3);
 end
 always_ff @(posedge clk)begin
  if(rd_en[0])rd_data[0]<=bank0[rd_row[0]];if(wr_en[0])bank0[wr_row[0]]<=wr_data[0];
  if(rd_en[1])rd_data[1]<=bank1[rd_row[1]];if(wr_en[1])bank1[wr_row[1]]<=wr_data[1];
  if(rd_en[2])rd_data[2]<=bank2[rd_row[2]];if(wr_en[2])bank2[wr_row[2]]<=wr_data[2];
  if(rd_en[3])rd_data[3]<=bank3[rd_row[3]];if(wr_en[3])bank3[wr_row[3]]<=wr_data[3];
 end
`ifdef RELAY_BP_SIM_ASSERT
 function automatic logic[WIDTH-1:0]peek(input integer a);
  case(a%4)0:peek=bank0[a/4];1:peek=bank1[a/4];2:peek=bank2[a/4];default:peek=bank3[a/4];endcase
 endfunction
`endif
endmodule

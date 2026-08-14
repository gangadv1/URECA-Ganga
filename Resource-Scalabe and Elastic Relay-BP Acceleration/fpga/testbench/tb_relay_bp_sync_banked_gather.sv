`timescale 1ns/1ps
module tb_relay_bp_sync_banked_gather;
 logic clk=0,rd_req=0,wr_req=0,rd_ready,wr_ready,rsp_valid;logic[3:0]rd_mask,wr_mask,rsp_mask;
 logic[4:0]rd_addr[0:3],wr_addr[0:3];logic signed[17:0]rsp_data[0:3],wr_data[0:3];integer fail=0,k;
 always #5 clk=~clk;
 relay_bp_sync_banked_gather #(.WIDTH(18),.DEPTH(20))dut(.*);
 initial begin
  wr_mask=4'b1111;for(k=0;k<4;k=k+1)begin wr_addr[k]=k;wr_data[k]=20+k;end
  @(negedge clk);wr_req=1;if(!wr_ready)fail=fail+1;@(negedge clk);wr_req=0;
  rd_mask=4'b1111;for(k=0;k<4;k=k+1)rd_addr[k]=k;rd_req=1;
  @(negedge clk);rd_req=0;if(!rsp_valid)fail=fail+1;for(k=0;k<4;k=k+1)if(rsp_data[k]!=20+k)fail=fail+1;
  rd_addr[0]=0;rd_addr[1]=4;rd_mask=4'b0011;#1;if(rd_ready)fail=fail+1;
  $display("BANKED_GATHER_RESULT cases=3 failed=%0d",fail);if(fail)$fatal(1,"banked gather mismatch");$finish;
 end
endmodule

`timescale 1ns/1ps
module tb_relay_bp_sync_p4_memory;
  logic clk=0,rd_req=0,wr_req=0,rsp_valid;logic[1:0]rd_word,wr_word;logic[3:0]wr_mask;
  logic signed[17:0]rsp_data[0:3],wr_data[0:3];integer fail=0,k;
  always #5 clk=~clk;
  relay_bp_sync_p4_memory #(.WIDTH(18),.LOGICAL_DEPTH(10)) dut(.*);
  initial begin
    wr_word=1;wr_mask=4'b1011;wr_data[0]=11;wr_data[1]=-12;wr_data[2]=13;wr_data[3]=-14;
    @(negedge clk);wr_req=1;@(negedge clk);wr_req=0;rd_word=1;rd_req=1;
    @(negedge clk);rd_req=0;if(!rsp_valid||rsp_data[0]!=11||rsp_data[1]!=-12||rsp_data[3]!=-14)fail=fail+1;
    // Masked lane 2 retains X; only written lanes are contractual.
    $display("SYNC_MEMORY_RESULT transactions=2 failed=%0d",fail);if(fail)$fatal(1,"sync memory mismatch");$finish;
  end
endmodule

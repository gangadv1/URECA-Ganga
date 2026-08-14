`timescale 1ns/1ps
module tb_relay_bp_node_wrappers;
 localparam P=4;logic clk=0,cfg_we=0,req_valid=0,req_write=0,req_ready,rsp_valid,correction_req=0,correction_ready,correction_rsp_valid;logic[3:0]cfg_kind,req_kind,rsp_kind,req_mask,rsp_mask;logic[31:0]cfg_addr,req_addr[0:3],rsp_addr[0:3],correction_word=0;logic signed[31:0]cfg_data;logic signed[21:0]req_wdata[0:3],rsp_data[0:3];logic[31:0]rc,wc;logic[3:0]correction_bits,correction_mask;integer i,fail;
 always #5 clk=~clk;
 relay_bp_memory_fabric_p4 #(.C(1),.V(20),.E(4))dut(.clk,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,.req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.read_conflicts(rc),.write_conflicts(wc),.correction_req,.correction_word,.correction_ready,.correction_rsp_valid,.correction_bits,.correction_mask);
 task wr(input integer k,input integer a,input integer d);begin @(negedge clk);req_kind=k;req_mask=1;req_addr[0]=a;req_wdata[0]=d;req_write=1;req_valid=1;@(negedge clk);if(!req_ready)$fatal(1,"write rejected");req_valid=0;req_write=0;end endtask
 task rd(input integer k,input integer a,input integer d);begin @(negedge clk);req_kind=k;req_mask=1;req_addr[0]=a;req_write=0;req_valid=1;@(negedge clk);if(!req_ready)$fatal(1,"read rejected");req_valid=0;wait(rsp_valid);#1;if($signed(rsp_data[0])!=d)begin $display("NODE_FAIL kind=%0d addr=%0d exp=%0d got=%0d",k,a,d,$signed(rsp_data[0]));fail++;end end endtask
 initial begin fail=0;for(i=0;i<4;i++)begin req_addr[i]=0;req_wdata[i]=0;end
  wr(4,0,131071);wr(4,1,-131072);wr(4,2,-7);wr(4,3,9);rd(4,0,131071);rd(4,1,-131072);rd(4,2,-7);rd(4,3,9);
  wr(10,4,-131072);rd(10,4,-131072);wr(10,4,131071);rd(10,4,131071);
  wr(6,5,-4);wr(6,6,0);wr(6,7,2);wr(6,8,4);wr(6,11,11);rd(6,5,-4);rd(6,6,0);rd(6,7,2);rd(6,8,4);rd(6,11,11);
  wr(11,9,1);wr(11,10,0);rd(11,9,1);rd(11,10,0);
  @(negedge clk);req_kind=11;req_mask=3;req_addr[0]=1;req_addr[1]=5;req_valid=1;#1;if(req_ready)fail++;@(negedge clk)req_valid=0;
  $display("NODE_WRAPPER_RESULT priors=4 marginals=2 gamma=5 decisions=2 failures=%0d",fail);if(fail)$fatal(1,"node wrapper failure");$finish;
 end
endmodule

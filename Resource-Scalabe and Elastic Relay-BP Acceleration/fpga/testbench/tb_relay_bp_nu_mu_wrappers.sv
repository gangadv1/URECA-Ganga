`timescale 1ns/1ps
module tb_relay_bp_nu_mu_wrappers;
 localparam E=20,P=4;logic clk=0,cfg_we=0,req_valid=0,req_write=0,req_ready,rsp_valid,correction_req=0,correction_ready,correction_rsp_valid;logic[3:0]cfg_kind,req_kind,rsp_kind,req_mask,rsp_mask;logic[31:0]cfg_addr,req_addr[0:3],rsp_addr[0:3],correction_word=0;logic signed[31:0]cfg_data;logic signed[21:0]req_wdata[0:3],rsp_data[0:3];logic[31:0]rc,wc;logic[3:0]correction_bits,correction_mask;integer i,fail;
 always #5 clk=~clk;
 relay_bp_memory_fabric_p4 #(.C(1),.V(4),.E(E))dut(.clk,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,.req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.read_conflicts(rc),.write_conflicts(wc),.correction_req,.correction_word,.correction_ready,.correction_rsp_valid,.correction_bits,.correction_mask);
 task write4(input integer kind,input logic[3:0]mask,input integer a0,a1,a2,a3,input integer d0,d1,d2,d3);begin @(negedge clk);req_kind=kind;req_mask=mask;req_addr[0]=a0;req_addr[1]=a1;req_addr[2]=a2;req_addr[3]=a3;req_wdata[0]=d0;req_wdata[1]=d1;req_wdata[2]=d2;req_wdata[3]=d3;req_write=1;req_valid=1;@(negedge clk);if(!req_ready)$fatal(1,"unexpected write reject");req_valid=0;req_write=0;end endtask
 task read4(input integer kind,input logic[3:0]mask,input integer a0,a1,a2,a3,input integer d0,d1,d2,d3);begin @(negedge clk);req_kind=kind;req_mask=mask;req_addr[0]=a0;req_addr[1]=a1;req_addr[2]=a2;req_addr[3]=a3;req_write=0;req_valid=1;@(negedge clk);if(!req_ready)$fatal(1,"unexpected read reject");req_valid=0;wait(rsp_valid);#1;if(mask[0]&&$signed(rsp_data[0])!=d0)fail++;if(mask[1]&&$signed(rsp_data[1])!=d1)fail++;if(mask[2]&&$signed(rsp_data[2])!=d2)fail++;if(mask[3]&&$signed(rsp_data[3])!=d3)fail++;end endtask
 initial begin fail=0;for(i=0;i<4;i++)begin req_addr[i]=0;req_wdata[i]=0;end
  write4(8,4'b1111,0,1,2,3,131071,-131072,-1,0);read4(8,4'b1111,0,1,2,3,131071,-131072,-1,0);
  write4(9,4'b1011,4,9,2,15,17,-18,0,12345);read4(9,4'b1011,4,9,2,15,17,-18,0,12345);
  @(negedge clk);req_kind=8;req_mask=4'b0011;req_addr[0]=0;req_addr[1]=4;req_valid=1;#1;if(req_ready)fail++;@(negedge clk)req_valid=0;
  $display("NU_MU_WRAPPER_RESULT transactions=5 banks=4 failures=%0d",fail);if(fail)$fatal(1,"nu/mu wrapper failure");$finish;
 end
endmodule

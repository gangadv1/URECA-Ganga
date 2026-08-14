`timescale 1ns/1ps
module tb_relay_bp_permanent_small_memories_p4;
 localparam C=1728,V=67752,E=391320,P=4,K_CP=0,K_VP=2,K_SYN=5;
 logic clk=0,cfg_we=0,req_valid=0,req_write=0,correction_req=0;logic[3:0]cfg_kind=0,req_kind=0;logic[31:0]cfg_addr=0,correction_word=0;logic signed[31:0]cfg_data=0;
 logic[P-1:0]req_mask=0;logic[31:0]req_addr[0:P-1];logic signed[21:0]req_wdata[0:P-1];logic req_ready,rsp_valid;logic[3:0]rsp_kind;logic[P-1:0]rsp_mask;logic[31:0]rsp_addr[0:P-1];logic signed[21:0]rsp_data[0:P-1];logic[31:0]rc,wc;logic cr,cv;logic[P-1:0]cb,cm;integer i;
 always #5 clk=~clk;
 relay_bp_memory_fabric_p4 #(.C(C),.V(V),.E(E),.L(1))dut(.clk,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,.req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.read_conflicts(rc),.write_conflicts(wc),.correction_req,.correction_word,.correction_ready(cr),.correction_rsp_valid(cv),.correction_bits(cb),.correction_mask(cm));
 task cfg(input[3:0]k,input[31:0]a,input[31:0]d);begin @(negedge clk);cfg_we=1;cfg_kind=k;cfg_addr=a;cfg_data=d;@(negedge clk);cfg_we=0;end endtask
 task read1(input[3:0]k,input[31:0]a,input[21:0]x);begin @(negedge clk);req_valid=1;req_kind=k;req_mask=1;req_addr[0]=a;@(negedge clk);req_valid=0;wait(rsp_valid);#1;if(rsp_kind!=k||rsp_mask!=1||rsp_addr[0]!=a||rsp_data[0]!==x)$fatal(1,"small memory mismatch kind=%0d address=%0d expected=%0d got=%0d",k,a,x,rsp_data[0]);end endtask
 initial begin
  for(i=0;i<P;i=i+1)begin req_addr[i]=0;req_wdata[i]=0;end
  cfg(K_CP,0,0);cfg(K_CP,1,51);cfg(K_CP,864,195660);cfg(K_CP,1728,391320);
  read1(K_CP,0,0);read1(K_CP,1,51);read1(K_CP,864,195660);read1(K_CP,1728,391320);
  cfg(K_VP,0,0);cfg(K_VP,1,1);cfg(K_VP,33876,195659);cfg(K_VP,67752,391320);
  read1(K_VP,0,0);read1(K_VP,1,1);read1(K_VP,33876,195659);read1(K_VP,67752,391320);
  cfg(K_SYN,0,0);cfg(K_SYN,1,1);cfg(K_SYN,777,1);cfg(K_SYN,1727,0);
  read1(K_SYN,0,0);read1(K_SYN,1,1);read1(K_SYN,777,1);read1(K_SYN,1727,0);
  cfg(K_SYN,0,1);cfg(K_SYN,1,0);cfg(K_SYN,777,0);cfg(K_SYN,1727,1);
  read1(K_SYN,0,1);read1(K_SYN,1,0);read1(K_SYN,777,0);read1(K_SYN,1727,1);
  $display("PERMANENT_SMALL_MEMORY_RESULT pointer_reads=8 syndrome_reads=8 reloads=4 failures=0");$finish;
 end
endmodule

`timescale 1ns/1ps
module tb_relay_bp_graph_memory_fabric_p4;
 localparam C=4,V=67752,E=391320,P=4,K_EV=1,K_VE=3;
 logic clk=0,cfg_we=0,req_valid=0,req_write=0,correction_req=0;
 logic[3:0]cfg_kind=0,req_kind=0;logic[31:0]cfg_addr=0,correction_word=0;logic signed[31:0]cfg_data=0;
 logic[P-1:0]req_mask=0;logic[31:0]req_addr[0:P-1];logic signed[21:0]req_wdata[0:P-1];logic req_ready,rsp_valid;logic[3:0]rsp_kind;logic[P-1:0]rsp_mask;logic[31:0]rsp_addr[0:P-1];logic signed[21:0]rsp_data[0:P-1];logic[31:0]rc,wc;logic cr,cv;logic[P-1:0]cb,cm;integer i;
 always #5 clk=~clk;
 relay_bp_memory_fabric_p4 #(.C(C),.V(V),.E(E),.L(1))dut(.clk,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,.req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.read_conflicts(rc),.write_conflicts(wc),.correction_req,.correction_word,.correction_ready(cr),.correction_rsp_valid(cv),.correction_bits(cb),.correction_mask(cm));
 task cfg(input[3:0]k,input[31:0]a,input[31:0]d);begin @(negedge clk);cfg_we=1;cfg_kind=k;cfg_addr=a;cfg_data=d;@(negedge clk);cfg_we=0;end endtask
 task read4(input[3:0]k,input[31:0]a0,a1,a2,a3,input[3:0]m,input[21:0]x0,x1,x2,x3);begin
  @(negedge clk);req_valid=1;req_kind=k;req_mask=m;req_addr[0]=a0;req_addr[1]=a1;req_addr[2]=a2;req_addr[3]=a3;
  @(negedge clk);req_valid=0;wait(rsp_valid);#1;
  if(rsp_kind!=k||rsp_mask!=m||(m[0]&&rsp_data[0]!==x0)||(m[1]&&rsp_data[1]!==x1)||(m[2]&&rsp_data[2]!==x2)||(m[3]&&rsp_data[3]!==x3))$fatal(1,"graph memory readback mismatch kind=%0d mask=%b",k,m);
 end endtask
 initial begin
  for(i=0;i<P;i=i+1)begin req_addr[i]=0;req_wdata[i]=0;end
  cfg(K_EV,0,0);cfg(K_EV,1,1);cfg(K_EV,2,67750);cfg(K_EV,3,67751);cfg(K_EV,5,12345);cfg(K_EV,6,54321);
  read4(K_EV,0,1,2,3,4'b1111,0,1,67750,67751);read4(K_EV,5,6,0,0,4'b0011,12345,54321,0,0);
  cfg(K_VE,0,0);cfg(K_VE,1,1);cfg(K_VE,2,391318);cfg(K_VE,3,391319);cfg(K_VE,9,300001);cfg(K_VE,14,234567);
  read4(K_VE,0,1,2,3,4'b1111,0,1,391318,391319);read4(K_VE,9,14,0,0,4'b0011,300001,234567,0,0);
  @(negedge clk);req_valid=1;req_kind=K_EV;req_mask=4'b0011;req_addr[0]=0;req_addr[1]=4;#1;if(req_ready)$fatal(1,"same-bank gather was not rejected");@(negedge clk);req_valid=0;
  $display("GRAPH_MEMORY_FABRIC_RESULT checks=12 banks=4 masks=partial unaligned=1 conflicts_rejected=1 failures=0");$finish;
 end
endmodule

`timescale 1ns/1ps
module tb_m4_message_alias;
 parameter integer READ_LATENCY=1;localparam W=18,D=16,AW=4;
 reg clk=0,rst=1;always #5 clk=~clk;reg phase,ri,close,wi,advance;wire permit;wire[15:0]outstanding;wire closed;
 reg ren,wen;reg[AW-1:0]raddr,waddr;reg[15:0]rtag;reg[W-1:0]wdata;wire rv;wire[W-1:0]rdata;wire[AW-1:0]rraddr;wire[15:0]rrtag;
 m4_message_ram #(.WIDTH(W),.DEPTH(D),.ADDR_W(AW),.READ_LATENCY(READ_LATENCY)) ram(.clk(clk),.rst(rst),.r_en(ren),.r_addr(raddr),.r_tag(rtag),.r_valid(rv),.r_data(rdata),.r_rsp_addr(rraddr),.r_rsp_tag(rrtag),.w_en(wen),.w_addr(waddr),.w_data(wdata));
 m4_message_phase_controller ctl(.clk(clk),.rst(rst),.phase(phase),.read_issue(ri),.read_return(rv),.neighborhood_close(close),.write_issue(wi),.phase_advance(advance),.write_permit(permit),.outstanding(outstanding),.neighborhood_closed(closed));
 integer i,errors=0,responses=0,expected_base=10;
 task gather(input integer base,input integer count);begin
  for(i=0;i<count;i=i+1)begin @(negedge clk);ren=1;ri=1;raddr=base+i;rtag=base+i;close=(i==count-1);@(posedge clk);end
  @(negedge clk);ren=0;ri=0;close=0;
  while(!permit)@(negedge clk);
 end endtask
 task overwrite(input integer base,input integer count,input integer value);begin
  for(i=0;i<count;i=i+1)begin @(negedge clk);if(!permit)$fatal(1,"permit dropped");wen=1;wi=1;waddr=base+i;wdata=value+i;@(posedge clk);end
  @(negedge clk);wen=0;wi=0;advance=1;@(posedge clk);@(negedge clk);advance=0;
 end endtask
 always @(negedge clk)if(rv)begin responses=responses+1;if(rrtag!==rraddr)begin $display("tag/address mismatch");errors=errors+1;end if(rdata!==(expected_base+rraddr))begin $display("message data mismatch expected=%0d got=%0d",expected_base+rraddr,rdata);errors=errors+1;end end
 initial begin phase=0;ri=0;close=0;wi=0;advance=0;ren=0;wen=0;raddr=0;waddr=0;rtag=0;wdata=0;for(i=0;i<D;i=i+1)ram.ram.mem[i]=10+i;
  repeat(3)@(posedge clk);rst=0;
  expected_base=10;gather(0,4);overwrite(0,4,100);phase=1;expected_base=100;gather(0,4);
  for(i=0;i<4;i=i+1)if(ram.ram.mem[i]!==100+i)begin $display("MU mismatch");errors=errors+1;end
  overwrite(0,4,200);phase=0;expected_base=200;gather(0,4);
  for(i=0;i<4;i=i+1)if(ram.ram.mem[i]!==200+i)begin $display("NU_new mismatch");errors=errors+1;end
  if(outstanding!=0)errors=errors+1;if(errors)$fatal(1,"alias test failed");$display("PASS M4_ALIAS latency=%0d responses=%0d hazards=0",READ_LATENCY,responses);$finish;
 end
endmodule

`timescale 1ns/1ps
module tb_m4_memory_fabric;
  parameter integer READ_LATENCY=1; localparam W=18;localparam D=256;localparam AW=8;
  reg clk=0,rst=1;always #5 clk=~clk;
  reg e0_en,e1_en;reg[AW-1:0]e0_addr,e1_addr;reg[15:0]e0_tag,e1_tag;wire e0_v,e1_v;wire[W-1:0]e0_data,e1_data;wire[15:0]e0_rt,e1_rt;
  m4_memory_fabric_top #(.WIDTH(W),.LOGICAL_DEPTH(D),.ADDR_W(AW),.READ_LATENCY(READ_LATENCY)) dut(.clk(clk),.rst(rst),.e0_s_en(e0_en),.e0_s_addr(e0_addr),.e0_s_tag(e0_tag),.e0_s_valid(e0_v),.e0_s_data(e0_data),.e0_s_rsp_tag(e0_rt),.e1_s_en(e1_en),.e1_s_addr(e1_addr),.e1_s_tag(e1_tag),.e1_s_valid(e1_v),.e1_s_data(e1_data),.e1_s_rsp_tag(e1_rt));
  integer i,fd,rv,cyc,errors=0,requests=0,responses=0;integer v0,v1,a0,a1;reg[1023:0]vecfile,tracefile;
  reg exp0v[0:2],exp1v[0:2];reg[W-1:0]exp0d[0:2],exp1d[0:2];reg[15:0]exp0t[0:2],exp1t[0:2];integer k;
  task clear_pipe;begin for(k=0;k<3;k=k+1)begin exp0v[k]=0;exp1v[k]=0;exp0d[k]=0;exp1d[k]=0;exp0t[k]=0;exp1t[k]=0;end end endtask
  task check_response;begin
    if(e0_v!==exp0v[READ_LATENCY-1])begin $display("E0 valid mismatch cycle %0d",cyc);errors=errors+1;end
    if(e1_v!==exp1v[READ_LATENCY-1])begin $display("E1 valid mismatch cycle %0d",cyc);errors=errors+1;end
    if(e0_v)begin responses=responses+1;if(e0_data!==exp0d[READ_LATENCY-1]||e0_rt!==exp0t[READ_LATENCY-1])begin $display("E0 response mismatch");errors=errors+1;end
      $fwrite(fd,"%0d,E0,shared,%0d,%0d,read,%0d,%0d,%0d,%0d,%0d,%0d\n",cyc,(e0_data-100)%4,e0_data-100,e0_rt,e0_rt,e0_rt,e0_rt+READ_LATENCY,cyc,(e0_data==exp0d[READ_LATENCY-1])&&(e0_rt==exp0t[READ_LATENCY-1]));end
    if(e1_v)begin responses=responses+1;if(e1_data!==exp1d[READ_LATENCY-1]||e1_rt!==exp1t[READ_LATENCY-1])begin $display("E1 response mismatch");errors=errors+1;end
      $fwrite(fd,"%0d,E1,shared,%0d,%0d,read,%0d,%0d,%0d,%0d,%0d,%0d\n",cyc,(e1_data-100)%4,e1_data-100,e1_rt-16'h8000,e1_rt-16'h8000,e1_rt-16'h8000,e1_rt-16'h8000+READ_LATENCY,cyc,(e1_data==exp1d[READ_LATENCY-1])&&(e1_rt==exp1t[READ_LATENCY-1]));end
  end endtask
  task shift_expect;begin
    for(k=2;k>0;k=k-1)begin exp0v[k]=exp0v[k-1];exp1v[k]=exp1v[k-1];exp0d[k]=exp0d[k-1];exp1d[k]=exp1d[k-1];exp0t[k]=exp0t[k-1];exp1t[k]=exp1t[k-1];end
    exp0v[0]=e0_en;exp1v[0]=e1_en;exp0d[0]=100+e0_addr;exp1d[0]=100+e1_addr;exp0t[0]=e0_tag;exp1t[0]=e1_tag;if(e0_en)requests=requests+1;if(e1_en)requests=requests+1;
  end endtask
  initial begin
    if(!$value$plusargs("VECTORS=%s",vecfile))vecfile="fpga/testbench/m4_memory_fabric/stress_vectors.txt";
    if(!$value$plusargs("TRACE=%s",tracefile))tracefile="results/m4-memory-fabric-rtl/trace_raw.csv";
    for(i=0;i<64;i=i+1)begin dut.BANK[0].u.mem[i]=100+4*i;dut.BANK[1].u.mem[i]=101+4*i;dut.BANK[2].u.mem[i]=102+4*i;dut.BANK[3].u.mem[i]=103+4*i;end
    e0_en=0;e1_en=0;e0_addr=0;e1_addr=0;e0_tag=0;e1_tag=0;clear_pipe();
    fd=$fopen(tracefile,"w");$fwrite(fd,"cycle,trajectory,memory,bank,address,operation,request_cycle,reference_grant,rtl_grant,reference_return,rtl_return,match\n");
    repeat(3)@(posedge clk);rst=0;@(negedge clk);
    // Directed: different address/same bank, same address, one idle, alternating.
    for(cyc=0;cyc<8;cyc=cyc+1)begin
      check_response();
      case(cyc)
       0:begin e0_en=1;e1_en=1;e0_addr=4;e1_addr=8;end
       1:begin e0_en=1;e1_en=1;e0_addr=12;e1_addr=12;end
       2:begin e0_en=1;e1_en=0;e0_addr=5;e1_addr=0;end
       3:begin e0_en=0;e1_en=1;e0_addr=0;e1_addr=9;end
       default:begin e0_en=1;e1_en=1;e0_addr=cyc*4;e1_addr=cyc*4+4;end
      endcase
      e0_tag=cyc;e1_tag=16'h8000+cyc;@(posedge clk);@(negedge clk);
      shift_expect();
    end
    // Frozen-vector randomized replay.
    rv=$fopen(vecfile,"r");if(rv==0)$fatal(1,"cannot open stress vectors");
    while(!$feof(rv))begin
      check_response();v0=0;v1=0;a0=0;a1=0;
      if($fscanf(rv,"%d %d %d %d\n",v0,a0,v1,a1)==4)begin e0_en=v0;e1_en=v1;e0_addr=a0;e1_addr=a1;e0_tag=cyc;e1_tag=16'h8000+cyc;shift_expect();cyc=cyc+1;@(posedge clk);@(negedge clk);end
    end
    $fclose(rv);e0_en=0;e1_en=0;
    repeat(READ_LATENCY+2)begin check_response();shift_expect();cyc=cyc+1;@(posedge clk);@(negedge clk);end
    $fclose(fd);
    if(responses!=requests)begin $display("dropped/duplicated response requests=%0d responses=%0d",requests,responses);errors=errors+1;end
    if(errors)$fatal(1,"FAIL errors=%0d",errors);$display("PASS M4_FABRIC latency=%0d requests=%0d responses=%0d",READ_LATENCY,requests,responses);$finish;
  end
endmodule

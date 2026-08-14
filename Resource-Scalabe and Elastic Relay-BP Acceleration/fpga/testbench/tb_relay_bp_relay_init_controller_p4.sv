`timescale 1ns/1ps
module tb_relay_bp_relay_init_controller_p4;
 localparam C=12,V=20,E=76,P=4;
 logic clk=0,rst=1,start=0,cfg_we=0;logic[3:0]cfg_kind;logic[31:0]cfg_addr;logic signed[31:0]cfg_data;
 logic busy,done,mu_valid,leg_state_reset,req_valid,req_write,req_ready,rsp_valid;logic[3:0]req_kind,rsp_kind,req_mask,rsp_mask;
 logic[31:0]req_addr[0:3],rsp_addr[0:3];logic signed[21:0]req_wdata[0:3],rsp_data[0:3];
 logic[31:0]cycles,reads,responses,writes,waits,pc,nc,retries,gw,mrc,mwc;
 integer ev[0:E-1],prior[0:V-1],marginal[0:V-1],gamma[0:V-1],dirty_nu[0:E-1],dirty_mu[0:E-1];
 integer fd,rc,one,cid,t,v,e,fail,comparisons,timeout;
 always #5 clk=~clk;
 relay_bp_response_memory #(.C(C),.V(V),.E(E),.STALL_PERIOD(5))mem(.clk,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.read_conflicts(mrc),.write_conflicts(mwc));
 relay_bp_relay_init_controller_p4 #(.VARIABLES(V),.EDGES(E))dut(.clk,.rst,.start,.busy,.done,.mu_valid,.leg_state_reset,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,
  .cycle_count(cycles),.read_requests(reads),.response_count(responses),.write_requests(writes),.wait_cycles(waits),
  .prior_conflicts(pc),.nu_conflicts(nc),.retry_subsets(retries),.gamma_writes(gw));
 task cfg_write(input integer k,input integer a,input integer d);begin @(negedge clk);cfg_kind=k;cfg_addr=a;cfg_data=d;cfg_we=1;@(negedge clk);cfg_we=0;end endtask
 task load_case;begin rc=$fscanf(fd,"%d",cid);
  for(v=0;v<V;v=v+1)begin one=$fscanf(fd," %d",prior[v]);rc=rc+one;end for(v=0;v<V;v=v+1)begin one=$fscanf(fd," %d",marginal[v]);rc=rc+one;end
  for(v=0;v<V;v=v+1)begin one=$fscanf(fd," %d",gamma[v]);rc=rc+one;end for(e=0;e<E;e=e+1)begin one=$fscanf(fd," %d",dirty_nu[e]);rc=rc+one;end
  for(e=0;e<E;e=e+1)begin one=$fscanf(fd," %d",dirty_mu[e]);rc=rc+one;end
  for(v=0;v<V;v=v+1)begin cfg_write(4,v,prior[v]);cfg_write(10,v,marginal[v]);cfg_write(6,v,gamma[v]);end
  for(e=0;e<E;e=e+1)begin cfg_write(8,e,dirty_nu[e]);cfg_write(9,e,dirty_mu[e]);end
 end endtask
 initial begin
  ev[0]=3;ev[1]=4;ev[2]=6;ev[3]=9;ev[4]=0;ev[5]=12;ev[6]=15;ev[7]=18;ev[8]=0;ev[9]=1;ev[10]=3;ev[11]=10;ev[12]=12;ev[13]=2;ev[14]=4;ev[15]=8;ev[16]=9;ev[17]=12;ev[18]=13;ev[19]=2;ev[20]=3;ev[21]=6;ev[22]=7;ev[23]=14;ev[24]=18;ev[25]=19;ev[26]=0;ev[27]=3;ev[28]=5;ev[29]=6;ev[30]=9;ev[31]=11;ev[32]=12;ev[33]=13;ev[34]=14;ev[35]=0;ev[36]=2;ev[37]=3;ev[38]=7;ev[39]=13;ev[40]=16;ev[41]=17;ev[42]=18;ev[43]=19;ev[44]=3;ev[45]=5;ev[46]=15;ev[47]=0;ev[48]=2;ev[49]=12;ev[50]=17;ev[51]=18;ev[52]=0;ev[53]=1;ev[54]=3;ev[55]=5;ev[56]=7;ev[57]=14;ev[58]=16;ev[59]=3;ev[60]=5;ev[61]=7;ev[62]=9;ev[63]=10;ev[64]=13;ev[65]=18;ev[66]=19;ev[67]=0;ev[68]=1;ev[69]=3;ev[70]=6;ev[71]=9;ev[72]=10;ev[73]=16;ev[74]=17;ev[75]=19;
  fd=$fopen("fpga/verification/memory_backed_relay_init/relay_cases.txt","r");if(!fd)$fatal(1,"relay vectors missing");repeat(2)@(posedge clk);#1 rst=0;
  for(e=0;e<E;e=e+1)cfg_write(1,e,ev[e]);fail=0;comparisons=0;
  for(t=0;t<5;t=t+1)begin load_case();@(negedge clk);start=1;@(negedge clk);start=0;timeout=0;while(!done&&timeout<5000)begin @(posedge clk);#1;timeout=timeout+1;end if(!done)$fatal(1,"relay init timeout state=%0d pos=%0d pending=%b selected=%b",dut.state,dut.position,dut.pending_mask,dut.selected_mask);
   if(mu_valid||!leg_state_reset||gw!=0)begin fail=fail+1;$fatal(1,"relay completion flags/gamma count mismatch");end
   for(e=0;e<E;e=e+1)begin if($signed(mem.nu[e])!==prior[ev[e]])begin fail=fail+1;$display("NU_RESET_FAIL case=%0d edge=%0d fault=%0d exp=%0d got=%0d",cid,e,ev[e],prior[ev[e]],$signed(mem.nu[e]));$fatal(1,"nu reset mismatch");end if($signed(mem.mu[e])!==dirty_mu[e])$fatal(1,"mu physically modified");comparisons=comparisons+1;end
   for(v=0;v<V;v=v+1)begin if($signed(mem.prior[v])!==prior[v])$fatal(1,"prior modified");if($signed(mem.marg[v])!==marginal[v])$fatal(1,"marginal modified");if($signed(mem.gamma[v])!==gamma[v])$fatal(1,"gamma load mismatch");comparisons=comparisons+3;end
   $display("RELAY_INIT_CASE_RESULT case=%0d cycles=%0d reads=%0d responses=%0d writes=%0d waits=%0d prior_conflicts=%0d nu_conflicts=%0d retries=%0d gamma_writes=%0d failed=0",cid,cycles,reads,responses,writes,waits,pc,nc,retries,gw);
  end
  $display("RELAY_INIT_CONTROLLER_RESULT cases=5 edges=380 node_checks=300 comparisons=%0d failed=%0d",comparisons,fail);if(fail)$fatal(1,"relay init failure");$finish;
 end
endmodule

`timescale 1ns/1ps
module tb_relay_bp_variable_controller_p4;
 localparam V=20,E=76,P=4;
 logic clk=0,rst=1,start=0,cfg_we=0;logic[3:0]cfg_kind;logic[31:0]cfg_addr;logic signed[31:0]cfg_data;
 logic busy,done,req_valid,req_write,req_ready,rsp_valid,variable_done;logic[3:0]req_kind,rsp_kind,req_mask,rsp_mask;
 logic[31:0]req_addr[0:3],rsp_addr[0:3];logic signed[21:0]req_wdata[0:3],rsp_data[0:3];
 logic[4:0]trace_variable;logic signed[17:0]trace_bias,trace_marginal,trace_weight;logic signed[21:0]trace_sum;logic trace_decision;
 logic signed[31:0]candidate_weight;logic[31:0]cycles,reads,responses,writes,waits,muc,nuc,retries,mrc,mwc;
 integer vp[0:V],ve[0:E-1],prior[0:V-1],prev[0:V-1],gamma[0:V-1],mu[0:E-1];
 integer ebias[0:V-1],esum[0:V-1],emarg[0:V-1],edec[0:V-1],enu[0:E-1],eweight;
 integer fd,rc,one,cid,t,v,e,fail,comparisons;
 always #5 clk=~clk;
 relay_bp_response_memory #(.C(12),.V(V),.E(E),.STALL_PERIOD(7))mem(.clk,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.read_conflicts(mrc),.write_conflicts(mwc));
 relay_bp_variable_controller_p4 #(.VARIABLES(V),.EDGES(E))dut(.clk,.rst,.start,.gamma_base(0),.busy,.done,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,
  .variable_done,.trace_variable,.trace_bias,.trace_marginal,.trace_sum,.trace_decision,.trace_weight_contribution(trace_weight),
  .candidate_weight,.cycle_count(cycles),.read_requests(reads),.response_count(responses),.write_requests(writes),.wait_cycles(waits),
  .mu_conflicts(muc),.nu_conflicts(nuc),.retry_subsets(retries));
 task cfg_write(input integer k,input integer a,input integer d);begin @(negedge clk);cfg_kind=k;cfg_addr=a;cfg_data=d;cfg_we=1;@(negedge clk);cfg_we=0;end endtask
 task load_case;begin rc=$fscanf(fd,"%d",cid);
  for(v=0;v<V;v=v+1)begin one=$fscanf(fd," %d",prior[v]);rc=rc+one;end
  for(v=0;v<V;v=v+1)begin one=$fscanf(fd," %d",prev[v]);rc=rc+one;end
  for(v=0;v<V;v=v+1)begin one=$fscanf(fd," %d",gamma[v]);rc=rc+one;end
  for(e=0;e<E;e=e+1)begin one=$fscanf(fd," %d",mu[e]);rc=rc+one;end
  for(v=0;v<V;v=v+1)begin one=$fscanf(fd," %d",ebias[v]);rc=rc+one;end
  for(v=0;v<V;v=v+1)begin one=$fscanf(fd," %d",esum[v]);rc=rc+one;end
  for(v=0;v<V;v=v+1)begin one=$fscanf(fd," %d",emarg[v]);rc=rc+one;end
  for(v=0;v<V;v=v+1)begin one=$fscanf(fd," %d",edec[v]);rc=rc+one;end
  one=$fscanf(fd," %d",eweight);rc=rc+one;for(e=0;e<E;e=e+1)begin one=$fscanf(fd," %d",enu[e]);rc=rc+one;end
  for(v=0;v<V;v=v+1)begin cfg_write(4,v,prior[v]);cfg_write(10,v,prev[v]);cfg_write(6,v,gamma[v]);end
  for(e=0;e<E;e=e+1)cfg_write(9,e,mu[e]);
 end endtask
 initial begin
  vp[0]=0;vp[1]=7;vp[2]=10;vp[3]=14;vp[4]=23;vp[5]=25;vp[6]=29;vp[7]=33;vp[8]=37;vp[9]=38;vp[10]=43;vp[11]=46;vp[12]=47;vp[13]=52;vp[14]=56;vp[15]=59;vp[16]=61;vp[17]=64;vp[18]=67;vp[19]=72;vp[20]=76;
  fd=$fopen("fpga/verification/memory_backed_variable/variable_cases.txt","r");if(!fd)$fatal(1,"variable vectors missing");
  repeat(2)@(posedge clk);#1 rst=0;for(v=0;v<=V;v=v+1)cfg_write(2,v,vp[v]);
  // Load permutation from generated manifest order.
  ve[0]=4;ve[1]=8;ve[2]=26;ve[3]=35;ve[4]=47;ve[5]=52;ve[6]=67;ve[7]=9;ve[8]=53;ve[9]=68;ve[10]=13;ve[11]=19;ve[12]=36;ve[13]=48;ve[14]=0;ve[15]=10;ve[16]=20;ve[17]=27;ve[18]=37;ve[19]=44;ve[20]=54;ve[21]=59;ve[22]=69;ve[23]=1;ve[24]=14;ve[25]=28;ve[26]=45;ve[27]=55;ve[28]=60;ve[29]=2;ve[30]=21;ve[31]=29;ve[32]=70;ve[33]=22;ve[34]=38;ve[35]=56;ve[36]=61;ve[37]=15;ve[38]=3;ve[39]=16;ve[40]=30;ve[41]=62;ve[42]=71;ve[43]=11;ve[44]=63;ve[45]=72;ve[46]=31;ve[47]=5;ve[48]=12;ve[49]=17;ve[50]=32;ve[51]=49;ve[52]=18;ve[53]=33;ve[54]=39;ve[55]=64;ve[56]=23;ve[57]=34;ve[58]=57;ve[59]=6;ve[60]=46;ve[61]=40;ve[62]=58;ve[63]=73;ve[64]=41;ve[65]=50;ve[66]=74;ve[67]=7;ve[68]=24;ve[69]=42;ve[70]=51;ve[71]=65;ve[72]=25;ve[73]=43;ve[74]=66;ve[75]=75;
  for(e=0;e<E;e=e+1)cfg_write(3,e,ve[e]);fail=0;comparisons=0;
  for(t=0;t<4;t=t+1)begin load_case();@(negedge clk);start=1;@(negedge clk);start=0;
   while(!done)begin @(posedge clk);#1;if(variable_done)begin v=trace_variable;if($signed(trace_bias)!=ebias[v]||$signed(trace_sum)!=esum[v]||$signed(trace_marginal)!=emarg[v]||trace_decision!=edec[v])begin fail=fail+1;$display("VAR_TRACE_FAIL case=%0d var=%0d state=%0d bias=%0d/%0d sum=%0d/%0d marg=%0d/%0d dec=%0d/%0d",cid,v,dut.state,$signed(trace_bias),ebias[v],$signed(trace_sum),esum[v],$signed(trace_marginal),emarg[v],trace_decision,edec[v]);$fatal(1,"first variable mismatch");end comparisons=comparisons+4;end end
   if($signed(candidate_weight)!=eweight)begin fail=fail+1;$fatal(1,"weight mismatch");end
   for(e=0;e<E;e=e+1)begin if($signed(mem.nu[e])!==enu[e])begin fail=fail+1;$display("NU_FAIL case=%0d edge=%0d exp=%0d got=%0d",cid,e,enu[e],$signed(mem.nu[e]));$fatal(1,"first nu mismatch");end comparisons=comparisons+1;end
   for(v=0;v<V;v=v+1)if($signed(mem.marg[v])!==emarg[v]||mem.decision[v]!==edec[v])begin fail=fail+1;$fatal(1,"node memory mismatch");end
   $display("VARIABLE_CASE_RESULT case=%0d cycles=%0d reads=%0d responses=%0d writes=%0d waits=%0d mu_conflicts=%0d nu_conflicts=%0d retries=%0d failed=0",cid,cycles,reads,responses,writes,waits,muc,nuc,retries);
  end
  $display("VARIABLE_CONTROLLER_RESULT cases=4 variables=80 incidences=304 comparisons=%0d failed=%0d",comparisons,fail);if(fail)$fatal(1,"variable controller failure");$finish;
 end
endmodule

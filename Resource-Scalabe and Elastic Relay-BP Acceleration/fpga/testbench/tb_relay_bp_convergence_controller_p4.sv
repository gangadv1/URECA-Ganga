`timescale 1ns/1ps
module tb_relay_bp_convergence_controller_p4;
 localparam C=12,V=20,E=76,P=4;
 logic clk=0,rst=1,start=0,cfg_we=0;logic[3:0]cfg_kind;logic[31:0]cfg_addr;logic signed[31:0]cfg_data;
 logic busy,done,converged,req_valid,req_write,req_ready,rsp_valid,check_done;logic[3:0]req_kind,rsp_kind,req_mask,rsp_mask;
 logic[31:0]req_addr[0:3],rsp_addr[0:3];logic signed[21:0]req_wdata[0:3],rsp_data[0:3];
 logic[31:0]residual,cycles,reads,responses,waits,conflicts,retries,mrc,mwc;logic[3:0]trace_check;logic trace_predicted,trace_expected,trace_mismatch;
 integer cp[0:C],ev[0:E-1],decision[0:V-1],syndrome[0:C-1],predicted[0:C-1],exp_residual,exp_converged;
 integer fd,rc,one,cid,t,c,v,e,fail,comparisons;
 always #5 clk=~clk;
 relay_bp_response_memory #(.C(C),.V(V),.E(E),.STALL_PERIOD(6))mem(.clk,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.read_conflicts(mrc),.write_conflicts(mwc));
 relay_bp_convergence_controller_p4 #(.CHECKS(C),.VARIABLES(V),.EDGES(E))dut(.clk,.rst,.start,.busy,.done,.converged,.residual_weight(residual),
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,
  .check_done,.trace_check,.trace_predicted,.trace_expected,.trace_mismatch,.cycle_count(cycles),.read_requests(reads),.response_count(responses),
  .wait_cycles(waits),.decision_conflicts(conflicts),.retry_subsets(retries));
 task cfg_write(input integer k,input integer a,input integer d);begin @(negedge clk);cfg_kind=k;cfg_addr=a;cfg_data=d;cfg_we=1;@(negedge clk);cfg_we=0;end endtask
 task load_case;begin rc=$fscanf(fd,"%d",cid);
  for(v=0;v<V;v=v+1)begin one=$fscanf(fd," %d",decision[v]);rc=rc+one;end
  for(c=0;c<C;c=c+1)begin one=$fscanf(fd," %d",syndrome[c]);rc=rc+one;end
  for(c=0;c<C;c=c+1)begin one=$fscanf(fd," %d",predicted[c]);rc=rc+one;end
  one=$fscanf(fd," %d",exp_residual);rc=rc+one;one=$fscanf(fd," %d",exp_converged);rc=rc+one;
  for(v=0;v<V;v=v+1)cfg_write(11,v,decision[v]);for(c=0;c<C;c=c+1)cfg_write(5,c,syndrome[c]);end endtask
 initial begin
  cp[0]=0;cp[1]=4;cp[2]=8;cp[3]=13;cp[4]=19;cp[5]=26;cp[6]=35;cp[7]=44;cp[8]=47;cp[9]=52;cp[10]=59;cp[11]=67;cp[12]=76;
  ev[0]=3;ev[1]=4;ev[2]=6;ev[3]=9;ev[4]=0;ev[5]=12;ev[6]=15;ev[7]=18;ev[8]=0;ev[9]=1;ev[10]=3;ev[11]=10;ev[12]=12;ev[13]=2;ev[14]=4;ev[15]=8;ev[16]=9;ev[17]=12;ev[18]=13;ev[19]=2;ev[20]=3;ev[21]=6;ev[22]=7;ev[23]=14;ev[24]=18;ev[25]=19;ev[26]=0;ev[27]=3;ev[28]=5;ev[29]=6;ev[30]=9;ev[31]=11;ev[32]=12;ev[33]=13;ev[34]=14;ev[35]=0;ev[36]=2;ev[37]=3;ev[38]=7;ev[39]=13;ev[40]=16;ev[41]=17;ev[42]=18;ev[43]=19;ev[44]=3;ev[45]=5;ev[46]=15;ev[47]=0;ev[48]=2;ev[49]=12;ev[50]=17;ev[51]=18;ev[52]=0;ev[53]=1;ev[54]=3;ev[55]=5;ev[56]=7;ev[57]=14;ev[58]=16;ev[59]=3;ev[60]=5;ev[61]=7;ev[62]=9;ev[63]=10;ev[64]=13;ev[65]=18;ev[66]=19;ev[67]=0;ev[68]=1;ev[69]=3;ev[70]=6;ev[71]=9;ev[72]=10;ev[73]=16;ev[74]=17;ev[75]=19;
  fd=$fopen("fpga/verification/memory_backed_convergence/convergence_cases.txt","r");if(!fd)$fatal(1,"convergence vectors missing");
  repeat(2)@(posedge clk);#1 rst=0;for(c=0;c<=C;c=c+1)cfg_write(0,c,cp[c]);for(e=0;e<E;e=e+1)cfg_write(1,e,ev[e]);fail=0;comparisons=0;
  for(t=0;t<6;t=t+1)begin load_case();@(negedge clk);start=1;@(negedge clk);start=0;
   while(!done)begin @(posedge clk);#1;if(check_done)begin c=trace_check;if(trace_predicted!=predicted[c]||trace_expected!=syndrome[c]||trace_mismatch!=(predicted[c]^syndrome[c]))begin fail=fail+1;$display("CHECK_TRACE_FAIL case=%0d check=%0d state=%0d pred=%0d/%0d syn=%0d/%0d",cid,c,dut.state,trace_predicted,predicted[c],trace_expected,syndrome[c]);$fatal(1,"first predicted syndrome mismatch");end comparisons=comparisons+1;end end
   if(residual!=exp_residual||converged!=exp_converged)begin fail=fail+1;$display("FINAL_FAIL case=%0d residual=%0d/%0d conv=%0d/%0d",cid,residual,exp_residual,converged,exp_converged);$fatal(1,"convergence result mismatch");end
   $display("CONVERGENCE_CASE_RESULT case=%0d cycles=%0d reads=%0d responses=%0d waits=%0d conflicts=%0d retries=%0d residual=%0d converged=%0d failed=0",cid,cycles,reads,responses,waits,conflicts,retries,residual,converged);
  end
  $display("CONVERGENCE_CONTROLLER_RESULT cases=6 checks=%0d incidences=456 predicted_comparisons=%0d failed=%0d",6*C,comparisons,fail);if(fail)$fatal(1,"convergence controller failure");$finish;
 end
endmodule

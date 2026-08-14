`timescale 1ns/1ps
module tb_relay_bp_check_controller_p4;
 localparam C=12,V=20,E=76,P=4;
 logic clk=0,rst=1,start=0,cfg_we=0;logic[3:0]cfg_kind;logic[31:0]cfg_addr;logic signed[31:0]cfg_data;
 logic busy,done,req_valid,req_write,req_ready,rsp_valid;logic[3:0]req_kind,rsp_kind;logic[3:0]req_mask,rsp_mask;
 logic[31:0]req_addr[0:3],rsp_addr[0:3];logic signed[21:0]req_wdata[0:3],rsp_data[0:3];
 logic[31:0]cycles,reads,responses,writes,waits,mem_rc,mem_wc;logic[3:0]dbg_check;logic[6:0]dbg_pos;logic[5:0]dbg_state;
 integer H[0:C-1][0:V-1],cp[0:C],ev[0:E-1],syndrome[0:C-1],nu[0:E-1],expected[0:E-1];
 integer fd,rc,tmp,case_id,c,q,e,fail,total_comp,expected_reads,expected_writes;
 function integer find_check(input integer edge_num);integer z;begin find_check=0;for(z=0;z<C;z=z+1)if(edge_num>=cp[z]&&edge_num<cp[z+1])find_check=z;end endfunction
 always #5 clk=~clk;
 relay_bp_response_memory #(.C(C),.V(V),.E(E),.STALL_PERIOD(5)) mem(.clk,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,
  .read_conflicts(mem_rc),.write_conflicts(mem_wc));
 relay_bp_check_controller_p4 #(.CHECKS(C),.EDGES(E)) dut(.clk,.rst,.start,.busy,.done,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,
  .rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.cycle_count(cycles),.read_requests(reads),
  .response_count(responses),.mu_write_requests(writes),.wait_cycles(waits),
  .debug_check(dbg_check),.debug_position(dbg_pos),.debug_state(dbg_state));
 task cfg_write(input integer k,input integer a,input integer d);begin @(negedge clk);cfg_kind=k;cfg_addr=a;cfg_data=d;cfg_we=1;@(negedge clk);cfg_we=0;end endtask
 task load_case;begin
  rc=$fscanf(fd,"%d",case_id);for(c=0;c<C;c=c+1)rc=rc+$fscanf(fd," %d",syndrome[c]);
  for(e=0;e<E;e=e+1)rc=rc+$fscanf(fd," %d",nu[e]);for(e=0;e<E;e=e+1)rc=rc+$fscanf(fd," %d",expected[e]);
  for(c=0;c<C;c=c+1)cfg_write(5,c,syndrome[c]);for(e=0;e<E;e=e+1)cfg_write(8,e,nu[e]);
 end endtask
 initial begin
  // CSR from deterministic intermediate fixture.
  cp[0]=0;cp[1]=4;cp[2]=8;cp[3]=13;cp[4]=19;cp[5]=26;cp[6]=35;cp[7]=44;cp[8]=47;cp[9]=52;cp[10]=59;cp[11]=67;cp[12]=76;
  fd=$fopen("fpga/verification/memory_backed_check/check_cases.txt","r");if(!fd)$fatal(1,"check vectors missing");
  repeat(2)@(posedge clk);#1 rst=0;for(c=0;c<=C;c=c+1)cfg_write(0,c,cp[c]);
  fail=0;total_comp=0;expected_reads=0;expected_writes=0;
  for(c=0;c<C;c=c+1)begin expected_reads=expected_reads+3+2*((cp[c+1]-cp[c]+3)/4);expected_writes=expected_writes+((cp[c+1]-cp[c]+3)/4);end
  for(tmp=0;tmp<4;tmp=tmp+1)begin load_case();@(negedge clk);start=1;@(negedge clk);start=0;wait(done);#1;
   if(reads!=expected_reads||responses!=expected_reads||writes!=expected_writes||waits==0)begin fail=fail+1;$display("ACCOUNT_FAIL case=%0d reads=%0d rsp=%0d writes=%0d waits=%0d",case_id,reads,responses,writes,waits);end
   for(e=0;e<E;e=e+1)begin if($signed(mem.mu[e])!==expected[e])begin fail=fail+1;$display("MU_FAIL case=%0d check=%0d edge=%0d state=%0d nu=%0d exp=%0d got=%0d",case_id,find_check(e),e,dbg_state,nu[e],expected[e],$signed(mem.mu[e]));$fatal(1,"first mu mismatch");end total_comp=total_comp+1;end
   $display("CHECK_CASE_RESULT case=%0d cycles=%0d reads=%0d responses=%0d writes=%0d failed=0",case_id,cycles,reads,responses,writes);
  end
  $display("CHECK_CONTROLLER_RESULT cases=4 checks=48 incidences=%0d failed=%0d",total_comp,fail);if(fail)$fatal(1,"controller failures");$finish;
 end
endmodule

`timescale 1ns/1ps
module tb_relay_bp_tier2_check_p4;
 localparam C=1728,V=67752,E=391320,P=4;
 logic clk=0,rst=1,start=0,cfg_we=0;logic[3:0]cfg_kind;logic[31:0]cfg_addr;logic signed[31:0]cfg_data;
 logic busy,done,req_valid,req_write,req_ready,rsp_valid;logic[3:0]req_kind,rsp_kind,req_mask,rsp_mask;
 logic[31:0]req_addr[0:3],rsp_addr[0:3];logic signed[21:0]req_wdata[0:3],rsp_data[0:3];
 logic[31:0]cycles,reads,responses,writes,waits,mrc,mwc;logic[10:0]dbg_check;logic[18:0]dbg_pos;logic[5:0]dbg_state;
 logic signed[17:0]expected_mu[0:E-1];integer e,fail;
 always #5 clk=~clk;
 relay_bp_response_memory #(.C(C),.V(V),.E(E)) mem(.clk,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.read_conflicts(mrc),.write_conflicts(mwc));
 relay_bp_check_controller_p4 #(.CHECKS(C),.EDGES(E))dut(.clk,.rst,.start,.busy,.done,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,
  .cycle_count(cycles),.read_requests(reads),.response_count(responses),.mu_write_requests(writes),.wait_cycles(waits),
  .debug_check(dbg_check),.debug_position(dbg_pos),.debug_state(dbg_state));
 initial begin
  $readmemh("fpga/verification/tier2_p0p003/images/check_row_ptr.memh",mem.cp);
  $readmemh("fpga/verification/tier2_p0p003/images/check_edge_fault_ids_scalar.memh",mem.ev);
  $readmemh("fpga/verification/tier2_p0p003/images/syndrome_shot0_scalar.memh",mem.syndrome);
  $readmemh("fpga/verification/tier2_p0p003/images/nu_initial_scalar.memh",mem.nu);
  $readmemh("fpga/verification/tier2_p0p003/images/mu_expected_scalar.memh",expected_mu);
  repeat(2)@(posedge clk);#1 rst=0;@(negedge clk)start=1;@(negedge clk)start=0;wait(done);#1;
  fail=0;for(e=0;e<E;e=e+1)if($signed(mem.mu[e])!==$signed(expected_mu[e]))begin
   $display("TIER2_MU_FAIL edge=%0d state=%0d expected=%0d got=%0d",e,dbg_state,$signed(expected_mu[e]),$signed(mem.mu[e]));fail=fail+1;if(fail==1)$fatal(1,"first Tier-2 mu mismatch");end
  $display("TIER2_CHECK_RESULT checks=%0d incidences=%0d cycles=%0d reads=%0d responses=%0d writes=%0d waits=%0d failures=%0d",C,E,cycles,reads,responses,writes,waits,fail);
  if(fail)$fatal(1,"Tier-2 check phase failed");$finish;
 end
endmodule

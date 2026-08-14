`timescale 1ns/1ps
module tb_relay_bp_tier2_convergence_p4;
 localparam C=1728,V=67752,E=391320,P=4;
 logic clk=0,rst=1,start=0,cfg_we=0;logic[3:0]cfg_kind;logic[31:0]cfg_addr;logic signed[31:0]cfg_data;
 logic busy,done,converged,req_valid,req_write,req_ready,rsp_valid,check_done,trace_predicted,trace_expected,trace_mismatch;
 logic[3:0]req_kind,rsp_kind,req_mask,rsp_mask;logic[31:0]req_addr[0:3],rsp_addr[0:3];logic signed[21:0]req_wdata[0:3],rsp_data[0:3];
 logic[31:0]residual,cycles,reads,responses,waits,conflicts,retries,mrc,mwc;logic[10:0]trace_check;integer seen,mismatch_expected,c;
 logic[18:0]cp[0:C];logic[16:0]ev[0:E-1];logic decision[0:V-1],syndrome[0:C-1];logic parity;
 always #5 clk=~clk;
 relay_bp_response_memory #(.C(C),.V(V),.E(E))mem(.clk,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.read_conflicts(mrc),.write_conflicts(mwc));
 relay_bp_convergence_controller_p4 #(.CHECKS(C),.VARIABLES(V),.EDGES(E))dut(.clk,.rst,.start,.busy,.done,.converged,.residual_weight(residual),
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,
  .check_done,.trace_check,.trace_predicted,.trace_expected,.trace_mismatch,.cycle_count(cycles),.read_requests(reads),.response_count(responses),.wait_cycles(waits),.decision_conflicts(conflicts),.retry_subsets(retries));
 initial begin
  $readmemh("fpga/verification/tier2_p0p003/images/check_row_ptr.memh",mem.cp);$readmemh("fpga/verification/tier2_p0p003/images/check_row_ptr.memh",cp);
  $readmemh("fpga/verification/tier2_p0p003/images/check_edge_fault_ids_scalar.memh",mem.ev);$readmemh("fpga/verification/tier2_p0p003/images/check_edge_fault_ids_scalar.memh",ev);
  $readmemh("fpga/verification/tier2_p0p003/images/syndrome_shot0_scalar.memh",mem.syndrome);$readmemh("fpga/verification/tier2_p0p003/images/syndrome_shot0_scalar.memh",syndrome);
  $readmemh("fpga/verification/tier2_p0p003/images/decision_expected_scalar.memh",mem.decision);$readmemh("fpga/verification/tier2_p0p003/images/decision_expected_scalar.memh",decision);
  mismatch_expected=0;for(c=0;c<C;c=c+1)begin parity=0;for(integer e=cp[c];e<cp[c+1];e=e+1)parity=parity^decision[ev[e]];if(parity!=syndrome[c])mismatch_expected=mismatch_expected+1;end
  repeat(2)@(posedge clk);#1 rst=0;seen=0;@(negedge clk)start=1;@(negedge clk)start=0;
  while(!done)begin @(posedge clk);#1;if(check_done)begin seen=seen+1;if(trace_mismatch!==(trace_predicted^trace_expected))$fatal(1,"trace mismatch inconsistency check=%0d",trace_check);end end
  if(seen!=C||residual!=mismatch_expected||converged!=(mismatch_expected==0))$fatal(1,"Tier-2 convergence mismatch seen=%0d residual=%0d expected=%0d converged=%0d",seen,residual,mismatch_expected,converged);
  $display("TIER2_CONVERGENCE_RESULT checks=%0d incidences=%0d residual=%0d converged=%0d cycles=%0d reads=%0d responses=%0d waits=%0d conflicts=%0d retries=%0d",C,E,residual,converged,cycles,reads,responses,waits,conflicts,retries);$finish;
 end
endmodule

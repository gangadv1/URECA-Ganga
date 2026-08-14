`timescale 1ns/1ps
module tb_relay_bp_tier2_variable_p4;
 localparam C=1728,V=67752,E=391320,P=4;
 logic clk=0,rst=1,start=0,cfg_we=0;logic[3:0]cfg_kind;logic[31:0]cfg_addr;logic signed[31:0]cfg_data;
 logic busy,done,req_valid,req_write,req_ready,rsp_valid,variable_done;logic[3:0]req_kind,rsp_kind,req_mask,rsp_mask;
 logic[31:0]req_addr[0:3],rsp_addr[0:3];logic signed[21:0]req_wdata[0:3],rsp_data[0:3];
 logic[16:0]trace_variable;logic signed[17:0]trace_bias,trace_marginal,trace_weight;logic signed[21:0]trace_sum;logic trace_decision;
 logic signed[31:0]candidate_weight;logic[31:0]cycles,reads,responses,writes,waits,muc,nuc,retries,mrc,mwc;
 logic signed[17:0]expected_nu[0:E-1],expected_marg[0:V-1];logic expected_dec[0:V-1];integer e,v,fail;logic signed[31:0]expected_weight;
 always #5 clk=~clk;
 relay_bp_response_memory #(.C(C),.V(V),.E(E))mem(.clk,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,.read_conflicts(mrc),.write_conflicts(mwc));
 relay_bp_variable_controller_p4 #(.VARIABLES(V),.EDGES(E))dut(.clk,.rst,.start,.gamma_base(0),.busy,.done,
  .req_valid,.req_write,.req_kind,.req_mask,.req_addr,.req_wdata,.req_ready,.rsp_valid,.rsp_kind,.rsp_mask,.rsp_addr,.rsp_data,
  .variable_done,.trace_variable,.trace_bias,.trace_marginal,.trace_sum,.trace_decision,.trace_weight_contribution(trace_weight),
  .candidate_weight,.cycle_count(cycles),.read_requests(reads),.response_count(responses),.write_requests(writes),.wait_cycles(waits),
  .mu_conflicts(muc),.nu_conflicts(nuc),.retry_subsets(retries));
 initial begin
  $readmemh("fpga/verification/tier2_p0p003/images/variable_row_ptr.memh",mem.vp);
  $readmemh("fpga/verification/tier2_p0p003/images/variable_to_edge_scalar.memh",mem.ve);
  $readmemh("fpga/verification/tier2_p0p003/images/priors_scalar.memh",mem.prior);
  $readmemh("fpga/verification/tier2_p0p003/images/priors_scalar.memh",mem.marg);
  $readmemh("fpga/verification/tier2_p0p003/images/mu_expected_scalar.memh",mem.mu);
  $readmemh("fpga/verification/tier2_p0p003/images/nu_expected_scalar.memh",expected_nu);
  $readmemh("fpga/verification/tier2_p0p003/images/marginal_expected_scalar.memh",expected_marg);
  $readmemh("fpga/verification/tier2_p0p003/images/decision_expected_scalar.memh",expected_dec);
  for(v=0;v<V;v=v+1)mem.gamma[v]=2;
  expected_weight=0;for(v=0;v<V;v=v+1)if(expected_dec[v])expected_weight=expected_weight+$signed(mem.prior[v]);
  repeat(2)@(posedge clk);#1 rst=0;@(negedge clk)start=1;@(negedge clk)start=0;wait(done);#1;fail=0;
  if(candidate_weight!==expected_weight)begin $display("TIER2_WEIGHT_FAIL expected=%0d got=%0d",expected_weight,candidate_weight);fail=fail+1;end
  for(v=0;v<V;v=v+1)if($signed(mem.marg[v])!==$signed(expected_marg[v])||mem.decision[v]!==expected_dec[v])begin
   $display("TIER2_NODE_FAIL variable=%0d expected_m=%0d got_m=%0d expected_d=%0d got_d=%0d",v,$signed(expected_marg[v]),$signed(mem.marg[v]),expected_dec[v],mem.decision[v]);fail=fail+1;if(fail==1)$fatal(1,"first Tier-2 node mismatch");end
  for(e=0;e<E;e=e+1)if($signed(mem.nu[e])!==$signed(expected_nu[e]))begin
   $display("TIER2_NU_FAIL edge=%0d expected=%0d got=%0d",e,$signed(expected_nu[e]),$signed(mem.nu[e]));fail=fail+1;if(fail==1)$fatal(1,"first Tier-2 nu mismatch");end
  $display("TIER2_VARIABLE_RESULT variables=%0d incidences=%0d cycles=%0d reads=%0d responses=%0d writes=%0d waits=%0d mu_conflicts=%0d nu_conflicts=%0d retries=%0d failures=%0d",V,E,cycles,reads,responses,writes,waits,muc,nuc,retries,fail);
  if(fail)$fatal(1,"Tier-2 variable phase failed");$finish;
 end
endmodule

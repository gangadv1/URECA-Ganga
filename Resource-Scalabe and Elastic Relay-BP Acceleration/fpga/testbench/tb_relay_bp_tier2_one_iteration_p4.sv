`timescale 1ns/1ps
module tb_relay_bp_tier2_one_iteration_p4;
 localparam C=1728,V=67752,E=391320,L=1;
 logic clk=0,rst=1,start=0,cfg_we=0;logic[3:0]cfg_kind=0;logic[31:0]cfg_addr=0;logic signed[31:0]cfg_data=0;logic[15:0]first_limit=1,later_limit=1;
 logic busy,done,converged,failed,candidate_valid,iteration_done;logic[31:0]total_iterations,total_cycles,check_cycles,variable_cycles,convergence_cycles,relay_cycles,wait_cycles;logic[0:0]relay_legs,trace_leg;logic[15:0]trace_iteration;logic trace_converged;logic signed[31:0]selected_weight,trace_weight;
 logic gamma_start,gamma_ready;logic[0:0]gamma_leg_index;logic[31:0]gamma_variable_count;
 logic signed[17:0]expected_mu[0:E-1],expected_nu[0:E-1],expected_marg[0:V-1];logic expected_dec[0:V-1];integer e,v,fail;
 logic signed[17:0]load_prior[0:V-1];
 always #5 clk=~clk;
 relay_bp_single_engine_memory_p4 #(.C(C),.V(V),.E(E),.L(L),
  .CP_INIT("fpga/verification/tier2_p0p003/images/check_row_ptr.memh"),.VP_INIT("fpga/verification/tier2_p0p003/images/variable_row_ptr.memh"),
  .EV_B0_INIT("fpga/verification/tier2_p0p003/images/check_edge_fault_ids_b0.memh"),.EV_B1_INIT("fpga/verification/tier2_p0p003/images/check_edge_fault_ids_b1.memh"),
  .EV_B2_INIT("fpga/verification/tier2_p0p003/images/check_edge_fault_ids_b2.memh"),.EV_B3_INIT("fpga/verification/tier2_p0p003/images/check_edge_fault_ids_b3.memh"),
  .VE_B0_INIT("fpga/verification/tier2_p0p003/images/variable_to_edge_b0.memh"),.VE_B1_INIT("fpga/verification/tier2_p0p003/images/variable_to_edge_b1.memh"),
  .VE_B2_INIT("fpga/verification/tier2_p0p003/images/variable_to_edge_b2.memh"),.VE_B3_INIT("fpga/verification/tier2_p0p003/images/variable_to_edge_b3.memh"),
  .SYN_B0_INIT("fpga/verification/tier2_p0p003/images/syndrome_shot0_b0.memh"),.SYN_B1_INIT("fpga/verification/tier2_p0p003/images/syndrome_shot0_b1.memh"),
  .SYN_B2_INIT("fpga/verification/tier2_p0p003/images/syndrome_shot0_b2.memh"),.SYN_B3_INIT("fpga/verification/tier2_p0p003/images/syndrome_shot0_b3.memh"))dut(.clk,.rst,.start,.cancel_request(1'b0),.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,.first_limit,.later_limit,
  .first_gamma(5'sd2),.gamma_valid(1'b0),.gamma_variable_index(17'd0),.gamma_value(5'sd0),.gamma_done(1'b0),.gamma_start,.gamma_leg_index,.gamma_variable_count,.gamma_ready,
  .gamma_seed_valid(1'b0),.gamma_seed(64'd0),.gamma_updated_state(64'd0),.gamma_seed_load(),.gamma_seed_state(),
  .busy,.done,.converged,.failed,.candidate_valid,.total_iterations,.relay_legs,.selected_weight,.total_cycles,.iteration_done,.trace_leg,.trace_iteration,.trace_converged,.trace_weight,
  .check_cycles,.variable_cycles,.convergence_cycles,.relay_cycles,.wait_cycles);
 initial begin
  $readmemh("fpga/verification/tier2_p0p003/images/priors_scalar.memh",load_prior);
  for(v=0;v<V;v=v+1)begin
   case(v%4)0:begin dut.memory.prior_memory.bank0[v/4]=load_prior[v];dut.memory.marginal_memory.bank0[v/4]=load_prior[v];end 1:begin dut.memory.prior_memory.bank1[v/4]=load_prior[v];dut.memory.marginal_memory.bank1[v/4]=load_prior[v];end 2:begin dut.memory.prior_memory.bank2[v/4]=load_prior[v];dut.memory.marginal_memory.bank2[v/4]=load_prior[v];end 3:begin dut.memory.prior_memory.bank3[v/4]=load_prior[v];dut.memory.marginal_memory.bank3[v/4]=load_prior[v];end endcase
  end
  $readmemh("fpga/verification/tier2_p0p003/images/mu_expected_scalar.memh",expected_mu);$readmemh("fpga/verification/tier2_p0p003/images/nu_expected_scalar.memh",expected_nu);
  $readmemh("fpga/verification/tier2_p0p003/images/marginal_expected_scalar.memh",expected_marg);$readmemh("fpga/verification/tier2_p0p003/images/decision_expected_scalar.memh",expected_dec);
  repeat(2)@(posedge clk);#1 rst=0;@(negedge clk)start=1;@(negedge clk)start=0;wait(done);#1;fail=0;
  if(total_iterations!=1||relay_legs!=1||!failed||converged)$fatal(1,"iteration accounting/status mismatch");
  for(e=0;e<E;e=e+1)begin
   if($signed(dut.memory.mu[e])!==$signed(expected_mu[e]))begin $display("ITER_MU_FAIL edge=%0d",e);fail=fail+1;end
   if($signed(dut.memory.nu[e])!==$signed(expected_nu[e]))begin $display("ITER_NU_FAIL edge=%0d",e);fail=fail+1;end
   if(fail)$fatal(1,"first Tier-2 integrated edge mismatch");
  end
  for(v=0;v<V;v=v+1)begin if($signed(dut.memory.marg[v])!==$signed(expected_marg[v])||dut.memory.decision[v]!==expected_dec[v])begin $display("ITER_NODE_FAIL variable=%0d",v);fail=fail+1;end if(fail)$fatal(1,"first Tier-2 integrated node mismatch");end
  $display("TIER2_ONE_ITERATION_RESULT iterations=%0d legs=%0d failed=%0d cycles=%0d check=%0d variable=%0d convergence=%0d relay_init=%0d waits=%0d failures=%0d",total_iterations,relay_legs,failed,total_cycles,check_cycles,variable_cycles,convergence_cycles,relay_cycles,wait_cycles,fail);$finish;
 end
endmodule

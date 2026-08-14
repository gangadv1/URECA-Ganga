`timescale 1ns/1ps
module tb_relay_bp_single_engine_memory_p4;
 parameter integer TB_STALL_PERIOD=7;
 localparam C=12,V=20,E=76,L=2;
 logic clk=0,rst=1,start=0,cfg_we=0;logic[3:0]cfg_kind;logic[31:0]cfg_addr;logic signed[31:0]cfg_data;
 logic busy,done,converged,failed,candidate_valid,iteration_done,trace_converged;logic[31:0]total_iterations,total_cycles,cc,vc,xc,rcyc,wc;
 logic correction_req=0,correction_ready,correction_rsp_valid;logic[31:0]correction_word=0;logic[3:0]correction_bits,correction_mask;
 logic gamma_start,gamma_ready,gamma_valid,gamma_done;logic[1:0]gamma_leg_index;logic[31:0]gamma_variable_count;logic[4:0]gamma_variable_index;logic signed[4:0]gamma_value;
 logic[1:0]relay_legs,trace_leg;logic[15:0]trace_iteration;logic signed[31:0]selected_weight,trace_weight;
 integer cp[0:C],ev[0:E-1],vp[0:V],ve[0:E-1],gamma[0:L*V-1],prior[0:V-1],syn[0:C-1],final_dec[0:V-1];
 integer emu[0:E-1],emarg[0:V-1],enu[0:E-1],edec[0:V-1];integer gf,sf,itf,one,q,shot,recshot,recl,reci,recconv,nrec,expconv,explegs,expweight,failc,records,timeout;
 always #5 clk=~clk;
relay_bp_single_engine_memory_p4 #(.C(C),.V(V),.E(E),.L(L),.STALL_PERIOD(TB_STALL_PERIOD))dut(.clk,.rst,.start,.cancel_request(1'b0),.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,.first_limit(16'd2),.later_limit(16'd3),
  .first_gamma(5'sd2),.gamma_valid,.gamma_variable_index,.gamma_value,.gamma_done,.gamma_start,.gamma_leg_index,.gamma_variable_count,.gamma_ready,
  .gamma_seed_valid(1'b0),.gamma_seed(64'd0),.gamma_updated_state(64'd0),.gamma_seed_load(),.gamma_seed_state(),
  .busy,.done,.converged,.failed,.candidate_valid,.total_iterations,.relay_legs,.selected_weight,.total_cycles,.iteration_done,.trace_leg,.trace_iteration,.trace_converged,.trace_weight,
  .correction_req,.correction_word,.correction_ready,.correction_rsp_valid,.correction_bits,.correction_mask,
  .check_cycles(cc),.variable_cycles(vc),.convergence_cycles(xc),.relay_cycles(rcyc),.wait_cycles(wc));
 relay_bp_deterministic_gamma_source #(.V(V),.L(L),.STALL_PERIOD(TB_STALL_PERIOD==0?0:5))gamma_source(.clk,.rst,.start(gamma_start),.abort(1'b0),.leg_index(gamma_leg_index),.variable_count(gamma_variable_count),.ready(gamma_ready),.valid(gamma_valid),.variable_index(gamma_variable_index),.value(gamma_value),.done(gamma_done));
 task cfg_write(input integer k,input integer a,input integer d);begin @(negedge clk);cfg_kind=k;cfg_addr=a;cfg_data=d;cfg_we=1;@(negedge clk);cfg_we=0;end endtask
 task read_iteration;begin one=$fscanf(itf,"%d %d %d %d",recshot,recl,reci,recconv);for(q=0;q<E;q=q+1)one=one+$fscanf(itf," %d",emu[q]);for(q=0;q<V;q=q+1)one=one+$fscanf(itf," %d",emarg[q]);for(q=0;q<E;q=q+1)one=one+$fscanf(itf," %d",enu[q]);for(q=0;q<V;q=q+1)one=one+$fscanf(itf," %d",edec[q]);records=records+1;end endtask
 initial begin
  gf=$fopen("fpga/verification/memory_backed_engine/graph.txt","r");sf=$fopen("fpga/verification/memory_backed_engine/shots.txt","r");itf=$fopen("fpga/verification/memory_backed_engine/iterations.txt","r");if(!gf||!sf||!itf)$fatal(1,"engine vectors missing");
  for(q=0;q<=C;q=q+1)one=$fscanf(gf,"%d",cp[q]);for(q=0;q<E;q=q+1)one=$fscanf(gf,"%d",ev[q]);for(q=0;q<=V;q=q+1)one=$fscanf(gf,"%d",vp[q]);for(q=0;q<E;q=q+1)one=$fscanf(gf,"%d",ve[q]);for(q=0;q<L*V;q=q+1)one=$fscanf(gf,"%d",gamma[q]);
  for(q=0;q<L*V;q=q+1)gamma_source.fixture[q]=gamma[q];
  repeat(2)@(posedge clk);#1 rst=0;for(q=0;q<=C;q=q+1)cfg_write(0,q,cp[q]);for(q=0;q<E;q=q+1)begin cfg_write(1,q,ev[q]);cfg_write(3,q,ve[q]);end for(q=0;q<=V;q=q+1)cfg_write(2,q,vp[q]);
  failc=0;records=0;read_iteration();
  for(shot=0;shot<3;shot=shot+1)begin one=$fscanf(sf,"%d",recshot);for(q=0;q<V;q=q+1)one=one+$fscanf(sf," %d",prior[q]);for(q=0;q<C;q=q+1)one=one+$fscanf(sf," %d",syn[q]);one=one+$fscanf(sf," %d %d %d %d",nrec,expconv,explegs,expweight);for(q=0;q<V;q=q+1)one=one+$fscanf(sf," %d",final_dec[q]);
   for(q=0;q<V;q=q+1)begin cfg_write(4,q,prior[q]);cfg_write(10,q,prior[q]);end for(q=0;q<C;q=q+1)cfg_write(5,q,syn[q]);@(negedge clk);start=1;@(negedge clk);start=0;timeout=0;
   while(!done&&timeout<200000)begin @(posedge clk);#1;timeout=timeout+1;if(iteration_done)begin
    if(recshot!=shot||trace_leg!=recl||trace_iteration!=reci)begin $display("ITER_ID_FAIL shot=%0d exp_shot=%0d leg=%0d/%0d iter=%0d/%0d",shot,recshot,trace_leg,recl,trace_iteration,reci);$fatal(1,"iteration identity mismatch");end
    for(q=0;q<E;q=q+1)begin if($signed(dut.memory.mu[q])!==emu[q])begin $display("MU_FAIL shot=%0d leg=%0d iter=%0d edge=%0d exp=%0d got=%0d",shot,recl,reci,q,emu[q],$signed(dut.memory.mu[q]));$fatal(1,"mu mismatch");end if($signed(dut.memory.nu[q])!==enu[q])begin $display("NU_FAIL shot=%0d leg=%0d iter=%0d edge=%0d exp=%0d got=%0d gamma0=%0d",shot,recl,reci,q,enu[q],$signed(dut.memory.nu[q]),$signed(dut.memory.gamma[0]));$fatal(1,"nu mismatch");end end
    for(q=0;q<V;q=q+1)if($signed(dut.memory.marg[q])!==emarg[q]||dut.memory.decision[q]!==edec[q])$fatal(1,"node mismatch shot=%0d var=%0d",shot,q);
    if(trace_converged!=recconv)begin $display("CONV_FAIL shot=%0d leg=%0d iter=%0d exp=%0d got=%0d residual=%0d",shot,recl,reci,recconv,trace_converged,dut.conv_residual);$fatal(1,"convergence mismatch");end
    if(records<12)read_iteration();end end
   if(!done)$fatal(1,"engine timeout state=%0d owner=%0d",dut.state,dut.owner);
   if(converged!=expconv||failed==expconv||total_iterations!=nrec||relay_legs!=explegs)$fatal(1,"final status mismatch shot=%0d",shot);
   if(expconv&&(!candidate_valid||$signed(selected_weight)!=expweight))$fatal(1,"candidate mismatch shot=%0d",shot);if(!expconv&&candidate_valid)$fatal(1,"invalid failure candidate");
   if(expconv)for(q=0;q<(V+3)/4;q=q+1)begin @(negedge clk);correction_word=q;correction_req=1;@(negedge clk)correction_req=0;wait(correction_rsp_valid);#1;for(one=0;one<4;one=one+1)if(q*4+one<V&&(!correction_mask[one]||correction_bits[one]!==final_dec[q*4+one]))$fatal(1,"correction readout mismatch shot=%0d var=%0d",shot,q*4+one);end
   for(q=0;q<V;q=q+1)if(dut.memory.decision[q]!==final_dec[q])$fatal(1,"final correction mismatch shot=%0d var=%0d",shot,q);
   $display("ENGINE_SHOT_RESULT shot=%0d converged=%0d iterations=%0d legs=%0d weight=%0d total_cycles=%0d check=%0d variable=%0d convergence=%0d relay=%0d waits=%0d failed=0",shot,converged,total_iterations,relay_legs,$signed(selected_weight),total_cycles,cc,vc,xc,rcyc,wc);
  end
  $display("MEMORY_ENGINE_RESULT shots=3 iteration_records=12 failed=%0d",failc);$finish;
 end
endmodule

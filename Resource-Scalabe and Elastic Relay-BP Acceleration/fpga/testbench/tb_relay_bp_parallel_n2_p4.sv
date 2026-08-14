`timescale 1ns/1ps
module tb_relay_bp_parallel_n2_p4;
 parameter integer S0=0,S1=0,CANCEL=1;localparam C=12,V=20,E=76,L=2;
 logic clk=0,rst=1,start=0,cfg_we=0;logic[3:0]cfg_kind;logic[31:0]cfg_addr,frame_id=32'h1234;logic signed[31:0]cfg_data;logic[15:0]first_limit=2,later_limit=3;
 logic g0s,g1s,g0r,g1r,g0v,g1v,g0d,g1d;logic[1:0]g0l,g1l;logic[31:0]g0n,g1n;logic[4:0]g0i,g1i;logic signed[4:0]g0x,g1x;
 logic sa;logic[31:0]af;logic b0,b1,d0,d1,f0,f1,c0,c1;logic signed[31:0]w0,w1;logic[31:0]it0,it1;logic[1:0]l0,l1;logic global_done,global_failed,global_candidate_valid,winning_engine_id,same_cycle_success;logic signed[31:0]winning_weight;logic[31:0]winning_iteration_count,first_success_cycle,winning_frame_id,dc0,dc1;logic[1:0]winning_leg_count;
 logic correction_req=0,correction_ready,correction_rsp_valid,pair_quiescent,ca0,ca1,cx0,cx1,lcp;logic[31:0]correction_word=0,crq,cak,cqu;logic[3:0]correction_bits,correction_mask;
 integer cp[0:C],ev[0:E-1],vp[0:V],ve[0:E-1],gamma[0:L*V-1],prior[0:V-1],syn[0:C-1],final_dec[0:V-1];integer gf,sf,itf,one,q,shot,nrec,expconv,explegs,expweight,timeout,recshot,records;
 always #5 clk=~clk;
 relay_bp_parallel_n2_p4 #(.C(C),.V(V),.E(E),.L(L),.STALL0(S0),.STALL1(S1),.CANCEL_ENABLE(CANCEL))dut(.clk,.rst,.start,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,.first_limit,.later_limit,.first_gamma(5'sd2),.frame_id,
  .gamma0_valid(g0v),.gamma0_variable_index(g0i),.gamma0_value(g0x),.gamma0_done(g0d),.gamma0_seed_valid(1'b0),.gamma0_seed(0),.gamma0_updated_state(0),.gamma0_start(g0s),.gamma0_leg_index(g0l),.gamma0_variable_count(g0n),.gamma0_ready(g0r),.gamma0_seed_load(),.gamma0_seed_state(),
  .gamma1_valid(g1v),.gamma1_variable_index(g1i),.gamma1_value(g1x),.gamma1_done(g1d),.gamma1_seed_valid(1'b0),.gamma1_seed(1),.gamma1_updated_state(1),.gamma1_start(g1s),.gamma1_leg_index(g1l),.gamma1_variable_count(g1n),.gamma1_ready(g1r),.gamma1_seed_load(),.gamma1_seed_state(),
  .start_accepted(sa),.active_frame_id(af),.engine0_busy(b0),.engine1_busy(b1),.engine0_done(d0),.engine1_done(d1),.engine0_failed(f0),.engine1_failed(f1),.engine0_candidate_valid(c0),.engine1_candidate_valid(c1),.engine0_weight(w0),.engine1_weight(w1),.engine0_iterations(it0),.engine1_iterations(it1),.engine0_legs(l0),.engine1_legs(l1),.global_done,.global_failed,.global_candidate_valid,.winning_engine_id,.winning_weight,.winning_iteration_count,.winning_leg_count,.same_cycle_success,.first_success_cycle,.winning_frame_id,.engine0_completion_cycle(dc0),.engine1_completion_cycle(dc1),.engine0_cancel_ack(ca0),.engine1_cancel_ack(ca1),.engine0_cancelled(cx0),.engine1_cancelled(cx1),.pair_quiescent,.loser_cancel_pending(lcp),.loser_cancel_request_cycle(crq),.loser_cancel_ack_cycle(cak),.loser_quiescent_cycle(cqu),.correction_req,.correction_word,.correction_ready,.correction_rsp_valid,.correction_bits,.correction_mask);
 relay_bp_deterministic_gamma_source #(.V(V),.L(L),.STALL_PERIOD(S0?7:0))gs0(.clk,.rst,.start(g0s),.abort(dut.gamma0_abort),.leg_index(g0l),.variable_count(g0n),.ready(g0r),.valid(g0v),.variable_index(g0i),.value(g0x),.done(g0d));
 relay_bp_deterministic_gamma_source #(.V(V),.L(L),.STALL_PERIOD(S1?11:0))gs1(.clk,.rst,.start(g1s),.abort(dut.gamma1_abort),.leg_index(g1l),.variable_count(g1n),.ready(g1r),.valid(g1v),.variable_index(g1i),.value(g1x),.done(g1d));
 task cfg(input integer k,a,d);begin @(negedge clk);cfg_we=1;cfg_kind=k;cfg_addr=a;cfg_data=d;@(negedge clk);cfg_we=0;end endtask
 task readcorr;begin for(q=0;q<(V+3)/4;q=q+1)begin @(negedge clk);correction_word=q;correction_req=1;@(negedge clk)correction_req=0;wait(correction_rsp_valid);#1;for(one=0;one<4;one=one+1)if(q*4+one<V&&correction_bits[one]!==final_dec[q*4+one])$fatal(1,"winner correction mismatch var=%0d",q*4+one);end end endtask
 initial begin
  gf=$fopen("fpga/verification/memory_backed_engine/graph.txt","r");sf=$fopen("fpga/verification/memory_backed_engine/shots.txt","r");itf=$fopen("fpga/verification/memory_backed_engine/iterations.txt","r");if(!gf||!sf)$fatal(1,"vectors missing");
  for(q=0;q<=C;q=q+1)one=$fscanf(gf,"%d",cp[q]);for(q=0;q<E;q=q+1)one=$fscanf(gf,"%d",ev[q]);for(q=0;q<=V;q=q+1)one=$fscanf(gf,"%d",vp[q]);for(q=0;q<E;q=q+1)one=$fscanf(gf,"%d",ve[q]);for(q=0;q<L*V;q=q+1)one=$fscanf(gf,"%d",gamma[q]);for(q=0;q<L*V;q=q+1)begin gs0.fixture[q]=gamma[q];gs1.fixture[q]=gamma[q];end
  repeat(2)@(posedge clk);rst=0;for(q=0;q<=C;q=q+1)cfg(0,q,cp[q]);for(q=0;q<E;q=q+1)begin cfg(1,q,ev[q]);cfg(3,q,ve[q]);end for(q=0;q<=V;q=q+1)cfg(2,q,vp[q]);
  for(shot=0;shot<3;shot=shot+1)begin one=$fscanf(sf,"%d",recshot);for(q=0;q<V;q=q+1)one=one+$fscanf(sf," %d",prior[q]);for(q=0;q<C;q=q+1)one=one+$fscanf(sf," %d",syn[q]);one=one+$fscanf(sf," %d %d %d %d",nrec,expconv,explegs,expweight);for(q=0;q<V;q=q+1)one=one+$fscanf(sf," %d",final_dec[q]);for(q=0;q<V;q=q+1)begin cfg(4,q,prior[q]);cfg(10,q,prior[q]);end for(q=0;q<C;q=q+1)cfg(5,q,syn[q]);
   @(negedge clk)start=1;@(negedge clk)start=0;timeout=0;while((!global_done||!pair_quiescent)&&timeout<250000)begin @(posedge clk);timeout=timeout+1;end repeat(3)@(posedge clk);
   if(!global_done)$fatal(1,"N2 timeout shot=%0d",shot);
   if(expconv&&(winning_iteration_count!=nrec||winning_leg_count!=explegs||!global_candidate_valid||global_failed))$fatal(1,"N2 winner status mismatch shot=%0d",shot);
   if(!expconv&&(it0!=nrec||it1!=nrec||!f0||!f1||!global_failed||global_candidate_valid))$fatal(1,"N2 failure status mismatch shot=%0d",shot);
   for(q=0;q<V;q=q+1)if(expconv&&(winning_engine_id?dut.engine_1.memory.decision[q]:dut.engine_0.memory.decision[q])!==final_dec[q])$fatal(1,"winner node-state mismatch shot=%0d var=%0d",shot,q);
   if(expconv)begin readcorr();if(!global_done||!global_candidate_valid||global_failed||winning_frame_id!=frame_id)$fatal(1,"invalid global success");end else if(!global_done||!global_failed||global_candidate_valid)$fatal(1,"invalid global failure");
   $display("N2_SHOT_RESULT shot=%0d converged=%0d e0_completion=%0d e1_completion=%0d first_success=%0d winner=%0d same_cycle=%0d cancel_req=%0d cancel_ack=%0d quiescent=%0d cancelled0=%0d cancelled1=%0d cleanup=%0d global_done=%0d failed=0",shot,expconv,dc0,dc1,first_success_cycle,winning_engine_id,same_cycle_success,crq,cak,cqu,cx0,cx1,expconv?cqu-first_success_cycle:0,global_done);
  end
  $display("N2_INTERMEDIATE_RESULT shots=3 engines=2 paired_trajectories=6 failures=0 stall0=%0d stall1=%0d",S0,S1);$finish;
 end
endmodule

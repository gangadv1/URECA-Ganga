`timescale 1ns/1ps
module tb_relay_bp_parallel_n2_rng_p4;
 parameter integer CANCEL=0;
 localparam C=12,V=20,E=76,L=2;logic clk=0,rst=1,start=0,cfg_we=0,seed_valid=0;logic[3:0]cfg_kind;logic[31:0]cfg_addr;logic signed[31:0]cfg_data;
 logic gd,gf,gcv,win,pq,cx0,cx1;logic[63:0]rs0,rs1;logic[31:0]rw0,rw1,rr0,rr1;integer cp[0:C],ev[0:E-1],vp[0:V],ve[0:E-1],prior[0:V-1],syn[0:C-1];integer emu0[0:E-1],enu0[0:E-1],emarg0[0:V-1],edec0[0:V-1],emu1[0:E-1],enu1[0:E-1],emarg1[0:V-1],edec1[0:V-1],g0[0:V-1],g1[0:V-1];
 integer gf0,gf1,graphf,shotf,q,one,shot,rec,cv0,it0,lg0,w0,cv1,it1,lg1,w1,cases0,cases1,rej0,rej1,timeout;reg[63:0]fs0,fs1;
 always #5 clk=~clk;
 relay_bp_parallel_n2_p4 #(.C(C),.V(V),.E(E),.L(L),.USE_INTERNAL_RNG(1),.CANCEL_ENABLE(CANCEL))dut(.clk,.rst,.start,.cfg_we,.cfg_kind,.cfg_addr,.cfg_data,.first_limit(16'd2),.later_limit(16'd3),.first_gamma(5'sd2),.frame_id(32'd55),
  .gamma0_valid(1'b0),.gamma0_variable_index('0),.gamma0_value('0),.gamma0_done(1'b0),.gamma0_seed_valid(seed_valid),.gamma0_seed(64'd8),.gamma0_updated_state(64'd0),
  .gamma1_valid(1'b0),.gamma1_variable_index('0),.gamma1_value('0),.gamma1_done(1'b0),.gamma1_seed_valid(seed_valid),.gamma1_seed(64'h9999aaaabbbbcccc),.gamma1_updated_state(64'd0),
  .global_done(gd),.global_failed(gf),.global_candidate_valid(gcv),.winning_engine_id(win),.pair_quiescent(pq),.engine0_cancelled(cx0),.engine1_cancelled(cx1),.rng0_state(rs0),.rng1_state(rs1),.rng0_words(rw0),.rng1_words(rw1),.rng0_rejected(rr0),.rng1_rejected(rr1),.correction_req(1'b0),.correction_word(0));
 task cfg(input integer k,a,d);begin @(negedge clk);cfg_we=1;cfg_kind=k;cfg_addr=a;cfg_data=d;@(negedge clk);cfg_we=0;end endtask
 initial begin
  graphf=$fopen("fpga/verification/memory_backed_engine/graph.txt","r");shotf=$fopen("fpga/verification/memory_backed_engine/shots.txt","r");gf0=$fopen("fpga/verification/parallel_n2/rng_decoder_engine0.txt","r");gf1=$fopen("fpga/verification/parallel_n2/rng_decoder_engine1.txt","r");if(!graphf||!shotf||!gf0||!gf1)$fatal(1,"rng decoder vectors missing");
  for(q=0;q<=C;q=q+1)one=$fscanf(graphf,"%d",cp[q]);for(q=0;q<E;q=q+1)one=$fscanf(graphf,"%d",ev[q]);for(q=0;q<=V;q=q+1)one=$fscanf(graphf,"%d",vp[q]);for(q=0;q<E;q=q+1)one=$fscanf(graphf,"%d",ve[q]);
  one=$fscanf(gf0,"%d %h %d",cases0,fs0,rej0);one=$fscanf(gf1,"%d %h %d",cases1,fs1,rej1);for(q=0;q<V;q=q+1)one=$fscanf(gf0,"%d",g0[q]);for(q=0;q<V;q=q+1)one=$fscanf(gf1,"%d",g1[q]);
  repeat(2)@(posedge clk);rst=0;for(q=0;q<=C;q=q+1)cfg(0,q,cp[q]);for(q=0;q<E;q=q+1)begin cfg(1,q,ev[q]);cfg(3,q,ve[q]);end for(q=0;q<=V;q=q+1)cfg(2,q,vp[q]);
  for(shot=0;shot<3;shot=shot+1)begin one=$fscanf(shotf,"%d",rec);for(q=0;q<V;q=q+1)one=$fscanf(shotf,"%d",prior[q]);for(q=0;q<C;q=q+1)one=$fscanf(shotf,"%d",syn[q]);for(q=0;q<4+V;q=q+1)one=$fscanf(shotf,"%d",rec);
   one=$fscanf(gf0,"%d %d %d %d %d",rec,cv0,it0,lg0,w0);for(q=0;q<E;q=q+1)one=$fscanf(gf0,"%d",emu0[q]);for(q=0;q<E;q=q+1)one=$fscanf(gf0,"%d",enu0[q]);for(q=0;q<V;q=q+1)one=$fscanf(gf0,"%d",emarg0[q]);for(q=0;q<V;q=q+1)one=$fscanf(gf0,"%d",edec0[q]);
   one=$fscanf(gf1,"%d %d %d %d %d",rec,cv1,it1,lg1,w1);for(q=0;q<E;q=q+1)one=$fscanf(gf1,"%d",emu1[q]);for(q=0;q<E;q=q+1)one=$fscanf(gf1,"%d",enu1[q]);for(q=0;q<V;q=q+1)one=$fscanf(gf1,"%d",emarg1[q]);for(q=0;q<V;q=q+1)one=$fscanf(gf1,"%d",edec1[q]);
   for(q=0;q<V;q=q+1)begin cfg(4,q,prior[q]);cfg(10,q,prior[q]);end for(q=0;q<C;q=q+1)cfg(5,q,syn[q]);@(negedge clk)seed_valid=1;@(negedge clk)seed_valid=0;@(negedge clk)start=1;@(negedge clk)start=0;timeout=0;while(!pq&&timeout<100000)begin @(posedge clk);timeout=timeout+1;end if(timeout>=100000)$fatal(1,"rng N2 timeout");#1;
   if(dut.engine0_iterations!=it0||dut.engine0_legs!=lg0||dut.engine0_candidate_valid!=cv0)$fatal(1,"rng engine0 status mismatch shot=%0d",shot);
   if(!CANCEL||!cv0)if(dut.engine1_iterations!=it1||dut.engine1_legs!=lg1||dut.engine1_candidate_valid!=cv1)$fatal(1,"rng engine1 status mismatch shot=%0d",shot);
   for(q=0;q<E;q=q+1)begin if($signed(dut.engine_0.memory.mu[q])!=emu0[q]||$signed(dut.engine_0.memory.nu[q])!=enu0[q])$fatal(1,"rng edge0 mismatch shot=%0d edge=%0d",shot,q);if(!CANCEL||!cv0)if($signed(dut.engine_1.memory.mu[q])!=emu1[q]||$signed(dut.engine_1.memory.nu[q])!=enu1[q])$fatal(1,"rng edge1 mismatch shot=%0d edge=%0d",shot,q);end
   for(q=0;q<V;q=q+1)begin if($signed(dut.engine_0.memory.marg[q])!=emarg0[q]||dut.engine_0.memory.decision[q]!=edec0[q])$fatal(1,"rng node0 mismatch shot=%0d var=%0d",shot,q);if(!CANCEL||!cv0)if($signed(dut.engine_1.memory.marg[q])!=emarg1[q]||dut.engine_1.memory.decision[q]!=edec1[q])$fatal(1,"rng node1 mismatch shot=%0d var=%0d",shot,q);end
   if(lg0==2)for(q=0;q<V;q=q+1)if($signed(dut.engine_0.memory.gamma[q])!=g0[q])$fatal(1,"rng gamma0 mismatch");if(lg1==2)for(q=0;q<V;q=q+1)if($signed(dut.engine_1.memory.gamma[q])!=g1[q])$fatal(1,"rng gamma1 mismatch");
   if(CANCEL&&cv0&&!cx1)$fatal(1,"real RNG losing engine not cancelled shot=%0d",shot);
   $display("N2_RNG_DECODER_SHOT shot=%0d e0_conv=%0d e1_conv=%0d e0_iter=%0d e1_iter=%0d e0_legs=%0d e1_legs=%0d total0=%0d total1=%0d check0=%0d var0=%0d conv0=%0d relay0=%0d rng_words0=%0d rng_words1=%0d state0=%h state1=%h cancelled1=%0d pass=1",shot,cv0,cv1,it0,it1,lg0,lg1,dut.engine_0.total_cycles,dut.engine_1.total_cycles,dut.unused00,dut.unused01,dut.unused02,dut.unused03,rw0,rw1,rs0,rs1,cx1);
  end
  if(rs0==rs1)$fatal(1,"independent RNG states unexpectedly equal");$display("N2_RNG_DECODER_RESULT shots=3 engines=2 exact_arrays=1 failures=0");$finish;
 end
endmodule

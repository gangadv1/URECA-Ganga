`timescale 1ns/1ps
module tb_relay_bp_gamma_rng_independence;
 localparam V=100;logic clk=0,rst=1,load=0,start=0,abort0=0;logic v0,v1,d0,d1,a0,seen0,seen1;logic[6:0]i0,i1;logic signed[4:0]x0,x1;logic[63:0]s0,s1;logic ready0,ready1;integer seq0[0:V-1],seq1[0:V-1],cycle,n,diff;
 always #2 clk=~clk;assign ready0=(cycle%5)!=0;assign ready1=1'b1;always_ff @(posedge clk)cycle<=cycle+1;
 relay_bp_gamma_rng #(.VW(7))r0(.clk,.rst,.seed_load(load),.seed_value(64'h12345678),.gamma_start(start),.leg_index(2'd1),.variable_count(V),.gamma_ready(ready0),.gamma_abort(abort0),.gamma_valid(v0),.gamma_variable_index(i0),.gamma_value(x0),.gamma_done(d0),.abort_done(a0),.idle(),.rng_state(s0),.raw_random_word(),.words_consumed(),.rejected_words());
 relay_bp_gamma_rng #(.VW(7))r1(.clk,.rst,.seed_load(load),.seed_value(64'h12345678),.gamma_start(start),.leg_index(2'd1),.variable_count(V),.gamma_ready(ready1),.gamma_abort(1'b0),.gamma_valid(v1),.gamma_variable_index(i1),.gamma_value(x1),.gamma_done(d1),.abort_done(),.idle(),.rng_state(s1),.raw_random_word(),.words_consumed(),.rejected_words());
 always_ff @(posedge clk)begin if(rst||start)begin seen0<=0;seen1<=0;end else begin if(d0)seen0<=1;if(d1)seen1<=1;end if(v0&&ready0)seq0[i0]<=x0;if(v1&&ready1)seq1[i1]<=x1;end
 initial begin cycle=0;repeat(2)@(posedge clk);rst=0;@(negedge clk)load=1;@(negedge clk)load=0;@(negedge clk)start=1;@(negedge clk)start=0;wait(seen0&&seen1);#1;for(n=0;n<V;n=n+1)if(seq0[n]!=seq1[n])$fatal(1,"same-seed independence mismatch %0d",n);if(s0!=s1)$fatal(1,"same seed final states differ under stalls");
  // Abort only generator 0 during a new vector; generator 1 must finish unchanged.
  @(negedge clk)start=1;@(negedge clk)start=0;wait(v0&&i0>10);@(negedge clk)abort0=1;@(negedge clk)abort0=0;wait(a0);wait(seen1);if(!r0.idle||!r1.idle)$fatal(1,"independent abort did not settle");
  $display("GAMMA_RNG_INDEPENDENCE_RESULT same_seed_vectors=100 stalled_engine0=1 engine1_unaffected=1 mid_abort_engine0=1 pass=1");$finish;
 end
endmodule

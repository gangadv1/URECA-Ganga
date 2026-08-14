`timescale 1ns/1ps
module tb_relay_bp_gamma_rng_distribution;
 localparam N=200000;logic clk=0,rst=1,seed_load=0,start=0;logic valid,done;logic[17:0]idx;logic signed[4:0]value;logic[63:0]state;logic[31:0]words,rejected;integer bin_count[0:15];integer i,total;
 always #1 clk=~clk;
 relay_bp_gamma_rng #(.VW(18))dut(.clk,.rst,.seed_load,.seed_value(64'h6a09e667f3bcc909),.gamma_start(start),.leg_index(2'd1),.variable_count(N),.gamma_ready(1'b1),.gamma_abort(1'b0),.gamma_valid(valid),.gamma_variable_index(idx),.gamma_value(value),.gamma_done(done),.abort_done(),.idle(),.rng_state(state),.raw_random_word(),.words_consumed(words),.rejected_words(rejected));
 always_ff @(posedge clk)if(valid)bin_count[$signed(value)+4]<=bin_count[$signed(value)+4]+1;
 initial begin for(i=0;i<16;i=i+1)bin_count[i]=0;repeat(2)@(posedge clk);rst=0;@(negedge clk)seed_load=1;@(negedge clk)seed_load=0;@(negedge clk)start=1;@(negedge clk)start=0;wait(done);#1;total=0;for(i=0;i<16;i=i+1)begin total=total+bin_count[i];$display("GAMMA_BIN coefficient=%0d count=%0d",i-4,bin_count[i]);end $display("GAMMA_DISTRIBUTION_RESULT requested=%0d accepted=%0d words=%0d rejected=%0d final_state=%h",N,total,words,rejected,state);$finish;end
endmodule

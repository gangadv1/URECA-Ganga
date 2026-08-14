`timescale 1ns/1ps
module tb_relay_bp_gamma_rng;
 localparam VW=17;logic clk=0,rst=1,seed_load=0,start=0,ready=0,abort=0;logic[63:0]seed;logic[31:0]count;
 logic valid,done,abort_done,idle;logic[VW-1:0]idx;logic signed[4:0]value;logic[63:0]state,raw;logic[31:0]words,rejected;
 integer f,cases,c,n,i,expv,exprej,one,fail,cycles;reg[63:0]expstate,expraw,holdraw;reg signed[4:0]holdvalue;reg[VW-1:0]holdidx;
 always #5 clk=~clk;
 relay_bp_gamma_rng #(.VW(VW))dut(.clk,.rst,.seed_load,.seed_value(seed),.gamma_start(start),.leg_index(2'd1),.variable_count(count),.gamma_ready(ready),.gamma_abort(abort),.gamma_valid(valid),.gamma_variable_index(idx),.gamma_value(value),.gamma_done(done),.abort_done,.idle,.rng_state(state),.raw_random_word(raw),.words_consumed(words),.rejected_words(rejected));
 task pulse_seed(input[63:0]s);begin @(negedge clk);seed=s;seed_load=1;@(negedge clk);seed_load=0;end endtask
 task pulse_start;begin @(negedge clk);start=1;@(negedge clk);start=0;end endtask
 initial begin
  f=$fopen("fpga/verification/parallel_n2/gamma_rng_vectors.txt","r");if(!f)$fatal(1,"rng vectors missing");one=$fscanf(f,"%d",cases);repeat(2)@(posedge clk);rst=0;fail=0;
  for(c=0;c<cases;c=c+1)begin one=$fscanf(f,"%h %d %h %d",seed,n,expstate,exprej);count=n;pulse_seed(seed);pulse_start();ready=0;
   for(i=0;i<n;i=i+1)begin one=$fscanf(f,"%d %d %h",one,expv,expraw);cycles=0;while(!valid&&cycles<100)begin @(posedge clk);cycles=cycles+1;end if(!valid)$fatal(1,"rng timeout case=%0d index=%0d",c,i);#1;
    if(idx!==i||$signed(value)!==expv||raw!==expraw)$fatal(1,"rng mismatch case=%0d index=%0d got=%0d raw=%h exp=%0d raw=%h",c,i,$signed(value),raw,expv,expraw);
    holdvalue=value;holdidx=idx;holdraw=raw;repeat((i%3)+1)begin @(posedge clk);#1;if(value!==holdvalue||idx!==holdidx||raw!==holdraw)$fatal(1,"valid stall instability");end
    @(negedge clk)ready=1;@(negedge clk)ready=0;
   end
   wait(done);#1;if(state!==expstate||rejected!==exprej)$fatal(1,"final state mismatch case=%0d state=%h/%h rejected=%0d/%0d",c,state,expstate,rejected,exprej);
  end
  // Abort before first coefficient, while a valid coefficient is stalled, and at a final boundary.
  count=20;pulse_seed(64'h1234);pulse_start();@(negedge clk)abort=1;@(negedge clk)abort=0;wait(abort_done);if(!idle||done)$fatal(1,"pre-first abort failed");
  pulse_start();wait(valid);repeat(3)@(posedge clk);@(negedge clk)abort=1;@(negedge clk)abort=0;wait(abort_done);if(!idle||valid||done)$fatal(1,"stalled-valid abort failed");
  count=1;pulse_start();wait(valid);@(negedge clk)begin ready=1;abort=1;end @(negedge clk)begin ready=0;abort=0;end wait(abort_done);if(!idle||done)$fatal(1,"final-boundary abort failed");
  $display("GAMMA_RNG_EXACT_RESULT cases=%0d coefficients=233 abort_cases=3 failures=%0d",cases,fail);$finish;
 end
endmodule

// Non-cryptographic, synthesizable xorshift64 gamma-vector generator.
// Accepted 10-bit regions 0..719 reproduce the exact M=16 quantization-bin
// probabilities of Uniform[-0.24,0.66]; 720..1023 are rejected.
module relay_bp_gamma_rng #(parameter int VW=17,LW=2)(
 input logic clk,rst,seed_load,input logic[63:0]seed_value,
 input logic gamma_start,input logic[LW-1:0]leg_index,input logic[31:0]variable_count,
 input logic gamma_ready,input logic gamma_abort,
 output logic gamma_valid,output logic[VW-1:0]gamma_variable_index,
 output logic signed[4:0]gamma_value,output logic gamma_done,output logic abort_done,
 output logic idle,output logic[63:0]rng_state,output logic[63:0]raw_random_word,
 output logic[31:0]words_consumed,rejected_words);
 localparam logic[63:0]ZERO_REMAP=64'h9e3779b97f4a7c15;
 logic active;logic[63:0]next_word;logic[9:0]region;
 function automatic [63:0]xorshift64(input [63:0]x);reg[63:0]y;begin y=x;y=y^(y<<13);y=y^(y>>7);y=y^(y<<17);xorshift64=y;end endfunction
 function automatic signed[4:0]map_region(input[9:0]r);begin
  if(r<10'd17)map_region=-5'sd4;
  else if(r<10'd67)map_region=-5'sd3;else if(r<10'd117)map_region=-5'sd2;
  else if(r<10'd167)map_region=-5'sd1;else if(r<10'd217)map_region=5'sd0;
  else if(r<10'd267)map_region=5'sd1;else if(r<10'd317)map_region=5'sd2;
  else if(r<10'd367)map_region=5'sd3;else if(r<10'd417)map_region=5'sd4;
  else if(r<10'd467)map_region=5'sd5;else if(r<10'd517)map_region=5'sd6;
  else if(r<10'd567)map_region=5'sd7;else if(r<10'd617)map_region=5'sd8;
  else if(r<10'd667)map_region=5'sd9;else if(r<10'd717)map_region=5'sd10;
  else map_region=5'sd11;
 end endfunction
 always_comb begin next_word=xorshift64(rng_state);region=next_word[9:0];idle=!active&&!gamma_valid;end
 always_ff @(posedge clk)begin
  if(rst)begin rng_state<=ZERO_REMAP;active<=0;gamma_valid<=0;gamma_done<=0;abort_done<=0;gamma_variable_index<=0;gamma_value<=0;raw_random_word<=0;words_consumed<=0;rejected_words<=0;end
  else begin
   gamma_done<=0;abort_done<=0;
   if(seed_load)begin rng_state<=seed_value==0?ZERO_REMAP:seed_value;active<=0;gamma_valid<=0;gamma_variable_index<=0;words_consumed<=0;rejected_words<=0;end
   else if(gamma_abort)begin active<=0;gamma_valid<=0;abort_done<=1;end
   else if(gamma_start&&!active&&!gamma_valid)begin active<=1;gamma_variable_index<=0;end
   else if(active&&!gamma_valid)begin
    rng_state<=next_word;raw_random_word<=next_word;words_consumed<=words_consumed+1;
    if(region<10'd720)begin gamma_value<=map_region(region);gamma_valid<=1;end else rejected_words<=rejected_words+1;
   end else if(gamma_valid&&gamma_ready)begin
    if(gamma_variable_index==variable_count-1)begin gamma_valid<=0;active<=0;gamma_done<=1;end
    else begin
     gamma_variable_index<=gamma_variable_index+1;rng_state<=next_word;raw_random_word<=next_word;words_consumed<=words_consumed+1;
     if(region<10'd720)begin gamma_value<=map_region(region);gamma_valid<=1;end
     else begin gamma_valid<=0;rejected_words<=rejected_words+1;end
    end
   end
  end
 end
`ifdef RELAY_BP_SIM_ASSERT
 always_ff @(posedge clk)begin
  if(gamma_valid&&$signed(gamma_value)<-4)$fatal(1,"gamma below supported set");
  if(gamma_valid&&$signed(gamma_value)>11)$fatal(1,"gamma above supported set");
  if(gamma_done&&active)$fatal(1,"gamma done while active");
 end
`endif
endmodule

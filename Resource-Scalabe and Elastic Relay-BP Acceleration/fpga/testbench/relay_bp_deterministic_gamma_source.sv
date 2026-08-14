// Verification-only deterministic source. Production engines consume only this
// handshake; a per-engine RNG replaces this module without changing the engine.
module relay_bp_deterministic_gamma_source #(
 parameter int V=20,L=2,VW=(V<=1)?1:$clog2(V),LW=$clog2(L+1),STALL_PERIOD=0
)(input logic clk,rst,input logic start,input logic abort,input logic[LW-1:0]leg_index,input logic[31:0]variable_count,
 input logic ready,output logic valid,output logic[VW-1:0]variable_index,output logic signed[4:0]value,output logic done);
 logic signed[4:0]fixture[0:L*V-1];logic active;logic[31:0]cycle_count;
 always_ff @(posedge clk)begin
  if(rst)begin valid<=0;done<=0;active<=0;variable_index<=0;cycle_count<=0;end else begin
   done<=0;cycle_count<=cycle_count+1;
   if(abort)begin active<=0;valid<=0;done<=0;end else begin
    if(start)begin active<=1;valid<=0;variable_index<=0;end
    if(active&&!valid&&((STALL_PERIOD==0)||(cycle_count%STALL_PERIOD!=STALL_PERIOD-1)))begin valid<=1;value<=fixture[leg_index*V+variable_index];end
    if(valid&&ready)begin valid<=0;if(variable_index==variable_count-1)begin active<=0;done<=1;end else variable_index<=variable_index+1;end
   end
  end
 end
endmodule

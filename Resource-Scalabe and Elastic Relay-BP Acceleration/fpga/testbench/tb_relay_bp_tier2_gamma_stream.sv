`timescale 1ns/1ps
module tb_relay_bp_tier2_gamma_stream;
 localparam V=67752,P=4;logic clk=0,rst=1,start=0,ready=1,valid,done;logic[16:0]variable_index;logic signed[4:0]value;logic[16:0]idx;integer i,cycles,fail;logic signed[4:0]expected;
 always #5 clk=~clk;
 relay_bp_deterministic_gamma_source #(.V(V),.L(2),.STALL_PERIOD(7))src(.clk,.rst,.start,.abort(1'b0),.leg_index(2'd1),.variable_count(V),.ready,.valid,.variable_index,.value,.done);
 function automatic signed[4:0]pattern(input integer n);case(n%5)0:pattern=-4;1:pattern=0;2:pattern=2;3:pattern=4;default:pattern=11;endcase endfunction
 initial begin
  for(i=0;i<V;i=i+1)src.fixture[V+i]=pattern(i);repeat(2)@(posedge clk);rst=0;@(negedge clk)start=1;@(negedge clk)start=0;cycles=0;fail=0;idx=0;
  while(!done)begin @(negedge clk);cycles=cycles+1;ready=(cycles%11!=0)&&(cycles%13!=0);if(valid&&ready)begin expected=pattern(idx);if(variable_index!==idx||value!==expected)begin fail=fail+1;$fatal(1,"gamma mismatch index=%0d got_index=%0d expected=%0d got=%0d",idx,variable_index,expected,value);end idx=idx+1;end end
  if(idx!=V)$fatal(1,"gamma omissions expected=%0d got=%0d",V,idx);
  $display("TIER2_GAMMA_STREAM_RESULT variables=%0d accepted=%0d cycles=%0d signed_values=5 stalls=1 failures=%0d",V,idx,cycles,fail);$finish;
 end
endmodule

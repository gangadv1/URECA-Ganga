`timescale 1ns/1ps
module m4_message_phase_controller #(
  parameter integer MAX_OUTSTANDING=8
) (
  input wire clk,input wire rst,
  input wire phase, // 0 CHECK: NU->MU, 1 VARIABLE: MU->NU
  input wire read_issue,input wire read_return,input wire neighborhood_close,
  input wire write_issue,input wire phase_advance,
  output wire write_permit,output wire [15:0] outstanding,output reg neighborhood_closed
);
  reg [15:0] count;reg active_phase;
  assign outstanding=count;
  assign write_permit=neighborhood_closed && (count==0);
  always @(posedge clk) begin
    if(rst) begin count<=0;neighborhood_closed<=0;active_phase<=0;end else begin
      if(phase!=active_phase)$fatal(1,"external phase changed without safe phase_advance");
      case ({read_issue,read_return})
        2'b10: count<=count+1;
        2'b01: begin if(count==0)$fatal(1,"duplicated/unmatched response");count<=count-1;end
        default: count<=count;
      endcase
      if(read_issue && neighborhood_closed)$fatal(1,"read issued after neighborhood close");
      if(count>=MAX_OUTSTANDING && read_issue && !read_return)$fatal(1,"outstanding overflow");
      if(neighborhood_close) neighborhood_closed<=1;
      if(write_issue && !(neighborhood_closed && (count==0) && !read_issue)) $fatal(1,"write before all required reads returned");
      if(phase_advance) begin
        if(count!=0 || !neighborhood_closed)$fatal(1,"phase change with outstanding/incomplete reads");
        neighborhood_closed<=0;active_phase<=~active_phase;
      end
    end
  end
endmodule

`timescale 1ns/1ps
// Physical phase-aliased store. Semantic legality is enforced by the controller.
module m4_message_ram #(
  parameter integer WIDTH=18, DEPTH=64, ADDR_W=$clog2(DEPTH), READ_LATENCY=1
) (
  input wire clk,input wire rst,
  input wire r_en,input wire [ADDR_W-1:0] r_addr,input wire [15:0] r_tag,
  output wire r_valid,output wire [WIDTH-1:0] r_data,output wire [ADDR_W-1:0] r_rsp_addr,output wire [15:0] r_rsp_tag,
  input wire w_en,input wire [ADDR_W-1:0] w_addr,input wire [WIDTH-1:0] w_data
);
  always @(posedge clk) if(!rst && r_en && w_en && (r_addr==w_addr)) $fatal(1,"prohibited same-address message read/write");
  m4_private_bank #(.WIDTH(WIDTH),.DEPTH(DEPTH),.ADDR_W(ADDR_W),.READ_LATENCY(READ_LATENCY)) ram(.*);
endmodule

`timescale 1ns/1ps
// Immutable two-read bank. Same-address dual reads are explicitly legal.
module m4_shared_tdp_bank #(
  parameter integer WIDTH = 18,
  parameter integer DEPTH = 64,
  parameter integer ADDR_W = $clog2(DEPTH),
  parameter integer READ_LATENCY = 1,
  parameter INIT_FILE = ""
) (
  input  wire                 clk,
  input  wire                 rst,
  input  wire                 a_en,
  input  wire [ADDR_W-1:0]    a_addr,
  input  wire [15:0]          a_tag,
  output wire                 a_valid,
  output wire [WIDTH-1:0]     a_data,
  output wire [ADDR_W-1:0]    a_rsp_addr,
  output wire [15:0]          a_rsp_tag,
  input  wire                 b_en,
  input  wire [ADDR_W-1:0]    b_addr,
  input  wire [15:0]          b_tag,
  output wire                 b_valid,
  output wire [WIDTH-1:0]     b_data,
  output wire [ADDR_W-1:0]    b_rsp_addr,
  output wire [15:0]          b_rsp_tag
);
  (* ram_style = "block" *) reg [WIDTH-1:0] mem [0:DEPTH-1];
  reg [READ_LATENCY-1:0] av, bv;
  reg [WIDTH-1:0] ad [0:READ_LATENCY-1], bd [0:READ_LATENCY-1];
  reg [ADDR_W-1:0] aa [0:READ_LATENCY-1], ba [0:READ_LATENCY-1];
  reg [15:0] at [0:READ_LATENCY-1], bt [0:READ_LATENCY-1];
  integer i;
  initial begin
    if (READ_LATENCY < 1 || READ_LATENCY > 2) $fatal(1, "READ_LATENCY must be 1 or 2");
    if (INIT_FILE != "") $readmemh(INIT_FILE, mem);
  end
  always @(posedge clk) begin
    if (rst) begin av <= '0; bv <= '0; end
    else begin
      av[0] <= a_en; bv[0] <= b_en;
      if (a_en) begin ad[0] <= mem[a_addr]; aa[0] <= a_addr; at[0] <= a_tag; end
      if (b_en) begin bd[0] <= mem[b_addr]; ba[0] <= b_addr; bt[0] <= b_tag; end
      for (i=1;i<READ_LATENCY;i=i+1) begin
        av[i] <= av[i-1]; bv[i] <= bv[i-1];
        ad[i] <= ad[i-1]; bd[i] <= bd[i-1]; aa[i] <= aa[i-1]; ba[i] <= ba[i-1]; at[i] <= at[i-1]; bt[i] <= bt[i-1];
      end
    end
  end
  assign a_valid=av[READ_LATENCY-1]; assign a_data=ad[READ_LATENCY-1]; assign a_rsp_addr=aa[READ_LATENCY-1]; assign a_rsp_tag=at[READ_LATENCY-1];
  assign b_valid=bv[READ_LATENCY-1]; assign b_data=bd[READ_LATENCY-1]; assign b_rsp_addr=ba[READ_LATENCY-1]; assign b_rsp_tag=bt[READ_LATENCY-1];
endmodule

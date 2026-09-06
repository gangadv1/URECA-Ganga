`timescale 1ns/1ps
// One-read/one-write trajectory-private bank, with declared read-first behavior.
module m4_private_bank #(
  parameter integer WIDTH=18, DEPTH=64, ADDR_W=$clog2(DEPTH), READ_LATENCY=1
) (
  input wire clk, input wire rst,
  input wire r_en, input wire [ADDR_W-1:0] r_addr, input wire [15:0] r_tag,
  output wire r_valid, output wire [WIDTH-1:0] r_data, output wire [ADDR_W-1:0] r_rsp_addr, output wire [15:0] r_rsp_tag,
  input wire w_en, input wire [ADDR_W-1:0] w_addr, input wire [WIDTH-1:0] w_data
);
  (* ram_style = "block" *) reg [WIDTH-1:0] mem [0:DEPTH-1];
  reg [READ_LATENCY-1:0] rv; reg [WIDTH-1:0] rd[0:READ_LATENCY-1]; reg [ADDR_W-1:0] ra[0:READ_LATENCY-1]; reg [15:0] rt[0:READ_LATENCY-1]; integer i;
  initial if (READ_LATENCY<1 || READ_LATENCY>2) $fatal(1,"READ_LATENCY must be 1 or 2");
  always @(posedge clk) begin
    if (rst) rv <= '0;
    else begin
      rv[0] <= r_en;
      // Nonblocking assignments define read-first on same-address R/W.
      if (r_en) begin rd[0] <= mem[r_addr]; ra[0] <= r_addr; rt[0] <= r_tag; end
      if (w_en) mem[w_addr] <= w_data;
      for(i=1;i<READ_LATENCY;i=i+1) begin rv[i]<=rv[i-1];rd[i]<=rd[i-1];ra[i]<=ra[i-1];rt[i]<=rt[i-1];end
    end
  end
  assign r_valid=rv[READ_LATENCY-1];assign r_data=rd[READ_LATENCY-1];assign r_rsp_addr=ra[READ_LATENCY-1];assign r_rsp_tag=rt[READ_LATENCY-1];
endmodule

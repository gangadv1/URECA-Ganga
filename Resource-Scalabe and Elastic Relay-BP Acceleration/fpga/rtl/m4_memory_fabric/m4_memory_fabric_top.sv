`timescale 1ns/1ps
// Representative scalable four-bank fabric. Logical address: bank=addr[1:0], local=addr>>2.
module m4_memory_fabric_top #(
  parameter integer WIDTH=18, LOGICAL_DEPTH=256, LOCAL_DEPTH=(LOGICAL_DEPTH+3)/4,
  parameter integer ADDR_W=$clog2(LOGICAL_DEPTH), LOCAL_AW=$clog2(LOCAL_DEPTH), READ_LATENCY=1
) (
  input wire clk,input wire rst,
  input wire e0_s_en,input wire [ADDR_W-1:0] e0_s_addr,input wire [15:0] e0_s_tag,output wire e0_s_valid,output wire [WIDTH-1:0] e0_s_data,output wire [15:0] e0_s_rsp_tag,
  input wire e1_s_en,input wire [ADDR_W-1:0] e1_s_addr,input wire [15:0] e1_s_tag,output wire e1_s_valid,output wire [WIDTH-1:0] e1_s_data,output wire [15:0] e1_s_rsp_tag
);
  wire [3:0] av,bv; wire [WIDTH-1:0] ad[0:3],bd[0:3]; wire [15:0] at[0:3],bt[0:3]; genvar b;
  generate for(b=0;b<4;b=b+1) begin:BANK
    m4_shared_tdp_bank #(.WIDTH(WIDTH),.DEPTH(LOCAL_DEPTH),.ADDR_W(LOCAL_AW),.READ_LATENCY(READ_LATENCY)) u(
      .clk(clk),.rst(rst),.a_en(e0_s_en&&(e0_s_addr[1:0]==b)),.a_addr(e0_s_addr[ADDR_W-1:2]),.a_tag(e0_s_tag),.a_valid(av[b]),.a_data(ad[b]),.a_rsp_addr(),.a_rsp_tag(at[b]),
      .b_en(e1_s_en&&(e1_s_addr[1:0]==b)),.b_addr(e1_s_addr[ADDR_W-1:2]),.b_tag(e1_s_tag),.b_valid(bv[b]),.b_data(bd[b]),.b_rsp_addr(),.b_rsp_tag(bt[b]));
  end endgenerate
  assign e0_s_valid=|av;assign e1_s_valid=|bv;
  assign e0_s_data=av[0]?ad[0]:av[1]?ad[1]:av[2]?ad[2]:ad[3];assign e1_s_data=bv[0]?bd[0]:bv[1]?bd[1]:bv[2]?bd[2]:bd[3];
  assign e0_s_rsp_tag=av[0]?at[0]:av[1]?at[1]:av[2]?at[2]:at[3];assign e1_s_rsp_tag=bv[0]?bt[0]:bv[1]?bt[1]:bv[2]?bt[2]:bt[3];
endmodule

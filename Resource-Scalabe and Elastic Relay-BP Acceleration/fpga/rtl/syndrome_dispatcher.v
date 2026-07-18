`timescale 1ns / 1ps
// -----------------------------------------------------------------------------
// Syndrome dispatcher
// -----------------------------------------------------------------------------
// This module captures a syndrome frame and broadcasts the same data to every
// Relay engine lane. The logic is intentionally simple and synthesizable: it
// behaves like a fanout register stage that aligns the incoming frame to the
// FPGA clock domain.
// -----------------------------------------------------------------------------

module syndrome_dispatcher #(
    parameter integer NUM_ENGINES = 4,
    parameter integer SYNDROME_WIDTH = 8,
    parameter integer LLR_WIDTH = 16,
    parameter integer FRAME_ID_WIDTH = 16
) (
    input  wire                         clk,
    input  wire                         rst,
    input  wire                         in_valid,
    input  wire [FRAME_ID_WIDTH-1:0]     in_frame_id,
    input  wire [SYNDROME_WIDTH-1:0]     in_syndrome,
    input  wire [LLR_WIDTH-1:0]          in_prior_llr,
    output reg                          out_valid,
    output reg  [FRAME_ID_WIDTH-1:0]     out_frame_id,
    output reg  [NUM_ENGINES*SYNDROME_WIDTH-1:0] out_syndrome_bus,
    output reg  [NUM_ENGINES*LLR_WIDTH-1:0]      out_prior_llr_bus
);

    integer i;
    integer lane_base;

    always @(posedge clk) begin
        if (rst) begin
            out_valid <= 1'b0;
            out_frame_id <= {FRAME_ID_WIDTH{1'b0}};
            out_syndrome_bus <= {NUM_ENGINES*SYNDROME_WIDTH{1'b0}};
            out_prior_llr_bus <= {NUM_ENGINES*LLR_WIDTH{1'b0}};
        end else begin
            out_valid <= in_valid;
            if (in_valid) begin
                out_frame_id <= in_frame_id;
                for (i = 0; i < NUM_ENGINES; i = i + 1) begin
                    lane_base = i * SYNDROME_WIDTH;
                    out_syndrome_bus[lane_base +: SYNDROME_WIDTH] <= in_syndrome;
                    lane_base = i * LLR_WIDTH;
                    out_prior_llr_bus[lane_base +: LLR_WIDTH] <= in_prior_llr;
                end
            end
        end
    end

endmodule

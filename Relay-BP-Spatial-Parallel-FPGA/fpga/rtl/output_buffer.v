`timescale 1ns / 1ps
// -----------------------------------------------------------------------------
// Output buffer
// -----------------------------------------------------------------------------
// This module latches the selected candidate and presents it to downstream
// logic. It behaves like a small handoff register or FIFO endpoint.
// -----------------------------------------------------------------------------

module output_buffer #(
    parameter integer FRAME_ID_WIDTH = 16,
    parameter integer CANDIDATE_WIDTH = 8,
    parameter integer RESIDUAL_WIDTH = 8,
    parameter integer CYCLE_WIDTH = 32,
    parameter integer LATENCY_WIDTH = 32,
    parameter integer LABEL_WIDTH = 8
) (
    input  wire                         clk,
    input  wire                         rst,
    input  wire                         in_valid,
    input  wire                         in_selected,
    input  wire [FRAME_ID_WIDTH-1:0]     in_frame_id,
    input  wire [LABEL_WIDTH-1:0]        in_lane_label,
    input  wire [CANDIDATE_WIDTH-1:0]    in_candidate,
    input  wire [RESIDUAL_WIDTH-1:0]     in_residual_score,
    input  wire [CYCLE_WIDTH-1:0]        in_convergence_cycle,
    input  wire [LATENCY_WIDTH-1:0]      in_latency,
    output reg                          out_valid,
    output reg                          out_selected,
    output reg  [FRAME_ID_WIDTH-1:0]     out_frame_id,
    output reg  [LABEL_WIDTH-1:0]        out_lane_label,
    output reg  [CANDIDATE_WIDTH-1:0]    out_candidate,
    output reg  [RESIDUAL_WIDTH-1:0]     out_residual_score,
    output reg  [CYCLE_WIDTH-1:0]        out_convergence_cycle,
    output reg  [LATENCY_WIDTH-1:0]      out_latency
);

    always @(posedge clk) begin
        if (rst) begin
            out_valid <= 1'b0;
            out_selected <= 1'b0;
            out_frame_id <= {FRAME_ID_WIDTH{1'b0}};
            out_lane_label <= {LABEL_WIDTH{1'b0}};
            out_candidate <= {CANDIDATE_WIDTH{1'b0}};
            out_residual_score <= {RESIDUAL_WIDTH{1'b0}};
            out_convergence_cycle <= {CYCLE_WIDTH{1'b0}};
            out_latency <= {LATENCY_WIDTH{1'b0}};
        end else if (in_valid) begin
            out_valid <= 1'b1;
            out_selected <= in_selected;
            out_frame_id <= in_frame_id;
            out_lane_label <= in_lane_label;
            out_candidate <= in_candidate;
            out_residual_score <= in_residual_score;
            out_convergence_cycle <= in_convergence_cycle;
            out_latency <= in_latency;
        end
    end

endmodule

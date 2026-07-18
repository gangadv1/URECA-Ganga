`timescale 1ns / 1ps
// -----------------------------------------------------------------------------
// First-success selector
// -----------------------------------------------------------------------------
// This module implements a priority-based arbiter. It scans the lane results
// and chooses the first converged lane according to a fixed priority order.
// The logic is intentionally shallow and synthesizable.
// -----------------------------------------------------------------------------

module first_success_selector #(
    parameter integer NUM_ENGINES = 4,
    parameter integer CANDIDATE_WIDTH = 8,
    parameter integer RESIDUAL_WIDTH = 8,
    parameter integer FRAME_ID_WIDTH = 16,
    parameter integer CYCLE_WIDTH = 32,
    parameter integer LATENCY_WIDTH = 32
) (
    input  wire                                  clk,
    input  wire                                  rst,
    input  wire [NUM_ENGINES-1:0]                lane_done,
    input  wire [NUM_ENGINES-1:0]                lane_converged,
    input  wire [NUM_ENGINES*RESIDUAL_WIDTH-1:0] lane_residual_score_bus,
    input  wire [NUM_ENGINES*CANDIDATE_WIDTH-1:0] lane_candidate_bus,
    input  wire [NUM_ENGINES*FRAME_ID_WIDTH-1:0]  lane_frame_id_bus,
    input  wire [NUM_ENGINES*CYCLE_WIDTH-1:0]     lane_convergence_cycle_bus,
    input  wire [NUM_ENGINES*LATENCY_WIDTH-1:0]   lane_latency_bus,
    output reg                                   selector_valid,
    output reg                                   selector_selected,
    output reg  [$clog2(NUM_ENGINES)-1:0]        selector_lane,
    output reg  [FRAME_ID_WIDTH-1:0]             selector_frame_id,
    output reg  [CANDIDATE_WIDTH-1:0]            selector_candidate,
    output reg  [RESIDUAL_WIDTH-1:0]             selector_residual_score,
    output reg  [CYCLE_WIDTH-1:0]                selector_convergence_cycle,
    output reg  [LATENCY_WIDTH-1:0]              selector_latency
);

    integer lane_index;
    integer lane_base;
    reg found;

    always @(*) begin
        selector_valid = 1'b0;
        selector_selected = 1'b0;
        selector_lane = {($clog2(NUM_ENGINES)){1'b0}};
        selector_frame_id = {FRAME_ID_WIDTH{1'b0}};
        selector_candidate = {CANDIDATE_WIDTH{1'b0}};
        selector_residual_score = {RESIDUAL_WIDTH{1'b0}};
        selector_convergence_cycle = {CYCLE_WIDTH{1'b0}};
        selector_latency = {LATENCY_WIDTH{1'b0}};
        found = 1'b0;

        for (lane_index = 0; lane_index < NUM_ENGINES; lane_index = lane_index + 1) begin
            if (!found && lane_done[lane_index] && lane_converged[lane_index]) begin
                selector_valid = 1'b1;
                selector_selected = 1'b1;
                selector_lane = lane_index;
                selector_frame_id = lane_frame_id_bus[lane_index*FRAME_ID_WIDTH +: FRAME_ID_WIDTH];
                selector_candidate = lane_candidate_bus[lane_index*CANDIDATE_WIDTH +: CANDIDATE_WIDTH];
                selector_residual_score = lane_residual_score_bus[lane_index*RESIDUAL_WIDTH +: RESIDUAL_WIDTH];
                selector_convergence_cycle = lane_convergence_cycle_bus[lane_index*CYCLE_WIDTH +: CYCLE_WIDTH];
                selector_latency = lane_latency_bus[lane_index*LATENCY_WIDTH +: LATENCY_WIDTH];
                found = 1'b1;
            end
        end
    end

endmodule

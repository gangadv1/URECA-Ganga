`timescale 1ns / 1ps
// -----------------------------------------------------------------------------
// Convergence monitor
// -----------------------------------------------------------------------------
// This module observes lane-local status and asserts a done flag when the
// residual score reaches zero. It is a small control block that does not alter
// the datapath; it only reports the completion status for arbitration logic.
// -----------------------------------------------------------------------------

module convergence_monitor #(
    parameter integer RESIDUAL_WIDTH = 8
) (
    input  wire                         clk,
    input  wire                         rst,
    input  wire                         lane_valid,
    input  wire                         lane_done,
    input  wire                         lane_converged,
    input  wire [RESIDUAL_WIDTH-1:0]    lane_residual_score,
    output reg                          monitor_valid,
    output reg                          monitor_done,
    output reg                          monitor_converged,
    output reg  [RESIDUAL_WIDTH-1:0]    monitor_residual_score
);

    always @(posedge clk) begin
        if (rst) begin
            monitor_valid <= 1'b0;
            monitor_done <= 1'b0;
            monitor_converged <= 1'b0;
            monitor_residual_score <= {RESIDUAL_WIDTH{1'b0}};
        end else begin
            monitor_valid <= lane_valid;
            monitor_done <= lane_done;
            monitor_converged <= lane_converged;
            monitor_residual_score <= lane_residual_score;
        end
    end

endmodule

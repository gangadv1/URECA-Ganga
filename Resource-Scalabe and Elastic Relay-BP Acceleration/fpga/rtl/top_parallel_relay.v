`timescale 1ns / 1ps
// -----------------------------------------------------------------------------
// Top-level Parallel Relay-BP FPGA model
// -----------------------------------------------------------------------------
// This module instantiates the dispatcher, multiple Relay engines, per-lane
// convergence monitors, a first-success selector, and the output buffer.
// It is parameterizable in the number of engines and keeps control separated
// from datapath by using distinct pipeline stages for dispatch, compute,
// monitoring, selection, and output capture.
// -----------------------------------------------------------------------------

module top_parallel_relay #(
    parameter integer NUM_ENGINES = 4,
    parameter integer SYNDROME_WIDTH = 8,
    parameter integer LLR_WIDTH = 16,
    parameter integer CANDIDATE_WIDTH = 8,
    parameter integer NUM_LEGS = 2,
    parameter integer MAX_CYCLES_PER_LEG = 8,
    parameter integer GAMMA_WIDTH = 8,
    parameter integer FRAME_ID_WIDTH = 16,
    parameter integer RESIDUAL_WIDTH = 8,
    parameter integer CYCLE_WIDTH = 32,
    parameter integer LATENCY_WIDTH = 32,
    parameter integer LABEL_WIDTH = 8
) (
    input  wire                          clk,
    input  wire                          rst,
    input  wire                          in_valid,
    input  wire [FRAME_ID_WIDTH-1:0]     in_frame_id,
    input  wire [SYNDROME_WIDTH-1:0]     in_syndrome,
    input  wire [LLR_WIDTH-1:0]          in_prior_llr,
    input  wire [NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH-1:0] gamma_schedule_flat_0,
    input  wire [NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH-1:0] gamma_schedule_flat_1,
    input  wire [NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH-1:0] gamma_schedule_flat_2,
    input  wire [NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH-1:0] gamma_schedule_flat_3,
    input  wire [NUM_ENGINES*8-1:0]      carry_factor_flat,
    output wire                          out_valid,
    output wire                          out_selected,
    output wire [FRAME_ID_WIDTH-1:0]     out_frame_id,
    output wire [LABEL_WIDTH-1:0]        out_lane_label,
    output wire [CANDIDATE_WIDTH-1:0]    out_candidate,
    output wire [RESIDUAL_WIDTH-1:0]     out_residual_score,
    output wire [CYCLE_WIDTH-1:0]        out_convergence_cycle,
    output wire [LATENCY_WIDTH-1:0]      out_latency
);

    wire dispatcher_valid;
    wire [FRAME_ID_WIDTH-1:0] dispatcher_frame_id;
    wire [NUM_ENGINES*SYNDROME_WIDTH-1:0] dispatcher_syndrome_bus;
    wire [NUM_ENGINES*LLR_WIDTH-1:0] dispatcher_prior_llr_bus;

    syndrome_dispatcher #(
        .NUM_ENGINES(NUM_ENGINES),
        .SYNDROME_WIDTH(SYNDROME_WIDTH),
        .LLR_WIDTH(LLR_WIDTH),
        .FRAME_ID_WIDTH(FRAME_ID_WIDTH)
    ) u_dispatcher (
        .clk(clk),
        .rst(rst),
        .in_valid(in_valid),
        .in_frame_id(in_frame_id),
        .in_syndrome(in_syndrome),
        .in_prior_llr(in_prior_llr),
        .out_valid(dispatcher_valid),
        .out_frame_id(dispatcher_frame_id),
        .out_syndrome_bus(dispatcher_syndrome_bus),
        .out_prior_llr_bus(dispatcher_prior_llr_bus)
    );

    wire [NUM_ENGINES-1:0] lane_done;
    wire [NUM_ENGINES-1:0] lane_converged;
    wire [NUM_ENGINES*RESIDUAL_WIDTH-1:0] lane_residual_score_bus;
    wire [NUM_ENGINES*CANDIDATE_WIDTH-1:0] lane_candidate_bus;
    wire [NUM_ENGINES*FRAME_ID_WIDTH-1:0] lane_frame_id_bus;
    wire [NUM_ENGINES*CYCLE_WIDTH-1:0] lane_convergence_cycle_bus;
    wire [NUM_ENGINES*LATENCY_WIDTH-1:0] lane_latency_bus;
    wire [NUM_ENGINES*LABEL_WIDTH-1:0] lane_label_bus;

    genvar lane;
    generate
        for (lane = 0; lane < NUM_ENGINES; lane = lane + 1) begin : GEN_LANES
            localparam integer LANE_ID_LOCAL = lane;
            wire [SYNDROME_WIDTH-1:0] lane_syndrome;
            wire [LLR_WIDTH-1:0] lane_prior_llr;
            wire [7:0] lane_current_leg;
            wire [7:0] lane_legs_used;
            wire [31:0] lane_total_iterations;
            wire [31:0] lane_convergence_cycle;
            wire [31:0] lane_latency;
            wire [RESIDUAL_WIDTH-1:0] lane_residual_score;
            wire [CANDIDATE_WIDTH-1:0] lane_candidate;
            wire [15:0] lane_selected_gamma;
            wire lane_busy;
            wire lane_done_int;
            wire lane_converged_int;

            assign lane_syndrome = dispatcher_syndrome_bus[lane*SYNDROME_WIDTH +: SYNDROME_WIDTH];
            assign lane_prior_llr = dispatcher_prior_llr_bus[lane*LLR_WIDTH +: LLR_WIDTH];

            relay_engine #(
                .LANE_ID(lane),
                .SYNDROME_WIDTH(SYNDROME_WIDTH),
                .LLR_WIDTH(LLR_WIDTH),
                .CANDIDATE_WIDTH(CANDIDATE_WIDTH),
                .NUM_LEGS(NUM_LEGS),
                .MAX_CYCLES_PER_LEG(MAX_CYCLES_PER_LEG),
                .GAMMA_WIDTH(GAMMA_WIDTH)
            ) u_engine (
                .clk(clk),
                .rst(rst),
                .start(dispatcher_valid),
                .frame_id(dispatcher_frame_id),
                .syndrome_in(lane_syndrome),
                .prior_llr_in(lane_prior_llr),
                .gamma_schedule_flat(
                    lane == 0 ? gamma_schedule_flat_0 :
                    lane == 1 ? gamma_schedule_flat_1 :
                    lane == 2 ? gamma_schedule_flat_2 :
                                 gamma_schedule_flat_3
                ),
                .carry_factor_flat(carry_factor_flat),
                .busy(lane_busy),
                .done(lane_done_int),
                .converged(lane_converged_int),
                .current_leg(lane_current_leg),
                .relay_legs_used(lane_legs_used),
                .total_iterations(lane_total_iterations),
                .convergence_cycle(lane_convergence_cycle),
                .total_latency_cycles(lane_latency),
                .residual_syndrome(),
                .residual_score(lane_residual_score),
                .candidate_vector(lane_candidate),
                .selected_gamma(lane_selected_gamma)
            );

            assign lane_done[lane] = lane_done_int;
            assign lane_converged[lane] = lane_converged_int;
            assign lane_residual_score_bus[lane*RESIDUAL_WIDTH +: RESIDUAL_WIDTH] = lane_residual_score;
            assign lane_candidate_bus[lane*CANDIDATE_WIDTH +: CANDIDATE_WIDTH] = lane_candidate;
            assign lane_frame_id_bus[lane*FRAME_ID_WIDTH +: FRAME_ID_WIDTH] = dispatcher_frame_id;
            assign lane_convergence_cycle_bus[lane*CYCLE_WIDTH +: CYCLE_WIDTH] = lane_convergence_cycle;
            assign lane_latency_bus[lane*LATENCY_WIDTH +: LATENCY_WIDTH] = lane_latency;
            assign lane_label_bus[lane*LABEL_WIDTH +: LABEL_WIDTH] = LANE_ID_LOCAL[7:0];
        end
    endgenerate

    wire selector_valid;
    wire selector_selected;
    wire [$clog2(NUM_ENGINES)-1:0] selector_lane;
    wire [FRAME_ID_WIDTH-1:0] selector_frame_id;
    wire [CANDIDATE_WIDTH-1:0] selector_candidate;
    wire [RESIDUAL_WIDTH-1:0] selector_residual_score;
    wire [CYCLE_WIDTH-1:0] selector_convergence_cycle;
    wire [LATENCY_WIDTH-1:0] selector_latency;

    first_success_selector #(
        .NUM_ENGINES(NUM_ENGINES),
        .CANDIDATE_WIDTH(CANDIDATE_WIDTH),
        .RESIDUAL_WIDTH(RESIDUAL_WIDTH),
        .FRAME_ID_WIDTH(FRAME_ID_WIDTH),
        .CYCLE_WIDTH(CYCLE_WIDTH),
        .LATENCY_WIDTH(LATENCY_WIDTH)
    ) u_selector (
        .clk(clk),
        .rst(rst),
        .lane_done(lane_done),
        .lane_converged(lane_converged),
        .lane_residual_score_bus(lane_residual_score_bus),
        .lane_candidate_bus(lane_candidate_bus),
        .lane_frame_id_bus(lane_frame_id_bus),
        .lane_convergence_cycle_bus(lane_convergence_cycle_bus),
        .lane_latency_bus(lane_latency_bus),
        .selector_valid(selector_valid),
        .selector_selected(selector_selected),
        .selector_lane(selector_lane),
        .selector_frame_id(selector_frame_id),
        .selector_candidate(selector_candidate),
        .selector_residual_score(selector_residual_score),
        .selector_convergence_cycle(selector_convergence_cycle),
        .selector_latency(selector_latency)
    );

    output_buffer #(
        .FRAME_ID_WIDTH(FRAME_ID_WIDTH),
        .CANDIDATE_WIDTH(CANDIDATE_WIDTH),
        .RESIDUAL_WIDTH(RESIDUAL_WIDTH),
        .CYCLE_WIDTH(CYCLE_WIDTH),
        .LATENCY_WIDTH(LATENCY_WIDTH),
        .LABEL_WIDTH(LABEL_WIDTH)
    ) u_output_buffer (
        .clk(clk),
        .rst(rst),
        .in_valid(selector_valid),
        .in_selected(selector_selected),
        .in_frame_id(selector_frame_id),
        .in_lane_label(selector_lane),
        .in_candidate(selector_candidate),
        .in_residual_score(selector_residual_score),
        .in_convergence_cycle(selector_convergence_cycle),
        .in_latency(selector_latency),
        .out_valid(out_valid),
        .out_selected(out_selected),
        .out_frame_id(out_frame_id),
        .out_lane_label(out_lane_label),
        .out_candidate(out_candidate),
        .out_residual_score(out_residual_score),
        .out_convergence_cycle(out_convergence_cycle),
        .out_latency(out_latency)
    );

endmodule

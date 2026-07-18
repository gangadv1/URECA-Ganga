`timescale 1ns / 1ps
// -----------------------------------------------------------------------------
// Relay engine
// -----------------------------------------------------------------------------
// This module models one hardware Relay lane as a small sequential engine.
// It uses lane-local registers, a simple residual counter, sequential Relay
// legs, and a synthetic candidate vector to mimic hardware behavior rather than
// mathematical decoding. The state machine is synthesizable and intended for
// Vivado / Vivado HLS integration at the RTL boundary.
// -----------------------------------------------------------------------------

module relay_engine #(
    parameter integer LANE_ID = 0,
    parameter integer SYNDROME_WIDTH = 8,
    parameter integer LLR_WIDTH = 16,
    parameter integer CANDIDATE_WIDTH = 8,
    parameter integer NUM_LEGS = 2,
    parameter integer MAX_CYCLES_PER_LEG = 8,
    parameter integer GAMMA_WIDTH = 8,
    parameter integer CYCLE_TIME_WIDTH = 32
) (
    input  wire                          clk,
    input  wire                          rst,
    input  wire                          start,
    input  wire [15:0]                   frame_id,
    input  wire [SYNDROME_WIDTH-1:0]     syndrome_in,
    input  wire [LLR_WIDTH-1:0]          prior_llr_in,
    input  wire [NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH-1:0] gamma_schedule_flat,
    input  wire [NUM_LEGS*8-1:0]         carry_factor_flat,
    output reg                           busy,
    output reg                           done,
    output reg                           converged,
    output reg  [7:0]                    current_leg,
    output reg  [7:0]                    relay_legs_used,
    output reg  [31:0]                   total_iterations,
    output reg  [31:0]                   convergence_cycle,
    output reg  [31:0]                   total_latency_cycles,
    output reg  [SYNDROME_WIDTH-1:0]     residual_syndrome,
    output reg  [7:0]                    residual_score,
    output reg  [CANDIDATE_WIDTH-1:0]    candidate_vector,
    output reg  [15:0]                   selected_gamma
);

    localparam [2:0] S_IDLE    = 3'd0;
    localparam [2:0] S_LOAD    = 3'd1;
    localparam [2:0] S_UPDATE  = 3'd2;
    localparam [2:0] S_CHECK   = 3'd3;
    localparam [2:0] S_CARRY   = 3'd4;
    localparam [2:0] S_DONE    = 3'd5;

    reg [2:0] state;
    reg [7:0] leg_cycle;
    reg [7:0] leg_index;
    reg [15:0] lane_memory [0:CANDIDATE_WIDTH-1];
    reg [15:0] prior_shadow [0:CANDIDATE_WIDTH-1];
    reg [15:0] belief_reg [0:CANDIDATE_WIDTH-1];
    reg [15:0] next_memory [0:CANDIDATE_WIDTH-1];
    reg [SYNDROME_WIDTH-1:0] syndrome_shadow;
    reg [CANDIDATE_WIDTH-1:0] candidate_shadow;
    reg [7:0] carry_factor;
    integer j;
    integer gamma_base;
    integer carry_value;
    integer progress_step;
    integer initial_residual;

    // -------------------------------------------------------------------------
    // Helper functions are intentionally simple and synthesis friendly.
    // -------------------------------------------------------------------------
    function [15:0] abs16;
        input signed [15:0] value;
        begin
            abs16 = value[15] ? (~value + 16'd1) : value;
        end
    endfunction

    function [15:0] gamma_at;
        input [2:0] leg_sel;
        input [7:0] cycle_sel;
        integer index;
        begin
            index = (leg_sel * MAX_CYCLES_PER_LEG + cycle_sel) * GAMMA_WIDTH;
            gamma_at = gamma_schedule_flat[index +: GAMMA_WIDTH];
        end
    endfunction

    // -------------------------------------------------------------------------
    // Lane-local control and state machine.
    // -------------------------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            state <= S_IDLE;
            busy <= 1'b0;
            done <= 1'b0;
            converged <= 1'b0;
            current_leg <= 8'd0;
            relay_legs_used <= 8'd0;
            total_iterations <= 32'd0;
            convergence_cycle <= 32'd0;
            total_latency_cycles <= 32'd0;
            residual_score <= 8'd0;
            residual_syndrome <= {SYNDROME_WIDTH{1'b0}};
            candidate_vector <= {CANDIDATE_WIDTH{1'b0}};
            selected_gamma <= 16'd0;
            syndrome_shadow <= {SYNDROME_WIDTH{1'b0}};
            candidate_shadow <= {CANDIDATE_WIDTH{1'b0}};
            leg_cycle <= 8'd0;
            leg_index <= 8'd0;
            carry_factor <= 8'd0;
            for (j = 0; j < CANDIDATE_WIDTH; j = j + 1) begin
                lane_memory[j] <= 16'd0;
                prior_shadow[j] <= 16'd0;
                belief_reg[j] <= 16'd0;
                next_memory[j] <= 16'd0;
            end
        end else begin
            case (state)
                S_IDLE: begin
                    done <= 1'b0;
                    converged <= 1'b0;
                    busy <= 1'b0;
                    if (start) begin
                        state <= S_LOAD;
                    end
                end

                S_LOAD: begin
                    busy <= 1'b1;
                    syndrome_shadow <= syndrome_in;
                    candidate_shadow <= {CANDIDATE_WIDTH{1'b0}};
                    total_iterations <= 32'd0;
                    convergence_cycle <= 32'd0;
                    total_latency_cycles <= 32'd0;
                    relay_legs_used <= 8'd0;
                    leg_index <= 8'd0;
                    leg_cycle <= 8'd0;
                    current_leg <= 8'd0;
                    for (j = 0; j < CANDIDATE_WIDTH; j = j + 1) begin
                        lane_memory[j] <= 16'd0;
                        prior_shadow[j] <= prior_llr_in;
                        belief_reg[j] <= prior_llr_in;
                        next_memory[j] <= 16'd0;
                    end
                    state <= S_UPDATE;
                end

                S_UPDATE: begin
                    selected_gamma <= gamma_at(leg_index[2:0], leg_cycle);
                    carry_factor <= carry_factor_flat[(leg_index * 8) +: 8];

                    // Synthetic datapath activity: update the per-lane beliefs,
                    // candidate vector, and lane memory to mimic a hardware lane.
                    for (j = 0; j < CANDIDATE_WIDTH; j = j + 1) begin
                        gamma_base = gamma_at(leg_index[2:0], leg_cycle);
                        progress_step = 1 + ((gamma_base >> 5) & 8'h07) + (LANE_ID % 8);
                        belief_reg[j] <= prior_shadow[j] + lane_memory[j] + progress_step;
                        candidate_shadow[j] <= belief_reg[j][0] ^ syndrome_shadow[j % SYNDROME_WIDTH];
                        next_memory[j] <= lane_memory[j] + (belief_reg[j] >> 2) + carry_factor;
                    end
                    state <= S_CHECK;
                end

                S_CHECK: begin
                    residual_score <= 8'd0;
                    residual_syndrome <= {SYNDROME_WIDTH{1'b0}};
                    initial_residual = 0;

                    for (j = 0; j < SYNDROME_WIDTH; j = j + 1) begin
                        residual_syndrome[j] <= syndrome_shadow[j] ^ candidate_shadow[j % CANDIDATE_WIDTH];
                        if ((syndrome_shadow[j] ^ candidate_shadow[j % CANDIDATE_WIDTH]) == 1'b1) begin
                            initial_residual = initial_residual + 1;
                        end
                    end

                    residual_score <= initial_residual[7:0];
                    candidate_vector <= candidate_shadow;
                    total_iterations <= total_iterations + 1;
                    total_latency_cycles <= total_latency_cycles + 1;

                    if (initial_residual == 0) begin
                        converged <= 1'b1;
                        relay_legs_used <= leg_index + 8'd1;
                        convergence_cycle <= total_latency_cycles + 1;
                        state <= S_DONE;
                    end else begin
                        state <= S_CARRY;
                    end
                end

                S_CARRY: begin
                    for (j = 0; j < CANDIDATE_WIDTH; j = j + 1) begin
                        lane_memory[j] <= next_memory[j];
                        prior_shadow[j] <= belief_reg[j];
                    end

                    leg_cycle <= leg_cycle + 8'd1;
                    if (leg_cycle + 8'd1 >= MAX_CYCLES_PER_LEG) begin
                        leg_index <= leg_index + 8'd1;
                        relay_legs_used <= leg_index + 8'd1;
                        leg_cycle <= 8'd0;
                        current_leg <= leg_index + 8'd1;
                        if ((leg_index + 8'd1) >= NUM_LEGS) begin
                            state <= S_DONE;
                        end else begin
                            state <= S_UPDATE;
                        end
                    end else begin
                        state <= S_UPDATE;
                    end
                end

                S_DONE: begin
                    busy <= 1'b0;
                    done <= 1'b1;
                    if (converged == 1'b0 && relay_legs_used == 8'd0) begin
                        relay_legs_used <= leg_index + 8'd1;
                    end
                    if (converged == 1'b0) begin
                        candidate_vector <= candidate_shadow;
                    end
                    state <= S_IDLE;
                end

                default: begin
                    state <= S_IDLE;
                end
            endcase
        end
    end

endmodule

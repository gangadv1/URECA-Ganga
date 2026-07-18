`timescale 1ns / 1ps

module tb_parallel_relay;

    localparam integer NUM_ENGINES = 4;
    localparam integer SYNDROME_WIDTH = 8;
    localparam integer LLR_WIDTH = 16;
    localparam integer CANDIDATE_WIDTH = 8;
    localparam integer NUM_LEGS = 2;
    localparam integer MAX_CYCLES_PER_LEG = 8;
    localparam integer GAMMA_WIDTH = 8;
    localparam integer FRAME_ID_WIDTH = 16;
    localparam integer RESIDUAL_WIDTH = 8;
    localparam integer CYCLE_WIDTH = 32;
    localparam integer LATENCY_WIDTH = 32;
    localparam integer LABEL_WIDTH = 8;
    localparam integer NUM_TEST_VECTORS = 6;
    localparam integer MAX_WAIT_CYCLES = 300;

    reg clk;
    reg rst;
    reg in_valid;
    reg [FRAME_ID_WIDTH-1:0] in_frame_id;
    reg [SYNDROME_WIDTH-1:0] in_syndrome;
    reg [LLR_WIDTH-1:0] in_prior_llr;
    reg [NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH-1:0] gamma_schedule_flat_0;
    reg [NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH-1:0] gamma_schedule_flat_1;
    reg [NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH-1:0] gamma_schedule_flat_2;
    reg [NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH-1:0] gamma_schedule_flat_3;
    reg [NUM_ENGINES*8-1:0] carry_factor_flat;

    wire out_valid;
    wire out_selected;
    wire [FRAME_ID_WIDTH-1:0] out_frame_id;
    wire [LABEL_WIDTH-1:0] out_lane_label;
    wire [CANDIDATE_WIDTH-1:0] out_candidate;
    wire [RESIDUAL_WIDTH-1:0] out_residual_score;
    wire [CYCLE_WIDTH-1:0] out_convergence_cycle;
    wire [LATENCY_WIDTH-1:0] out_latency;

    integer cycle_count;
    integer start_cycle;
    integer latency_cycles;
    integer frame_index;
    integer successful_frames;
    integer total_latency;
    integer min_latency;
    integer max_latency;
    integer total_selected;
    integer total_not_selected;
    integer total_timeouts;
    integer observed_winner_count [0:NUM_ENGINES-1];
    integer wait_cycles;
    integer frame_done;

    reg [SYNDROME_WIDTH-1:0] syndrome_vectors [0:NUM_TEST_VECTORS-1];
    reg [FRAME_ID_WIDTH-1:0] frame_ids [0:NUM_TEST_VECTORS-1];
    reg [LLR_WIDTH-1:0] prior_llrs [0:NUM_TEST_VECTORS-1];

    top_parallel_relay #(
        .NUM_ENGINES(NUM_ENGINES),
        .SYNDROME_WIDTH(SYNDROME_WIDTH),
        .LLR_WIDTH(LLR_WIDTH),
        .CANDIDATE_WIDTH(CANDIDATE_WIDTH),
        .NUM_LEGS(NUM_LEGS),
        .MAX_CYCLES_PER_LEG(MAX_CYCLES_PER_LEG),
        .GAMMA_WIDTH(GAMMA_WIDTH),
        .FRAME_ID_WIDTH(FRAME_ID_WIDTH),
        .RESIDUAL_WIDTH(RESIDUAL_WIDTH),
        .CYCLE_WIDTH(CYCLE_WIDTH),
        .LATENCY_WIDTH(LATENCY_WIDTH),
        .LABEL_WIDTH(LABEL_WIDTH)
    ) dut (
        .clk(clk),
        .rst(rst),
        .in_valid(in_valid),
        .in_frame_id(in_frame_id),
        .in_syndrome(in_syndrome),
        .in_prior_llr(in_prior_llr),
        .gamma_schedule_flat_0(gamma_schedule_flat_0),
        .gamma_schedule_flat_1(gamma_schedule_flat_1),
        .gamma_schedule_flat_2(gamma_schedule_flat_2),
        .gamma_schedule_flat_3(gamma_schedule_flat_3),
        .carry_factor_flat(carry_factor_flat),
        .out_valid(out_valid),
        .out_selected(out_selected),
        .out_frame_id(out_frame_id),
        .out_lane_label(out_lane_label),
        .out_candidate(out_candidate),
        .out_residual_score(out_residual_score),
        .out_convergence_cycle(out_convergence_cycle),
        .out_latency(out_latency)
    );

    always #5 clk = ~clk;

    integer i;
    integer leg;
    integer cycle_slot;
    integer gamma_index;
    reg [7:0] gamma_value;

    initial begin
        clk = 1'b0;
        rst = 1'b1;
        in_valid = 1'b0;
        in_frame_id = {FRAME_ID_WIDTH{1'b0}};
        in_syndrome = {SYNDROME_WIDTH{1'b0}};
        in_prior_llr = {LLR_WIDTH{1'b0}};
        gamma_schedule_flat_0 = {NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH{1'b0}};
        gamma_schedule_flat_1 = {NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH{1'b0}};
        gamma_schedule_flat_2 = {NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH{1'b0}};
        gamma_schedule_flat_3 = {NUM_LEGS*MAX_CYCLES_PER_LEG*GAMMA_WIDTH{1'b0}};
        carry_factor_flat = {NUM_ENGINES*8{1'b0}};
        cycle_count = 0;
        successful_frames = 0;
        total_latency = 0;
        min_latency = 32'h7fffffff;
        max_latency = 0;
        total_selected = 0;
        total_not_selected = 0;
        total_timeouts = 0;
        wait_cycles = 0;
        frame_done = 0;

        for (i = 0; i < NUM_ENGINES; i = i + 1) begin
            observed_winner_count[i] = 0;
        end

        syndrome_vectors[0] = 8'h01;
        syndrome_vectors[1] = 8'h03;
        syndrome_vectors[2] = 8'h07;
        syndrome_vectors[3] = 8'h0F;
        syndrome_vectors[4] = 8'h15;
        syndrome_vectors[5] = 8'h2A;

        frame_ids[0] = 16'h1001;
        frame_ids[1] = 16'h1002;
        frame_ids[2] = 16'h1003;
        frame_ids[3] = 16'h1004;
        frame_ids[4] = 16'h1005;
        frame_ids[5] = 16'h1006;

        prior_llrs[0] = 16'sd12;
        prior_llrs[1] = -16'sd7;
        prior_llrs[2] = 16'sd9;
        prior_llrs[3] = -16'sd11;
        prior_llrs[4] = 16'sd6;
        prior_llrs[5] = -16'sd5;

        for (leg = 0; leg < NUM_LEGS; leg = leg + 1) begin
            for (cycle_slot = 0; cycle_slot < MAX_CYCLES_PER_LEG; cycle_slot = cycle_slot + 1) begin
                gamma_index = (leg * MAX_CYCLES_PER_LEG + cycle_slot) * GAMMA_WIDTH;
                gamma_value = 8'd8 + leg * 8 + cycle_slot;
                gamma_schedule_flat_0[gamma_index +: GAMMA_WIDTH] = gamma_value;
                gamma_schedule_flat_1[gamma_index +: GAMMA_WIDTH] = gamma_value + 8'd1;
                gamma_schedule_flat_2[gamma_index +: GAMMA_WIDTH] = gamma_value + 8'd2;
                gamma_schedule_flat_3[gamma_index +: GAMMA_WIDTH] = gamma_value + 8'd3;
            end
        end

        carry_factor_flat[0 +: 8] = 8'd1;
        carry_factor_flat[8 +: 8] = 8'd2;
        carry_factor_flat[16 +: 8] = 8'd3;
        carry_factor_flat[24 +: 8] = 8'd4;

        $dumpfile("tb_parallel_relay.vcd");
        $dumpvars(0, tb_parallel_relay);

        repeat (5) @(posedge clk);
        rst = 1'b0;
        @(posedge clk);

        for (frame_index = 0; frame_index < NUM_TEST_VECTORS; frame_index = frame_index + 1) begin
            wait_cycles = 0;
            frame_done = 0;
            in_frame_id = frame_ids[frame_index];
            in_syndrome = syndrome_vectors[frame_index];
            in_prior_llr = prior_llrs[frame_index];
            in_valid = 1'b1;
            start_cycle = cycle_count;
            @(posedge clk);
            in_valid = 1'b0;

            begin : FRAME_WAIT
                while (wait_cycles < MAX_WAIT_CYCLES) begin
                    @(posedge clk);
                    wait_cycles = wait_cycles + 1;
                    if (out_valid && out_selected && out_frame_id == frame_ids[frame_index]) begin
                        latency_cycles = cycle_count - start_cycle;
                        successful_frames = successful_frames + 1;
                        total_latency = total_latency + latency_cycles;
                        total_selected = total_selected + 1;
                        frame_done = 1;
                        if (latency_cycles < min_latency) begin
                            min_latency = latency_cycles;
                        end
                        if (latency_cycles > max_latency) begin
                            max_latency = latency_cycles;
                        end
                        if (out_lane_label < NUM_ENGINES) begin
                            observed_winner_count[out_lane_label] = observed_winner_count[out_lane_label] + 1;
                        end
                        $display("FRAME %0d SELECTED lane=%0d frame_id=%0h candidate=%0h residual=%0d latency=%0d cycles output_latency=%0d convergence_cycle=%0d",
                                 frame_index,
                                 out_lane_label,
                                 out_frame_id,
                                 out_candidate,
                                 out_residual_score,
                                 latency_cycles,
                                 out_latency,
                                 out_convergence_cycle);
                        disable FRAME_WAIT;
                    end
                end
            end

            if (!frame_done) begin
                total_timeouts = total_timeouts + 1;
                total_not_selected = total_not_selected + 1;
                $display("FRAME %0d TIMEOUT frame_id=%0h syndrome=%0h", frame_index, frame_ids[frame_index], syndrome_vectors[frame_index]);
            end

            repeat (3) @(posedge clk);
        end

        if (successful_frames > 0) begin
            $display("--- Simulation Statistics ---");
            $display("Total frames            : %0d", NUM_TEST_VECTORS);
            $display("Successful decodes      : %0d", successful_frames);
            $display("Timeouts                : %0d", total_timeouts);
            $display("Average latency (cycles): %0f", real'(total_latency) / real'(successful_frames));
            $display("Minimum latency         : %0d", min_latency);
            $display("Maximum latency         : %0d", max_latency);
            $display("Selected outputs        : %0d", total_selected);
            $display("Not selected outputs    : %0d", total_not_selected);
            for (i = 0; i < NUM_ENGINES; i = i + 1) begin
                $display("Winning lane %0d count  : %0d", i, observed_winner_count[i]);
            end
        end else begin
            $display("--- Simulation Statistics ---");
            $display("No successful decodes were observed.");
        end

        $finish;
    end

    initial begin : cycle_counter_block
        forever begin
            @(posedge clk);
            cycle_count = cycle_count + 1;
        end
    end

endmodule

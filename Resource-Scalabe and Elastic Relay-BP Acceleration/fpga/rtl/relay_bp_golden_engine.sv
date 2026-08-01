// New folded/tiled Relay-BP golden RTL engine.
// The controller and datapath are sequenced explicitly and mirror the Python
// fixed-point reference order: variable phase -> check phase -> decision ->
// relay-memory update -> next leg or finish.
module relay_bp_golden_engine #(
  parameter int CHECKS = 72,
  parameter int VARIABLES = 144,
  parameter int EDGES = 1,
  parameter int B = 4,
  parameter int M_SHIFT = 3,
  parameter int CLIP = (1 << (B - 1)) - 1,
  parameter int MAX_ITERATIONS_PER_LEG = 3,
  parameter int MAX_LEGS = 2,
  parameter int GAMMA_SHIFT = 4,
  parameter int LEG0_GAMMA0 = 4,
  parameter int LEG0_GAMMA1 = 8,
  parameter int LEG0_GAMMA2 = 8,
  parameter int LEG1_GAMMA0 = 2,
  parameter int LEG1_GAMMA1 = 3,
  parameter int LEG1_GAMMA2 = 5,
  parameter int LEG0_BETA_INT = 2,
  parameter int LEG1_BETA_INT = 4
) (
  input  logic clk,
  input  logic rst,
  input  logic start,
  input  logic [CHECKS-1:0] syndrome,
  input  logic signed [B-1:0] prior [VARIABLES],
  input  logic [M_SHIFT:0] gamma_int,
  input  logic [M_SHIFT:0] beta_int,
  input  logic [EDGES*((CHECKS <= 1) ? 1 : $clog2(CHECKS))-1:0] check_of_edge,
  input  logic [EDGES*((VARIABLES <= 1) ? 1 : $clog2(VARIABLES))-1:0] variable_of_edge,
  output logic busy,
  output logic done,
  output logic converged,
  output logic [VARIABLES-1:0] decoded_error,
  output logic [CHECKS-1:0] residual_syndrome,
  output logic [$clog2(MAX_ITERATIONS_PER_LEG*MAX_LEGS+1)-1:0] iterations,
  output logic [$clog2(MAX_LEGS+1)-1:0] legs,
  output logic trace_valid,
  output logic trace_is_check,
  output logic [31:0] trace_node,
  output logic [31:0] active_cycles
);
  import fixedpoint_relay_pkg::*;

  typedef enum logic [2:0] {IDLE, VAR_PHASE, CHECK_PHASE, DECIDE_PHASE, RELAY_PHASE, FINISH} state_t;

  state_t state;
  integer node;
  integer edge_index;
  integer other;
  integer other_count;
  localparam int CHECK_W = (CHECKS <= 1) ? 1 : $clog2(CHECKS);
  localparam int VARIABLE_W = (VARIABLES <= 1) ? 1 : $clog2(VARIABLES);

  longint signed sum_value;
  longint signed relay_value;
  longint signed min_value;
  longint signed abs_value;
  longint signed sign_value;
  longint signed updated_memory;
  longint signed gamma_value;
  longint signed beta_value;
  logic signed [B-1:0] prior_state [0:VARIABLES-1];
  logic signed [B-1:0] belief [0:VARIABLES-1];
  logic signed [B-1:0] relay_memory [0:VARIABLES-1];
  logic signed [B-1:0] v_to_c [0:EDGES-1];
  logic signed [B-1:0] c_to_v [0:EDGES-1];
  logic [CHECKS-1:0] residual;
  logic [CHECKS-1:0] residual_next;
  logic [$clog2(MAX_ITERATIONS_PER_LEG+1)-1:0] leg_iterations;

  function automatic int edge_count_for_check(input int check);
    int count;
    begin
      count = 0;
      for (int i = 0; i < EDGES; i++) begin
        if (check_of_edge[i*CHECK_W +: CHECK_W] == check) count++;
      end
      edge_count_for_check = count;
    end
  endfunction

  function automatic int gamma_for_iteration(input int leg_number, input int iteration_number);
    begin
      case (leg_number)
        1: begin
          case (iteration_number)
            0: gamma_for_iteration = LEG0_GAMMA0;
            1: gamma_for_iteration = LEG0_GAMMA1;
            default: gamma_for_iteration = LEG0_GAMMA2;
          endcase
        end
        default: begin
          case (iteration_number)
            0: gamma_for_iteration = LEG1_GAMMA0;
            1: gamma_for_iteration = LEG1_GAMMA1;
            default: gamma_for_iteration = LEG1_GAMMA2;
          endcase
        end
      endcase
    end
  endfunction

  function automatic int beta_for_leg(input int leg_number);
    begin
      case (leg_number)
        1: beta_for_leg = LEG0_BETA_INT;
        default: beta_for_leg = LEG1_BETA_INT;
      endcase
    end
  endfunction

  always_comb begin
    residual_next = syndrome;
    for (edge_index = 0; edge_index < EDGES; edge_index++) begin
      residual_next[check_of_edge[edge_index*CHECK_W +: CHECK_W]] = residual_next[check_of_edge[edge_index*CHECK_W +: CHECK_W]] ^ decoded_error[variable_of_edge[edge_index*VARIABLE_W +: VARIABLE_W]];
    end
  end

  always_ff @(posedge clk) begin
    if (rst) begin
      state <= IDLE;
      busy <= 0;
      done <= 0;
      converged <= 0;
      iterations <= 0;
      legs <= 0;
      decoded_error <= '0;
      residual <= '0;
      residual_syndrome <= '0;
      active_cycles <= 0;
      leg_iterations <= 0;
      for (edge_index = 0; edge_index < EDGES; edge_index++) begin
        v_to_c[edge_index] <= '0;
        c_to_v[edge_index] <= '0;
      end
      for (node = 0; node < VARIABLES; node++) begin
        prior_state[node] <= '0;
        belief[node] <= '0;
        relay_memory[node] <= '0;
      end
    end else begin
      done <= 0;
      trace_valid <= 0;
      case (state)
        IDLE: begin
          if (start) begin
            busy <= 1;
            converged <= 0;
            iterations <= 0;
            legs <= 1;
            leg_iterations <= 0;
            active_cycles <= 0;
            node <= 0;
            for (edge_index = 0; edge_index < EDGES; edge_index++) begin
              v_to_c[edge_index] <= '0;
              c_to_v[edge_index] <= '0;
            end
            for (node = 0; node < VARIABLES; node++) begin
              prior_state[node] <= prior[node];
              belief[node] <= prior[node];
              relay_memory[node] <= '0;
              decoded_error[node] <= prior[node] < 0;
            end
            residual <= syndrome;
            residual_syndrome <= syndrome;
            state <= VAR_PHASE;
          end
        end

        VAR_PHASE: begin
          trace_valid <= 1;
          trace_is_check <= 0;
          trace_node <= node;
          active_cycles <= active_cycles + 1;
          gamma_value = gamma_for_iteration(legs, leg_iterations);
          relay_value = round_shift_away($signed(relay_memory[node]) * gamma_value, GAMMA_SHIFT);
          sum_value = $signed(prior_state[node]) + relay_value;
          for (edge_index = 0; edge_index < EDGES; edge_index++) begin
            if (variable_of_edge[edge_index*VARIABLE_W +: VARIABLE_W] == node) begin
              sum_value = sum_value + $signed(c_to_v[edge_index]);
            end
          end
          belief[node] <= saturate_signed(sum_value, B, CLIP);
          decoded_error[node] <= saturate_signed(sum_value, B, CLIP) < 0;
          for (edge_index = 0; edge_index < EDGES; edge_index++) begin
            if (variable_of_edge[edge_index*VARIABLE_W +: VARIABLE_W] == node) begin
              v_to_c[edge_index] <= saturate_signed(saturate_signed(sum_value, B, CLIP) - $signed(c_to_v[edge_index]), B, CLIP);
            end
          end
          if (node == VARIABLES - 1) begin
            node <= 0;
            state <= CHECK_PHASE;
          end else begin
            node <= node + 1;
          end
        end

        CHECK_PHASE: begin
          trace_valid <= 1;
          trace_is_check <= 1;
          trace_node <= node;
          active_cycles <= active_cycles + 1;
          for (edge_index = 0; edge_index < EDGES; edge_index++) begin
            if (check_of_edge[edge_index*CHECK_W +: CHECK_W] == node) begin
              min_value = CLIP;
              sign_value = syndrome[node] ? -1 : 1;
              other_count = 0;
              for (other = 0; other < EDGES; other++) begin
                if (check_of_edge[other*CHECK_W +: CHECK_W] == node && other != edge_index) begin
                  other_count++;
                  if (v_to_c[other] < 0) sign_value = -sign_value;
                  abs_value = v_to_c[other] < 0 ? -$signed(v_to_c[other]) : $signed(v_to_c[other]);
                  if (abs_value < min_value) min_value = abs_value;
                end
              end
              c_to_v[edge_index] <= other_count == 0 ? '0 : saturate_signed(sign_value * min_value, B, CLIP);
            end
          end
          if (node == CHECKS - 1) begin
            state <= DECIDE_PHASE;
          end else begin
            node <= node + 1;
          end
        end

        DECIDE_PHASE: begin
          trace_valid <= 1;
          trace_is_check <= 0;
          trace_node <= 32'hffff_fffe;
          active_cycles <= active_cycles + 1;
          residual <= residual_next;
          residual_syndrome <= residual_next;
          iterations <= iterations + 1;
          leg_iterations <= leg_iterations + 1;
          if (residual_next == '0) begin
            converged <= 1;
            state <= FINISH;
          end else if (leg_iterations + 1 >= MAX_ITERATIONS_PER_LEG) begin
            state <= RELAY_PHASE;
          end else begin
            node <= 0;
            state <= VAR_PHASE;
          end
        end

        RELAY_PHASE: begin
          active_cycles <= active_cycles + 1;
          leg_iterations <= 0;
          beta_value = beta_for_leg(legs);
          for (node = 0; node < VARIABLES; node++) begin
            updated_memory = memory_mix(
                relay_memory[node],
                $signed(belief[node]) - (decoded_error[node] ? 2 : 0),
                beta_value,
                M_SHIFT,
                B,
                CLIP);
            relay_memory[node] <= updated_memory;
            prior_state[node] <= saturate_signed($signed(belief[node]) + updated_memory, B, CLIP);
          end
          if (legs >= MAX_LEGS) begin
            state <= FINISH;
          end else begin
            legs <= legs + 1;
            node <= 0;
            state <= VAR_PHASE;
          end
        end

        FINISH: begin
          busy <= 0;
          done <= 1;
          state <= IDLE;
        end
      endcase
    end
  end
endmodule

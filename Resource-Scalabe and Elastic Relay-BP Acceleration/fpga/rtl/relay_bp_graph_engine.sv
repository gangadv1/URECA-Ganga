// Functional full-graph folded Relay-BP engine.
// CHECK_OF_EDGE and VARIABLE_OF_EDGE are generated from the same incidence
// package consumed by Python. One check/variable is processed per active cycle;
// replace that loop body with PC/PV replicated tiles after measurement locks.
module relay_bp_graph_engine #(
  parameter int CHECKS = 1,
  parameter int VARIABLES = 1,
  parameter int EDGES = 1,
  parameter int B = 8,
  parameter int M_SHIFT = 3,
  parameter int CLIP = (1 << (B - 1)) - 1,
  parameter int MAX_ITERATIONS = 3,
  parameter int MAX_LEGS = 1
) (
  input logic clk, rst, start,
  input logic [CHECKS-1:0] syndrome,
  input logic signed [B-1:0] prior [VARIABLES],
  input logic [M_SHIFT:0] gamma_int,
  input logic [M_SHIFT:0] beta_int,
  input logic [EDGES*((CHECKS <= 1) ? 1 : $clog2(CHECKS))-1:0] check_of_edge,
  input logic [EDGES*((VARIABLES <= 1) ? 1 : $clog2(VARIABLES))-1:0] variable_of_edge,
  output logic busy, done, converged,
  output logic [VARIABLES-1:0] decoded_error,
  output logic [$clog2(MAX_ITERATIONS+1)-1:0] iterations,
  output logic [$clog2(MAX_LEGS+1)-1:0] legs,
  output logic trace_valid, trace_is_check,
  output logic [31:0] trace_node, active_cycles
);
  import fixedpoint_relay_pkg::*;
  typedef enum logic [2:0] {IDLE, VAR_PHASE, CHECK, DECIDE, RELAY, FINISH} state_t;
  state_t state;
  integer node, edge_index, other, other_count;
  localparam int CHECK_W = (CHECKS <= 1) ? 1 : $clog2(CHECKS);
  localparam int VARIABLE_W = (VARIABLES <= 1) ? 1 : $clog2(VARIABLES);
  longint signed sum_value, relay_value, min_value, abs_value, sign_value;
  logic signed [B-1:0] v_to_c [0:EDGES-1];
  logic signed [B-1:0] c_to_v [0:EDGES-1];
  logic signed [B-1:0] belief [0:VARIABLES-1];
  logic signed [B-1:0] memory [0:VARIABLES-1];
  logic [CHECKS-1:0] residual;

  always_ff @(posedge clk) begin
    if (rst) begin
      state <= IDLE; busy <= 0; done <= 0; converged <= 0; iterations <= 0; legs <= 0;
      decoded_error <= '0; residual <= '0; active_cycles <= 0;
      for (edge_index = 0; edge_index < EDGES; edge_index++) begin v_to_c[edge_index] <= '0; c_to_v[edge_index] <= '0; end
      for (node = 0; node < VARIABLES; node++) begin belief[node] <= '0; memory[node] <= '0; end
    end else begin
      done <= 0; trace_valid <= 0;
      case (state)
        IDLE: if (start) begin
          busy <= 1; converged <= 0; iterations <= 0; legs <= 1; node <= 0; active_cycles <= 0;
          for (edge_index = 0; edge_index < EDGES; edge_index++) begin v_to_c[edge_index] <= '0; c_to_v[edge_index] <= '0; end
          for (edge_index = 0; edge_index < VARIABLES; edge_index++) begin belief[edge_index] <= prior[edge_index]; memory[edge_index] <= '0; end
          state <= VAR_PHASE;
        end
        VAR_PHASE: begin
          trace_valid <= 1; trace_is_check <= 0; trace_node <= node; active_cycles <= active_cycles + 1;
          relay_value = round_shift_away($signed(memory[node]) * $signed(gamma_int), M_SHIFT);
          sum_value = $signed(prior[node]) + relay_value;
          for (edge_index = 0; edge_index < EDGES; edge_index++) if (variable_of_edge[edge_index*VARIABLE_W +: VARIABLE_W] == node) sum_value = sum_value + $signed(c_to_v[edge_index]);
          belief[node] <= saturate_signed(sum_value, B, CLIP);
          decoded_error[node] <= saturate_signed(sum_value, B, CLIP) < 0;
          for (edge_index = 0; edge_index < EDGES; edge_index++) if (variable_of_edge[edge_index*VARIABLE_W +: VARIABLE_W] == node)
            v_to_c[edge_index] <= saturate_signed(saturate_signed(sum_value, B, CLIP) - $signed(c_to_v[edge_index]), B, CLIP);
          if (node == VARIABLES - 1) begin node <= 0; state <= CHECK; end else node <= node + 1;
        end
        CHECK: begin
          trace_valid <= 1; trace_is_check <= 1; trace_node <= node; active_cycles <= active_cycles + 1;
          for (edge_index = 0; edge_index < EDGES; edge_index++) if (check_of_edge[edge_index*CHECK_W +: CHECK_W] == node) begin
            min_value = CLIP; sign_value = syndrome[node] ? -1 : 1; other_count = 0;
            for (other = 0; other < EDGES; other++) if (check_of_edge[other*CHECK_W +: CHECK_W] == node && other != edge_index) begin
              other_count = other_count + 1;
              if (v_to_c[other] < 0) sign_value = -sign_value;
              abs_value = v_to_c[other] < 0 ? -$signed(v_to_c[other]) : $signed(v_to_c[other]);
              if (abs_value < min_value) min_value = abs_value;
            end
            c_to_v[edge_index] <= other_count == 0 ? '0 : saturate_signed(sign_value * min_value, B, CLIP);
          end
          if (node == CHECKS - 1) state <= DECIDE; else node <= node + 1;
        end
        DECIDE: begin
          active_cycles <= active_cycles + 1; residual = syndrome;
          for (edge_index = 0; edge_index < EDGES; edge_index++) residual[check_of_edge[edge_index*CHECK_W +: CHECK_W]] = residual[check_of_edge[edge_index*CHECK_W +: CHECK_W]] ^ decoded_error[variable_of_edge[edge_index*VARIABLE_W +: VARIABLE_W]];
          iterations <= iterations + 1;
          if (residual == '0) begin converged <= 1; state <= FINISH; end
          else if (iterations + 1 >= MAX_ITERATIONS) state <= RELAY;
          else begin node <= 0; state <= VAR_PHASE; end
        end
        RELAY: begin
          active_cycles <= active_cycles + 1;
          for (node = 0; node < VARIABLES; node++)
            memory[node] <= memory_mix(memory[node], $signed(belief[node]) - (decoded_error[node] ? 2 : 0), beta_int, M_SHIFT, B, CLIP);
          if (legs >= MAX_LEGS) state <= FINISH;
          else begin legs <= legs + 1; iterations <= 0; node <= 0; state <= VAR_PHASE; end
        end
        FINISH: begin busy <= 0; done <= 1; state <= IDLE; end
      endcase
    end
  end
endmodule

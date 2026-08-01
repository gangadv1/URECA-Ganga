// Standalone Relay-BP controller/FSM scaffold for the new RTL hierarchy.
module relay_bp_controller #(
  parameter int MAX_ITERATIONS_PER_LEG = 3,
  parameter int MAX_LEGS = 2,
  parameter int SLOT_W = 1,
  parameter int ITER_W = (MAX_ITERATIONS_PER_LEG * MAX_LEGS <= 1) ? 1 : $clog2(MAX_ITERATIONS_PER_LEG * MAX_LEGS + 1),
  parameter int LEG_W = (MAX_LEGS <= 1) ? 1 : $clog2(MAX_LEGS + 1)
) (
  input  logic clk,
  input  logic rst,
  input  logic start,
  input  logic converged_in,
  output logic busy,
  output logic done,
  output logic start_iteration,
  output logic start_leg,
  output logic check_phase,
  output logic variable_phase,
  output logic relay_phase,
  output logic decision_phase,
  output logic [$clog2(MAX_ITERATIONS_PER_LEG+1)-1:0] leg_iteration_count,
  output logic [ITER_W-1:0] total_iterations,
  output logic [LEG_W-1:0] leg_count,
  output logic trace_valid
);
  typedef enum logic [3:0] {IDLE, LOAD, READ, CHECK, VARIABLE, RELAY, DECIDE, NEXT_ITERATION, NEXT_LEG, DONE} state_t;
  state_t state;
  always_ff @(posedge clk) begin
    if (rst) begin
      state <= IDLE;
      busy <= 0;
      done <= 0;
      total_iterations <= 0;
      leg_count <= 0;
      leg_iteration_count <= 0;
    end else begin
      done <= 0;
      start_iteration <= 0;
      start_leg <= 0;
      trace_valid <= 0;
      case (state)
        IDLE: if (start) begin
          busy <= 1;
          total_iterations <= 0;
          leg_count <= 1;
          leg_iteration_count <= 0;
          state <= LOAD;
        end
        LOAD: begin start_iteration <= 1; state <= READ; end
        READ: state <= VARIABLE;
        VARIABLE: begin trace_valid <= 1; state <= CHECK; end
        CHECK: begin trace_valid <= 1; state <= DECIDE; end
        DECIDE: begin
          trace_valid <= 1;
          total_iterations <= total_iterations + 1'b1;
          leg_iteration_count <= leg_iteration_count + 1'b1;
          if (converged_in) state <= DONE;
          else if (leg_iteration_count + 1 >= MAX_ITERATIONS_PER_LEG) state <= RELAY;
          else state <= VARIABLE;
        end
        RELAY: begin trace_valid <= 1; state <= NEXT_ITERATION; end
        NEXT_ITERATION: begin
          leg_iteration_count <= 0;
          if (leg_count >= MAX_LEGS) state <= DONE;
          else begin leg_count <= leg_count + 1'b1; start_leg <= 1; state <= LOAD; end
        end
        NEXT_LEG: state <= DONE;
        DONE: begin busy <= 0; done <= 1; state <= IDLE; end
      endcase
    end
  end
  always_comb begin
    check_phase = state == CHECK;
    variable_phase = state == VARIABLE;
    relay_phase = state == RELAY;
    decision_phase = state == DECIDE;
  end
endmodule

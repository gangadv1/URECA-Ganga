// Folded/tiled controller for the Blueprint's new RTL path.
// Edge operations are provided by a generated schedule ROM.  The controller
// reuses PC/PV tiles over all graph slots and exposes phase/slot trace data.
module relay_bp_folded #(
  parameter int CHECKS = 72,
  parameter int VARIABLES = 144,
  parameter int EDGE_SLOTS = 1,
  parameter int B = 8,
  parameter int PC = 8,
  parameter int PV = 8,
  parameter int MAX_ITERATIONS = 8,
  parameter int MAX_LEGS = 2,
  parameter int SLOT_W = (EDGE_SLOTS <= 1) ? 1 : $clog2(EDGE_SLOTS),
  parameter int ITER_W = (MAX_ITERATIONS <= 1) ? 1 : $clog2(MAX_ITERATIONS + 1),
  parameter int LEG_W = (MAX_LEGS <= 1) ? 1 : $clog2(MAX_LEGS + 1)
) (
  input  logic clk, rst, start,
  input  logic [CHECKS-1:0] syndrome,
  input  logic [CHECKS-1:0] syndrome_after_iteration,
  output logic busy, done, converged,
  output logic [ITER_W-1:0] iteration_count,
  output logic [LEG_W-1:0] leg_count,
  output logic check_phase, variable_phase,
  output logic [SLOT_W-1:0] schedule_slot,
  output logic trace_valid,
  output logic [31:0] active_cycles
);
  typedef enum logic [2:0] {IDLE, CHECK, VARIABLE, DECIDE, NEXT_LEG, FINISH} state_t;
  state_t state;
  logic [CHECKS-1:0] residual;

  always_ff @(posedge clk) begin
    if (rst) begin
      state <= IDLE; busy <= 0; done <= 0; converged <= 0; iteration_count <= 0;
      leg_count <= 0; schedule_slot <= 0; active_cycles <= 0; residual <= '0;
    end else begin
      done <= 0;
      case (state)
        IDLE: if (start) begin
          busy <= 1; converged <= 0; iteration_count <= 0; leg_count <= 1;
          schedule_slot <= 0; active_cycles <= 0; residual <= syndrome; state <= CHECK;
        end
        CHECK: begin
          active_cycles <= active_cycles + 1;
          if (schedule_slot == EDGE_SLOTS - 1) begin schedule_slot <= 0; state <= VARIABLE; end
          else schedule_slot <= schedule_slot + 1'b1;
        end
        VARIABLE: begin
          active_cycles <= active_cycles + 1;
          if (schedule_slot == EDGE_SLOTS - 1) begin schedule_slot <= 0; state <= DECIDE; end
          else schedule_slot <= schedule_slot + 1'b1;
        end
        DECIDE: begin
          active_cycles <= active_cycles + 1;
          residual <= syndrome_after_iteration;
          iteration_count <= iteration_count + 1'b1;
          if (syndrome_after_iteration == '0) begin converged <= 1; state <= FINISH; end
          else if (iteration_count + 1 >= MAX_ITERATIONS) state <= NEXT_LEG;
          else state <= CHECK;
        end
        NEXT_LEG: if (leg_count >= MAX_LEGS) state <= FINISH;
          else begin leg_count <= leg_count + 1'b1; iteration_count <= 0; state <= CHECK; end
        FINISH: begin busy <= 0; done <= 1; state <= IDLE; end
      endcase
    end
  end
  always_comb begin
    check_phase = state == CHECK;
    variable_phase = state == VARIABLE;
    trace_valid = state == CHECK || state == VARIABLE || state == DECIDE;
  end
endmodule

// Convergence and decision block for the Relay-BP golden RTL path.
module relay_bp_convergence_decision #(
  parameter int CHECKS = 1,
  parameter int VARIABLES = 1
) (
  input  logic [CHECKS-1:0] syndrome,
  input  logic [VARIABLES-1:0] decoded_error,
  input  logic [$clog2((CHECKS <= 1) ? 1 : CHECKS + 1)-1:0] residual_score_in,
  output logic [CHECKS-1:0] residual_syndrome,
  output logic converged,
  output logic [$clog2((CHECKS <= 1) ? 1 : CHECKS + 1)-1:0] residual_score
);
  always_comb begin
    residual_syndrome = syndrome;
    for (int edge_index = 0; edge_index < CHECKS; edge_index++) begin
      residual_syndrome[edge_index] = syndrome[edge_index] ^ decoded_error[edge_index % VARIABLES];
    end
    converged = (residual_syndrome == '0);
    residual_score = residual_score_in;
  end
endmodule

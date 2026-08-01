// Simple synthesizable edge-message memory for the new Relay-BP hierarchy.
module relay_bp_edge_message_memory #(
  parameter int EDGES = 1,
  parameter int B = 4
) (
  input  logic clk,
  input  logic write_enable,
  input  logic [$clog2((EDGES <= 1) ? 1 : EDGES)-1:0] write_index,
  input  logic signed [B-1:0] write_data,
  input  logic [$clog2((EDGES <= 1) ? 1 : EDGES)-1:0] read_index,
  output logic signed [B-1:0] read_data
);
  logic signed [B-1:0] storage [0:EDGES-1];
  always_ff @(posedge clk) begin
    if (write_enable) storage[write_index] <= write_data;
  end
  always_comb read_data = storage[read_index];
endmodule

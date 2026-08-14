// Generic one-cycle synchronous P=4 packed memory.
// A read accepted at cycle n produces rsp_valid/data at cycle n+1.
// Simultaneous read/write of one word is deterministic read-first.
module relay_bp_sync_p4_memory #(
  parameter int WIDTH=18, LOGICAL_DEPTH=1, P=4,
  parameter int WORDS=(LOGICAL_DEPTH+P-1)/P,
  parameter int AW=(WORDS<=1)?1:$clog2(WORDS)
) (
  input logic clk,
  input logic rd_req, input logic [AW-1:0] rd_word,
  output logic rsp_valid, output logic signed [WIDTH-1:0] rsp_data[0:P-1],
  input logic wr_req, input logic [AW-1:0] wr_word,
  input logic [P-1:0] wr_mask, input logic signed [WIDTH-1:0] wr_data[0:P-1]
);
  logic signed [WIDTH-1:0] storage[0:WORDS-1][0:P-1];
  integer lane;
  always_ff @(posedge clk) begin
    rsp_valid <= rd_req;
    if(rd_req) for(lane=0;lane<P;lane=lane+1) rsp_data[lane] <= storage[rd_word][lane];
    if(wr_req) for(lane=0;lane<P;lane=lane+1) if(wr_mask[lane]) storage[wr_word][lane] <= wr_data[lane];
  end
endmodule

// Scalar companion for CSR pointers, syndrome bits, and iteration limits.
module relay_bp_sync_scalar_memory #(
  parameter int WIDTH=19, DEPTH=1, AW=(DEPTH<=1)?1:$clog2(DEPTH)
) (
  input logic clk,
  input logic rd_req, input logic [AW-1:0] rd_addr,
  output logic rsp_valid, output logic signed [WIDTH-1:0] rsp_data,
  input logic wr_req, input logic [AW-1:0] wr_addr,
  input logic signed [WIDTH-1:0] wr_data
);
  logic signed [WIDTH-1:0] storage[0:DEPTH-1];
  always_ff @(posedge clk) begin
    rsp_valid <= rd_req;
    if(rd_req) rsp_data <= storage[rd_addr]; // read-first when addresses coincide
    if(wr_req) storage[wr_addr] <= wr_data;
  end
endmodule

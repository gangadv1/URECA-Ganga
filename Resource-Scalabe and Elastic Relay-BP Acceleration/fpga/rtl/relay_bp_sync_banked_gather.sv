// Four single-port banks supporting conflict-aware arbitrary edge gathers.
// Address a maps to bank a%4 and row a/4. req_ready is false if two valid
// lanes request the same bank; the controller must retry a conflict-free mask.
module relay_bp_sync_banked_gather #(
  parameter int WIDTH=18, DEPTH=1, P=4,
  parameter int AW=(DEPTH<=1)?1:$clog2(DEPTH),
  parameter int ROWS=(DEPTH+P-1)/P,
  parameter int RW=(ROWS<=1)?1:$clog2(ROWS)
) (
  input logic clk,
  input logic rd_req, input logic [P-1:0] rd_mask,
  input logic [AW-1:0] rd_addr[0:P-1], output logic rd_ready,
  output logic rsp_valid, output logic [P-1:0] rsp_mask,
  output logic signed [WIDTH-1:0] rsp_data[0:P-1],
  input logic wr_req, input logic [P-1:0] wr_mask,
  input logic [AW-1:0] wr_addr[0:P-1], output logic wr_ready,
  input logic signed [WIDTH-1:0] wr_data[0:P-1]
);
  logic signed [WIDTH-1:0] bank[0:P-1][0:ROWS-1];
  integer i,j,b;
  always_comb begin
    rd_ready=1;wr_ready=1;
    for(i=0;i<P;i=i+1)for(j=i+1;j<P;j=j+1)begin
      if(rd_mask[i]&&rd_mask[j]&&(rd_addr[i]%P)==(rd_addr[j]%P))rd_ready=0;
      if(wr_mask[i]&&wr_mask[j]&&(wr_addr[i]%P)==(wr_addr[j]%P))wr_ready=0;
    end
  end
  always_ff @(posedge clk) begin
    rsp_valid<=rd_req&&rd_ready;rsp_mask<=rd_mask;
    if(rd_req&&rd_ready)for(i=0;i<P;i=i+1)if(rd_mask[i])rsp_data[i]<=bank[rd_addr[i]%P][rd_addr[i]/P];
    if(wr_req&&wr_ready)for(i=0;i<P;i=i+1)if(wr_mask[i])bank[wr_addr[i]%P][wr_addr[i]/P]<=wr_data[i];
  end
endmodule

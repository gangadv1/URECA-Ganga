// Relay coefficient storage.  The table is kept explicit so the separate-M
// and shared-scale paths can be compared in hardware.
module relay_bp_coefficient_table #(
  parameter int ENTRIES = 16,
  parameter int M_SHIFT = 3
) (
  input  logic [$clog2((ENTRIES <= 1) ? 1 : ENTRIES)-1:0] index,
  output logic [M_SHIFT:0] beta_int
);
  logic [M_SHIFT:0] storage [0:ENTRIES-1];
  initial begin
    for (int i = 0; i < ENTRIES; i++) storage[i] = '0;
  end
  always_comb beta_int = storage[index];
endmodule

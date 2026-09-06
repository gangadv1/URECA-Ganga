# Read/write semantics status

The standalone RTL declares read-first private RAM behavior and prohibits same-address message read/write in normal M4 operation. Functional Icarus tests passed, but Vivado primitive configuration and collision-mode reporting were not produced. Compatibility with a selected FPGA's RAMB18/RAMB36 modes is therefore **not synthesis-confirmed**.

# Standalone BRAM inference status

`iverilog`/`vvp` were available and used for simulation. Neither Yosys nor Vivado was present, so primitive inference, BRAM/LUTRAM/register counts, and warnings were **not executed**. `synth_yosys.ys` and `synth_vivado.tcl` are prepared in `fpga/testbench/m4_memory_fabric/`. The RTL carries `ram_style="block"`, but that attribute is not evidence of successful inference. Full-size packing remains the analytical 980-BRAM36 result until an FPGA synthesis tool confirms it.

# M4 standalone memory-fabric RTL validation

This isolated study does not instantiate or synthesize the Relay-BP decoder. Run `sh fpga/testbench/m4_memory_fabric/run_tests.sh`, then `python3 fpga/testbench/m4_memory_fabric/analyze_results.py`. Icarus simulations cover one-/two-cycle reads, simultaneous E0/E1 shared reads, same-address reads, message alias transitions, and 5,000 deterministic stress cycles per mode. Synthesis scripts are prepared but were not executed in this environment.

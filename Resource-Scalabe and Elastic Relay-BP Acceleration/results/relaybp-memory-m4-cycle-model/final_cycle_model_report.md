# M4 cycle-level analytical report

The frozen BA2 one-cycle-read controller baseline remains exact and adds no memory stalls. Two-cycle reads are legal with return-valid fences and add 169,038 structural dependency bubbles per iteration-plus-relay template. Across 128 N=2 shots the L2 first-success increase is mean 9,028,218.4, p95 27,876,948.3, p99 42,268,903.7, max 90,423,558 modeled cycles (mean 2.261%); 0 winner identities change and no success is lost. This is not decoder divergence or an FPGA measurement.

RAMB36 width/depth packing gives 980 blocks; TDP port-aware packing remains 980 because each shared bank needs at most two reads and each private bank needs at most one read plus one write. Same-address read/write is forbidden by the semantic return fence, so read-first, write-first, and no-change primitives are decoder-equivalent for issued requests.

The port-aware value is numerically below GARI's measured three-core 2,121 BRAM and above its measured one-core 704 BRAM. Uncertainty remains material: primitive mode availability, initialization constraints, ECC/parity use, tool packing, routing, FIFOs, and controller storage are not synthesized here, while GARI is measured from a different architecture. No hardware-resource win is established.

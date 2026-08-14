# P=4 single-engine logical memory interfaces

These are logical port requirements, not inferred BRAM/URAM mappings.

| Memory | Width | Depth | Direction | P=4 active-phase requirement | Banking expectation |
|---|---:|---:|---|---|---|
| nu | 18 signed | 391,320 | R/W | check: 4 reads/cycle; variable: 4 writes/cycle; leg reset writes or prior bypass | >=4 banks or 72-bit packed word |
| mu | 18 signed | 391,320 | R/W | check: 4 writes/cycle; variable: up to 4 reads/cycle | >=4 banks; edge-ID-consistent check/variable access |
| marginals | 18 signed | 67,752 | R/W | up to 4 old reads and 4 current writes/cycle, read-before-write | 4 banks or true dual-port organization |
| priors | 18 signed | 67,752 | Read-only during decode | 4 reads/cycle for variable bias; potentially 4 more for implicit edge reset | 4 banks; replication may be needed for reset overlap |
| gamma | 5 signed | 67,752 | R/W at leg boundary, read during variable phase | 4 reads/cycle; RNG fill up to 4 writes/cycle | 4 banks |
| syndrome | 1 | 1,728 | Load then read | up to 4 check bits/cycle; convergence reuses | packed/banked ROM-like shot buffer |
| hard decision | 1 | 67,752 | R/W | 4 writes/cycle in variable phase; 4 reads/cycle in convergence | 4 banks or packed words |
| check row pointers | 19 | 1,729 | Read-only | boundary lookup for active checks | small replicated/banked table |
| check edge/fault IDs | edge ID 19 + fault ID 17 | 391,320 | Read-only | 4 records/cycle | 4 banks/packed wide word |
| variable row pointers | 19 | 67,753 | Read-only | boundary lookup for active variables | banked table/cache |
| variable-to-edge permutation | 19 | 391,320 | Read-only | 4 edge IDs/cycle | 4 banks/packed wide word |

Candidate correction storage is another 67,752-bit mutable memory for generic S/lowest-weight operation. Bias and incoming-total arrays are not persistent: bias and the 22-bit total remain local to the variable transaction.

Address request/response interfaces must include valid/ready, address, data, write enable/byte mask where relevant, and an explicit fixed or tagged read latency. The later traversal controller must not assume asynchronous reads.

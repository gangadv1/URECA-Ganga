# Synchronous P=4 memory architecture

## Contract

`relay_bp_sync_p4_memory` accepts a registered word read request and returns `rsp_valid` with four lanes one cycle later. Writes have four lane enables. A same-cycle read and write of one word is read-first. Tail lanes are masked and initialized/padded to zero by the image generator.

`relay_bp_sync_scalar_memory` provides the corresponding one-cycle scalar interface for CSR pointers, syndrome, and configuration tables.

`relay_bp_sync_banked_gather` implements four ordinary single-port banks with `logical_address % 4` bank selection and `logical_address / 4` row selection. It rejects a request when two active lanes select one bank. The traversal controller must issue conflict-free subsets and consume data only on `rsp_valid`.

## Organization

- Check-ordered nu/mu and edge-fault records: four-lane packed words because check CSR incidences are contiguous.
- Variable-to-edge permutation: four-lane packed sequential words.
- Arbitrary mu reads and nu writes after permutation: four banks with conflict-aware sub-request scheduling.
- Prior, marginal, gamma, and decision: four-lane node words for sequential variable groups; a scalar variable pipeline may select one lane after a registered response.
- Check/variable row pointers and syndrome: scalar synchronous memories. Adjacent pointer lookup requires replication, a two-port wrapper, or two registered reads; no multiport assumption is permitted.

## Integration status

The adapters, collision detection, timing contract, image format, and directed tests exist. The complete engine FSM has not yet been rewritten to drive these request/response ports. In particular, it still accesses its internal arrays and therefore cannot be classified as memory-backed. Required new controller substates are pointer-request/wait, packed-word-request/wait, conflict-subset request/wait, and write-commit for every traversal phase.

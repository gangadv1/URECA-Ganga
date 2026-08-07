"""Directed tests for canonical fixed-point Relay-BP semantics."""

from __future__ import annotations

import numpy as np
from scipy import sparse

from fixedpoint import FixedConfig
from relay_bp_fixed import FixedRelayBPDecoder, FixedRelayConfig, FixedRelayLegConfig


def test_fixed_sparse_and_dense_match_with_negative_per_node_gamma() -> None:
    h = np.array([[1, 1, 0], [0, 1, 1]], dtype=np.uint8)
    gamma = np.array([-0.25, 0.125, 0.5])
    config = FixedRelayConfig(
        fixed=FixedConfig(b=8, g=4, M=8),
        leg_configs=(FixedRelayLegConfig(max_iterations=3, gamma=gamma),),
    )
    dense = FixedRelayBPDecoder(h, config).decode([2.2, 3.1, 1.7], [1, 0])
    sparse_result = FixedRelayBPDecoder(sparse.csr_matrix(h), config).decode([2.2, 3.1, 1.7], [1, 0])
    assert dense.to_json_dict() == sparse_result.to_json_dict()
    assert dense.metadata["legacy_relay_memory_used"] is False


def test_fixed_zero_posterior_decodes_as_error_and_converges_by_syndrome() -> None:
    decoder = FixedRelayBPDecoder(
        np.array([[1]], dtype=np.uint8),
        FixedRelayConfig(
            fixed=FixedConfig(b=6, g=2, M=8),
            leg_configs=(FixedRelayLegConfig(max_iterations=1, gamma=0.0),),
        ),
    )
    result = decoder.decode([0.0], [1])
    np.testing.assert_array_equal(result.decoded_error, np.array([1], dtype=np.uint8))
    assert result.converged


def test_fixed_relay_handoff_has_no_carry_memory_state() -> None:
    decoder = FixedRelayBPDecoder(
        np.array([[1, 1, 1]], dtype=np.uint8),
        FixedRelayConfig(
            fixed=FixedConfig(b=8, g=4, M=8),
            leg_configs=(
                FixedRelayLegConfig(max_iterations=1, gamma=0.0),
                FixedRelayLegConfig(max_iterations=1, gamma=0.5),
            ),
            S=2,
            R=2,
            trace_iterations=True,
        ),
    )
    result = decoder.decode([2.0, 3.0, 4.0], [0])
    assert result.metadata["relay_handoff"] == "previous leg final marginals only"
    assert result.metadata["legacy_relay_memory_used"] is False
    np.testing.assert_array_equal(result.relay_memory, np.zeros(3, dtype=np.int64))

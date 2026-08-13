"""Directed tests for canonical fixed-point Relay-BP semantics."""

from __future__ import annotations

import numpy as np
from scipy import sparse

from fixedpoint import FixedConfig
from relay_bp_fixed import (
    BlockFloatingRelayBPDecoder,
    FixedRelayBPDecoder,
    FixedRelayConfig,
    FixedRelayLegConfig,
    SeparatedExponentRelayBPDecoder,
)


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


def test_block_floating_shared_exponent_preserves_signs_and_order() -> None:
    values = np.array([-1024.0, -17.0, 0.0, 9.0, 511.0])
    exponent = BlockFloatingRelayBPDecoder._choose_exponent(1024.0, 127)
    quantized = BlockFloatingRelayBPDecoder._quantize_real(values, exponent)

    assert exponent == 4
    assert np.array_equal(np.signbit(quantized[quantized != 0]), np.signbit(values[quantized != 0]))
    assert np.all(np.diff(quantized) >= 0)


def test_block_floating_metadata_and_no_legacy_memory() -> None:
    decoder = BlockFloatingRelayBPDecoder(
        np.array([[1, 1]], dtype=np.uint8),
        FixedRelayConfig(
            fixed=FixedConfig(b=8, g=4, M=16),
            leg_configs=(FixedRelayLegConfig(max_iterations=2, gamma=0.125),),
        ),
    )
    result = decoder.decode(np.array([6.0, 6.0]), np.array([1], dtype=np.uint8))

    assert result.metadata["arithmetic"]["representation"] == "iteration-shared block floating"
    assert result.metadata["relay_handoff"] == "previous leg final marginals only"
    assert result.metadata["legacy_relay_memory_used"] is False
    assert result.metadata["block_floating"]["exponent_min"] >= 0


def test_separated_exponent_alignment_uses_power_of_two_rounding() -> None:
    values = np.array([-7, -3, 3, 7], dtype=np.int64)
    np.testing.assert_array_equal(
        SeparatedExponentRelayBPDecoder._align_mantissa(values, 2, 1),
        np.array([-14, -6, 6, 14]),
    )
    np.testing.assert_array_equal(
        SeparatedExponentRelayBPDecoder._align_mantissa(values, 1, 3),
        np.array([-2, -1, 1, 2]),
    )


def test_separated_exponent_headroom_and_metadata() -> None:
    config = FixedRelayConfig(
        fixed=FixedConfig(b=8, g=4, M=16),
        leg_configs=(FixedRelayLegConfig(max_iterations=2, gamma=0.125),),
    )
    full = SeparatedExponentRelayBPDecoder(np.array([[1, 1]], dtype=np.uint8), config)
    headroom = SeparatedExponentRelayBPDecoder(
        np.array([[1, 1]], dtype=np.uint8), config, headroom_fraction=0.75
    )
    assert full._block_exponent(100.0) == 0
    assert headroom._block_exponent(100.0) == 1
    result = headroom.decode(np.array([6.0, 6.0]), np.array([1], dtype=np.uint8))
    assert result.metadata["arithmetic"]["headroom_fraction"] == 0.75
    assert result.metadata["legacy_relay_memory_used"] is False


def test_state_percentile_cap_reduces_state_exponent_and_records_clipping() -> None:
    config = FixedRelayConfig(
        fixed=FixedConfig(b=12, g=4, M=16),
        leg_configs=(FixedRelayLegConfig(max_iterations=1, gamma=0.125),),
    )
    decoder = SeparatedExponentRelayBPDecoder(
        np.array([[1, 1, 1, 1]], dtype=np.uint8), config, state_percentile=99.0
    )
    result = decoder.decode(np.array([6.0, 6.0, 6.0, 6.0]), np.array([1], dtype=np.uint8))
    block = result.metadata["block_floating"]
    assert result.metadata["arithmetic"]["state_percentile"] == 99.0
    assert block["state_clip_candidates"] > 0
    assert block["state_deliberately_clipped"] >= 0


def test_separated_exponent_is_limited_to_unsigned_width() -> None:
    config = FixedRelayConfig(
        fixed=FixedConfig(b=12, g=4, M=16),
        leg_configs=(FixedRelayLegConfig(max_iterations=1, gamma=0.0),),
    )
    decoder = SeparatedExponentRelayBPDecoder(
        np.array([[1, 1]], dtype=np.uint8), config, exponent_bits=3
    )
    assert decoder._block_exponent(float(2**30)) == 7

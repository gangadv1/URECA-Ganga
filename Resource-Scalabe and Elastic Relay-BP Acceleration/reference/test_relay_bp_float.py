"""Small deterministic conformance tests for the floating Relay-BP path."""

from __future__ import annotations

import numpy as np
from scipy import sparse

from relay_bp_float import FloatRelayBPDecoder, RelayLegConfig


def test_sparse_incidence_path_matches_dense_path() -> None:
    h = np.array([[1, 0, 1, 1], [0, 1, 1, 0]], dtype=np.uint8)
    syndrome = np.array([1, 0], dtype=np.uint8)
    lambdas = np.array([0.7, 1.1, -0.2, 0.4])
    legs = (RelayLegConfig(max_iterations=4, gamma=0.125),)
    dense = FloatRelayBPDecoder(h, leg_configs=legs, trace_messages=True).decode(lambdas, syndrome)
    sparse_result = FloatRelayBPDecoder(sparse.csr_matrix(h), leg_configs=legs, trace_messages=True).decode(
        lambdas, syndrome
    )

    assert dense.to_json_dict() == sparse_result.to_json_dict()


def test_independent_ensemble_restarts_original_marginals() -> None:
    h = np.array([[0, 1, 1], [1, 1, 0]], dtype=np.uint8)
    syndrome = np.array([1, 0], dtype=np.uint8)
    lambdas = np.array([0.4, 0.8, 1.2])
    legs = (
        RelayLegConfig(max_iterations=1, gamma=0.25),
        RelayLegConfig(max_iterations=1, gamma=0.25),
    )
    relay = FloatRelayBPDecoder(h, leg_configs=legs, S=2, R=2, trace_messages=True).decode(lambdas, syndrome)
    ensemble = FloatRelayBPDecoder(
        h, leg_configs=legs, S=2, R=2, trace_messages=True, relay_handoff=False
    ).decode(lambdas, syndrome)

    relay_second = next(record for record in relay.trace if record.leg_index == 1)
    ensemble_second = next(record for record in ensemble.trace if record.leg_index == 1)
    expected_ensemble_bias = (1.0 - 0.25) * lambdas + 0.25 * lambdas
    np.testing.assert_allclose(ensemble_second.lambda_bias, expected_ensemble_bias)
    assert not np.allclose(relay_second.lambda_bias, ensemble_second.lambda_bias)


def test_dmem_bp_uses_paper_update_order_and_previous_marginal() -> None:
    h = np.array([[0, 1, 1], [1, 1, 0]], dtype=np.uint8)
    syndrome = np.array([1, 0], dtype=np.uint8)
    lambdas = np.array([0.4, 0.8, 1.2])
    gamma = np.array([-0.3, 0.15, 0.6])
    decoder = FloatRelayBPDecoder(
        h,
        leg_configs=(RelayLegConfig(max_iterations=2, gamma=gamma),),
        S=1,
        R=1,
        trace_messages=True,
    )

    result = decoder.decode(lambdas, syndrome)

    assert len(result.trace) == 2
    first_marginal = np.asarray(result.trace[0].beliefs)
    second_bias = np.asarray(result.trace[1].lambda_bias)
    expected_bias = (1.0 - gamma) * lambdas + gamma * first_marginal
    np.testing.assert_allclose(second_bias, expected_bias)

    # On the first iteration M(0)=lambda, so Lambda(1)=lambda.  Check messages
    # are therefore formed from the initialized nu(0)=lambda before M(1).
    np.testing.assert_allclose(result.trace[0].lambda_bias, lambdas)
    np.testing.assert_allclose(result.trace[0].check_to_var[0], [0.0, -1.2, -0.8])
    np.testing.assert_allclose(result.trace[0].check_to_var[1], [0.8, 0.4, 0.0])


def test_relay_bp_s_relays_marginals_and_selects_lowest_weight_solution() -> None:
    h = np.array([[0, 1, 1], [1, 1, 1]], dtype=np.uint8)
    syndrome = np.array([0, 1], dtype=np.uint8)
    lambdas = np.array([0.4, 0.8, 1.2])
    legs = (
        RelayLegConfig(max_iterations=3, gamma=-1.0),
        RelayLegConfig(max_iterations=3, gamma=-1.0),
    )
    decoder = FloatRelayBPDecoder(h, leg_configs=legs, S=2, R=2, trace_messages=True)

    result = decoder.decode(lambdas, syndrome)

    assert result.converged is True
    assert result.solutions_found == 2
    assert result.relay_legs == 2
    np.testing.assert_allclose(result.solution_weights, (0.4, 2.4))
    np.testing.assert_array_equal(result.decoded_error, np.array([1, 0, 0], dtype=np.uint8))
    np.testing.assert_array_equal((h @ result.decoded_error) & 1, syndrome)

    converged_records = [record for record in result.trace if record.converged]
    assert [record.decoded_error for record in converged_records] == [[1, 0, 0], [1, 1, 1]]


def test_gross_defaults_sample_reproducible_per_node_negative_gamma() -> None:
    h = np.array([[1, 1, 1]], dtype=np.uint8)
    syndrome = np.array([1], dtype=np.uint8)
    lambdas = np.array([1.0, 2.0, 3.0])
    first = FloatRelayBPDecoder(h, S=2, R=2, seed=17, trace_messages=True).decode(lambdas, syndrome)
    second = FloatRelayBPDecoder(h, S=2, R=2, seed=17, trace_messages=True).decode(lambdas, syndrome)

    assert first.metadata["leg_max_iterations"] == [80, 60]
    assert first.to_json_dict() == second.to_json_dict()
    second_leg = next(record for record in first.trace if record.leg_index == 1)
    gamma = np.asarray(second_leg.gamma)
    assert gamma.shape == (3,)
    assert np.all(gamma >= -0.24)
    assert np.all(gamma <= 0.66)
    assert len(set(gamma.tolist())) == 3
    assert np.any(gamma < 0.0)


def test_zero_marginal_decodes_as_error() -> None:
    decision = FloatRelayBPDecoder._hard_decision(np.array([1.0, 0.0, -0.0, -1.0]))
    np.testing.assert_array_equal(decision, np.array([0, 1, 1, 1], dtype=np.uint8))


def test_degree_one_check_emits_official_maximum_magnitude_message() -> None:
    decoder = FloatRelayBPDecoder(
        np.array([[1]], dtype=np.uint8),
        leg_configs=(RelayLegConfig(max_iterations=1, gamma=0.0),),
        trace_messages=True,
    )
    result = decoder.decode(np.array([2.0]), np.array([1], dtype=np.uint8))

    assert result.trace[0].check_to_var[0][0] == -np.finfo(float).max
    np.testing.assert_array_equal(result.decoded_error, np.array([1], dtype=np.uint8))
    assert result.converged is True


def test_rng_state_advances_across_decode_calls() -> None:
    h = np.array([[1, 1, 1]], dtype=np.uint8)
    syndrome = np.array([1], dtype=np.uint8)
    lambdas = np.array([1.0, 2.0, 3.0])
    decoder = FloatRelayBPDecoder(h, S=2, R=2, seed=17, trace_messages=True)

    first = decoder.decode(lambdas, syndrome)
    second = decoder.decode(lambdas, syndrome)
    fresh = FloatRelayBPDecoder(h, S=2, R=2, seed=17, trace_messages=True).decode(lambdas, syndrome)

    first_gamma = next(record.gamma for record in first.trace if record.leg_index == 1)
    second_gamma = next(record.gamma for record in second.trace if record.leg_index == 1)
    fresh_gamma = next(record.gamma for record in fresh.trace if record.leg_index == 1)
    np.testing.assert_allclose(first_gamma, fresh_gamma)
    assert not np.allclose(first_gamma, second_gamma)


def test_selected_solution_returns_its_own_marginals() -> None:
    h = np.array([[0, 1, 1], [1, 1, 1]], dtype=np.uint8)
    syndrome = np.array([0, 1], dtype=np.uint8)
    lambdas = np.array([0.4, 0.8, 1.2])
    decoder = FloatRelayBPDecoder(
        h,
        leg_configs=(
            RelayLegConfig(max_iterations=3, gamma=-1.0),
            RelayLegConfig(max_iterations=3, gamma=-1.0),
        ),
        S=2,
        R=2,
        trace_messages=True,
    )

    result = decoder.decode(lambdas, syndrome)
    converged = [record for record in result.trace if record.converged]
    assert result.solution_weights[0] < result.solution_weights[1]
    np.testing.assert_allclose(result.beliefs, converged[0].beliefs)
    assert not np.allclose(result.beliefs, converged[-1].beliefs)

# Installed Sinter 1.16.0 conversion source, retained to document metric semantics.
def shot_error_rate_to_piece_error_rate(shot_error_rate: Union[float, 'sinter.Fit'], *, pieces: float, values: float = 1) -> Union[float, 'sinter.Fit']:
    """Convert from total error rate to per-piece error rate.

    Args:
        shot_error_rate: The rate at which shots fail. If this is set to a sinter.Fit,
            the conversion broadcasts over the low,best,high of the fit.
        pieces: The number of xor-pieces we want to subdivide each shot into,
            as if each piece was an independent chance for the shot to fail and
            the total chance of a shot failing was the xor of each piece
            failing.
        values: The number of or-pieces each shot's failure is being formed out
            of.

    Returns:
        Let N = `pieces` (number of rounds)
        Let V = `values` (number of observables)
        Let S = `shot_error_rate`
        Let R = the returned result

        R satisfies the following property. Let X be the probability of each
        observable flipping, each round. R will be the probability that any of
        the observables is flipped after 1 round, given this X. X is chosen to
        satisfy the following condition. If a Bernoulli distribution with
        probability X is sampled V*N times, and the results grouped into V
        groups of N, and each group is reduced to a single value using XOR, and
        then the reduced group values are reduced to a single final value using
        OR, then this final value will be True with probability S.

        Or, in other words, if a shot consists of N rounds which V independent
        observables must survive, then R is like the per-round failure for
        any of the observables.

    Examples:
        >>> import sinter
        >>> sinter.shot_error_rate_to_piece_error_rate(
        ...     shot_error_rate=0.1,
        ...     pieces=2,
        ... )
        0.05278640450004207
        >>> sinter.shot_error_rate_to_piece_error_rate(
        ...     shot_error_rate=0.05278640450004207,
        ...     pieces=1 / 2,
        ... )
        0.10000000000000003
        >>> sinter.shot_error_rate_to_piece_error_rate(
        ...     shot_error_rate=1e-9,
        ...     pieces=100,
        ... )
        1.000000082740371e-11
        >>> sinter.shot_error_rate_to_piece_error_rate(
        ...     shot_error_rate=0.6,
        ...     pieces=10,
        ...     values=2,
        ... )
        0.12052311142021144
    """

    if isinstance(shot_error_rate, Fit):
        return Fit(
            low=shot_error_rate_to_piece_error_rate(shot_error_rate=shot_error_rate.low, pieces=pieces, values=values),
            best=shot_error_rate_to_piece_error_rate(shot_error_rate=shot_error_rate.best, pieces=pieces, values=values),
            high=shot_error_rate_to_piece_error_rate(shot_error_rate=shot_error_rate.high, pieces=pieces, values=values),
        )

    if not (0 <= shot_error_rate <= 1):
        raise ValueError(f'need (0 <= shot_error_rate={shot_error_rate} <= 1)')
    if pieces <= 0:
        raise ValueError('need pieces > 0')
    if not isinstance(pieces, (int, float)):
        raise ValueError('need isinstance(pieces, (int, float)')
    if not isinstance(values, (int, float)):
        raise ValueError('need isinstance(values, (int, float)')
    if pieces == 1:
        return shot_error_rate
    if values != 1:
        p = 1 - (1 - shot_error_rate)**(1 / values)
        p = shot_error_rate_to_piece_error_rate(p, pieces=pieces)
        return 1 - (1 - p)**values

    if shot_error_rate > 0.5:
        return 1 - shot_error_rate_to_piece_error_rate(1 - shot_error_rate, pieces=pieces)
    assert 0 <= shot_error_rate <= 0.5
    randomize_rate = 2*shot_error_rate
    round_randomize_rate = 1 - (1 - randomize_rate)**(1 / pieces)
    round_error_rate = round_randomize_rate / 2

    if round_error_rate == 0:
        # The intermediate numbers got too small. Fallback to division approximation.
        return shot_error_rate / pieces

    return round_error_rate

"""Decoder-independent canonical scoring; called only AFTER decoding.

The sampled logical label exists at this boundary, never in gari_adapter.decode.
The same rule as canonical Relay-BP: (H correction == syndrome) AND
(L correction == observed logical label), all arithmetic over GF(2).
"""
import numpy as np


def score_correction(H, L, raw_syndrome, correction, observed_logicals):
    syndrome = np.asarray(raw_syndrome)
    correction = np.asarray(correction)
    observed = np.asarray(observed_logicals)
    for value, shape in ((syndrome,(H.shape[0],)),(correction,(H.shape[1],)),(observed,(L.shape[0],))):
        if value.shape != shape or value.dtype.kind not in 'biu' or not np.isin(value,(0,1)).all():
            raise ValueError(f'Expected binary array of shape {shape}')
    predicted_syndrome = np.asarray(H@correction).ravel()%2
    predicted_logicals = np.asarray(L@correction).ravel()%2
    syndrome_valid = bool(np.array_equal(predicted_syndrome,syndrome))
    logical_match = bool(np.array_equal(predicted_logicals,observed))
    return dict(syndrome_valid=syndrome_valid,logical_match=logical_match,
                success=syndrome_valid and logical_match,
                logical_mismatch=not logical_match,
                canonical_failure=not(syndrome_valid and logical_match),
                residual_detector_weight=int(np.count_nonzero(predicted_syndrome!=syndrome)),
                residual_logical_weight=int(np.count_nonzero(predicted_logicals!=observed)))

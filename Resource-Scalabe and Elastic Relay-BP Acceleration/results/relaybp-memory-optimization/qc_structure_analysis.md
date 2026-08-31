# Gross/QC and circuit-level regularity audit

## Code-level structure

The Gross code is a structured bivariate-bicycle code, so its code-level parity checks can be described using circulant shifts. Such formulas can greatly reduce storage for a code-capacity matrix.

## Circuit-level expansion

The selected graph is not merely the code-level parity matrix. Stim circuit faults expand into 67,752 variables with detector degrees 1–9 and incidences spanning measurement time. Fault probabilities, logical attachments, boundary rounds, separators, and circuit locations distinguish faults that would be identical under a code-only view.

The actual graph nevertheless contains measurable round-translation regularity:

- 67,752 exact detector/observable/separator signatures are unique.
- Normalizing detector IDs by 144-detector measurement-round translations gives 12,096 templates.
- 61,704 faults belong to templates occurring more than once.
- Maximum template repetition is 12.
- Detector spans are zero rounds for 6,696 faults, one for 36,576, and two for 24,480.

This suggests template-plus-round encoding could reduce topology storage.

## Why no M4 QC saving is credited

BA2 assigns global fault and edge addresses from co-access statistics. A simple QC/template generator produces mathematical detector/fault identities, not necessarily their BA2 runtime addresses. Preserving BA2 would require a compact template-to-BA2 address map, boundary exceptions, probability classes, logical attachments, and deterministic edge ordering.

Until such a generator is demonstrated to reproduce all 391,320 BA2 incidences and access groups exactly, full QC/template compression is speculative. No structured-generation saving is included in the selected estimates.

The next safe QC experiment is offline: infer templates, emit the complete BA2-ordered CSR from them, and require byte-exact equality with current memory images before estimating generator hardware.

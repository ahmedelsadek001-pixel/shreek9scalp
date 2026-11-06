# V6 Evidence Policy

V5.1 release certification remains compatible with its ten release controls. V6 adds broker validation and operator approval as separate release controls. Both must be provenance-backed before V6 live authorization can be considered.

`evaluate_v6_release` additionally requires the exact normalized 40-character
release candidate commit SHA. Evidence from a different commit, an omitted
candidate or malformed candidate is rejected even if all flags are positive.
The candidate binding does not independently authenticate a source string or
operator signature; those still need external verification before any positive
broker validation or approval record is issued.

"""Bounded, identity-free projection of experimental strategy observations."""

REASONS = frozenset({
    "insufficient_history", "consolidation_range", "breakout_body",
    "breakout_tick_volume", "no_close_outside_range",
    "retest_window_before_evaluation", "retest_did_not_touch_level",
    "no_pin_or_engulfing_confirmation", "first_confirmation_before_evaluation",
})
SCHEMA = "shreek.strategy-diagnostics.v1"


def bounded_diagnostics(value: dict) -> dict:
    """Persist only known counters, never arbitrary payloads or credentials."""
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise ValueError("invalid strategy diagnostic schema")
    result = {"schema": SCHEMA}
    for key in ("candidates", "valid_breakouts", "returned_signals"):
        count = value.get(key)
        if type(count) is not int or not 0 <= count <= 10000:
            raise ValueError("invalid strategy diagnostic counter")
        result[key] = count
    rejected = value.get("rejected")
    if not isinstance(rejected, dict) or not set(rejected) <= REASONS:
        raise ValueError("invalid strategy diagnostic reasons")
    if any(type(count) is not int or not 0 <= count <= 10000 for count in rejected.values()):
        raise ValueError("invalid strategy rejection counter")
    if not result["returned_signals"] <= result["valid_breakouts"] <= result["candidates"]:
        raise ValueError("inconsistent strategy diagnostic counters")
    result["rejected"] = dict(rejected)
    return result

"""Deterministic ICT setup-quality scoring with fail-closed validation."""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Tuple


@dataclass(frozen=True)
class SetupQualityInput:
    htf_structure: bool = False
    liquidity_sweep: bool = False
    fvg: bool = False
    order_block: bool = False
    m15_confirmation: bool = False
    m5_confirmation: bool = False
    m3_confirmation: bool = False
    rr_valid: bool = False
    session_valid: bool = False


@dataclass(frozen=True)
class SetupQuality:
    score: int
    grade: str
    tradable: bool


_WEIGHTS: Tuple[Tuple[str, int], ...] = (
    ("htf_structure", 20),
    ("liquidity_sweep", 15),
    ("fvg", 15),
    ("order_block", 10),
    ("m15_confirmation", 15),
    ("m5_confirmation", 10),
    ("m3_confirmation", 5),
    ("rr_valid", 5),
    ("session_valid", 5),
)


def score_setup(setup: SetupQualityInput) -> SetupQuality:
    """Score one setup; invalid input is rejected rather than coerced."""
    if not isinstance(setup, SetupQualityInput):
        raise TypeError("setup must be SetupQualityInput")
    expected = {field.name for field in fields(SetupQualityInput)}
    if expected != {name for name, _ in _WEIGHTS}:
        raise RuntimeError("setup-quality weights do not match input schema")
    for name in expected:
        if type(getattr(setup, name)) is not bool:
            raise TypeError("setup-quality factors must be booleans")
    score = sum(weight for name, weight in _WEIGHTS if getattr(setup, name))
    if score < 60:
        grade = "BLOCKED"
    elif score < 70:
        grade = "WEAK"
    elif score < 80:
        grade = "VALID"
    elif score < 90:
        grade = "HIGH"
    else:
        grade = "A+"
    return SetupQuality(score=score, grade=grade, tradable=score >= 60)

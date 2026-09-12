"""Deterministic 0-100 setup-quality scoring for admission research."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


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


_WEIGHTS = (
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


def score_setup(values: SetupQualityInput) -> SetupQuality:
    if not isinstance(values, SetupQualityInput):
        raise TypeError("values must be SetupQualityInput")
    score = sum(weight for name, weight in _WEIGHTS if getattr(values, name))
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
    return SetupQuality(score, grade, score >= 60)

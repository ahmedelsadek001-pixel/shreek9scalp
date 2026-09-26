"""Regression tests for strict numeric validation in robustness evidence."""

import pytest

from research.robustness import _is_finite_real


@pytest.mark.parametrize("value", [True, False, "1", b"1", None, object()])
def test_is_finite_real_rejects_booleans_and_coercions(value):
    assert not _is_finite_real(value)


@pytest.mark.parametrize("value", [0, 1, -1, 0.25, -3.5])
def test_is_finite_real_accepts_finite_ints_and_floats(value):
    assert _is_finite_real(value)


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf"), 10**10000],
    ids=["nan", "positive_inf", "negative_inf", "huge_int"],
)
def test_is_finite_real_rejects_non_finite_or_overflowing_values(value):
    assert not _is_finite_real(value)

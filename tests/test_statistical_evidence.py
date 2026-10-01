import pytest

from core.statistical_evidence import confidence_excludes_zero, mean_confidence_interval


def test_positive_sample_interval_excludes_zero():
    interval = mean_confidence_interval([2.0, 2.1, 1.9, 2.2, 1.8])
    assert interval.samples == 5
    assert interval.mean == pytest.approx(2.0)
    assert interval.lower > 0.0
    assert confidence_excludes_zero(interval) is True


def test_mixed_sample_interval_does_not_exclude_zero():
    interval = mean_confidence_interval([-2.0, -1.0, 0.0, 1.0, 2.0])
    assert interval.lower < 0.0 < interval.upper
    assert confidence_excludes_zero(interval) is False


@pytest.mark.parametrize("values", [[], [1.0], [1.0, float("nan")], [1.0, float("inf")], [1.0, True]])
def test_invalid_pnl_fails_closed(values):
    with pytest.raises(ValueError):
        mean_confidence_interval(values)


@pytest.mark.parametrize("confidence", [0.0, 1.0, -0.1, 1.1, True, float("nan")])
def test_invalid_confidence_fails_closed(confidence):
    with pytest.raises(ValueError):
        mean_confidence_interval([1.0, 2.0], confidence)


def test_interval_type_validation_fails_closed():
    with pytest.raises(ValueError):
        confidence_excludes_zero(object())

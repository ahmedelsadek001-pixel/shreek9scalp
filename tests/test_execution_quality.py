import pytest

from research.execution_quality import analyze_execution_quality


def test_execution_quality_metrics():
    report = analyze_execution_quality([100, 101, 102], [100.2, 100.8, 102.5], [0.4, 0.2, 0.6])
    assert report.samples == 3
    assert report.mean_slippage == pytest.approx((0.2 - 0.2 + 0.5) / 3)
    assert report.median_slippage == pytest.approx(0.2)
    assert report.max_abs_slippage == pytest.approx(0.5)
    assert report.max_spread == pytest.approx(0.6)


def test_execution_quality_rejects_misaligned_data():
    with pytest.raises(ValueError):
        analyze_execution_quality([100], [100, 101])

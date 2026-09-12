from core.walk_forward import WalkForwardResult, WalkForwardSummary, WalkForwardWindow
from research.advanced_wfo import analyze_wfo_stability


def test_wfo_stability_report():
    summary = WalkForwardSummary(
        windows=(
            WalkForwardResult(WalkForwardWindow(0, 10, 10, 15), {"a": 1}, 2.0, 1.0),
            WalkForwardResult(WalkForwardWindow(5, 15, 15, 20), {"a": 2}, 2.0, -0.5),
            WalkForwardResult(WalkForwardWindow(10, 20, 20, 25), {"a": 2}, 2.0, 0.5),
        ),
        aggregate_test_score=1.0 / 3.0,
        median_test_score=0.5,
        positive_test_windows=2,
        stability_pct=66.6666667,
    )
    report = analyze_wfo_stability(summary)
    assert report.windows == 3
    assert report.positive_windows_pct == 66.66666666666666
    assert report.parameter_switches == 1
    assert report.stable is True

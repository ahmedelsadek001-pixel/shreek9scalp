from core.robustness import RobustnessPolicy, build_robustness_report
from core.walk_forward import WalkForwardSummary


def test_robustness_report_passes_clean_inputs():
    wfo = WalkForwardSummary((), 1.0, 1.0, 1, 100.0)
    report = build_robustness_report(wfo, [10.0, -2.0, 8.0], simulations=50, seed=7)
    assert report.passed
    assert report.failures == ()


def test_robustness_report_rejects_low_wfo_stability():
    wfo = WalkForwardSummary((), -1.0, -1.0, 1, 50.0)
    policy = RobustnessPolicy(min_wfo_stability_pct=60.0)
    report = build_robustness_report(wfo, [10.0, -2.0], simulations=20, seed=7, policy=policy)
    assert not report.passed
    assert "WFO stability below minimum" in report.failures


def test_policy_rejects_invalid_thresholds():
    try:
        RobustnessPolicy(min_wfo_stability_pct=101).validate()
    except ValueError:
        pass
    else:
        raise AssertionError("expected invalid WFO threshold")

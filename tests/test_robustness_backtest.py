from core.robustness import build_backtest_robustness_report
from core.walk_forward import WalkForwardSummary


def _wfo(stability=100.0):
    return WalkForwardSummary((), 1.0, 1.0, 1, stability)


def _result_with_pnl(pnl):
    class Trade:
        def __init__(self, value):
            self.net_pnl = value

    return type("Result", (), {"trades": tuple(Trade(x) for x in pnl)})()


def test_backtest_adapter_extracts_trade_pnl_and_runs_robustness():
    report = build_backtest_robustness_report(_wfo(), _result_with_pnl([10.0, -5.0, 7.0]), simulations=50)
    assert report.passed
    assert report.monte_carlo.simulations == 50


def test_backtest_adapter_rejects_empty_trade_set():
    try:
        build_backtest_robustness_report(_wfo(), _result_with_pnl([]), simulations=10)
    except ValueError as exc:
        assert "pnl" in str(exc)
    else:
        raise AssertionError("empty trade results must fail closed")

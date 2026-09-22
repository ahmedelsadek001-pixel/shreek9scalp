from dataclasses import replace
from datetime import datetime

import pytest

from core.backtest_engine import BacktestResult, BacktestStats, BacktestTrade
from core.block_bootstrap import moving_block_bootstrap
from core.enums import Direction
from core.research_certification import ResearchCertificationPolicy, certify_research
from core.statistical_evidence import mean_confidence_interval
from research.backtest_wfo import BacktestWFOResult
from research.purged_wfo import PurgedWFOResult, PurgedWindow
from research.robustness import run_oos_monte_carlo
from core.research_metrics import calculate_research_metrics


def _result(pnl):
    now = datetime(2026, 1, 1)
    trades = tuple(BacktestTrade(now, now, now, Direction.BUY, 100, 101, 1, v, 0, v, "TP") for v in pnl)
    equity = [10000.0]
    for v in pnl: equity.append(equity[-1] + v)
    wins=sum(v>0 for v in pnl); losses=sum(v<0 for v in pnl); gp=sum(v for v in pnl if v>0); gl=-sum(v for v in pnl if v<0)
    stats=BacktestStats(10000.0,equity[-1],sum(pnl),sum(pnl)/100.0,len(pnl),wins,losses,gp,gp/gl if gl else float("inf"),sum(pnl)/len(pnl),gl,gl/100.0,0.0)
    return BacktestResult(trades,tuple(equity),stats)


def _wfo():
    rows=tuple(_result([2.0,2.0,2.0,2.0]) for _ in range(3))
    metrics=tuple(calculate_research_metrics(r) for r in rows)
    validation=PurgedWFOResult(
        (PurgedWindow(0,4,4,4,4,8),PurgedWindow(8,12,12,12,12,16),PurgedWindow(16,20,20,20,20,24)),
        (2.0,2.0,2.0),(2.0,2.0,2.0),({"x":1},{"x":1},{"x":1}))
    return BacktestWFOResult(validation,metrics,metrics,rows)


def test_certification_passes_consistent_strong_oos_evidence():
    wfo=_wfo(); pnl=wfo.oos_trade_pnl
    interval=mean_confidence_interval(pnl)
    bootstrap=moving_block_bootstrap(pnl,block_size=2,simulations=100,seed=7)
    robustness=run_oos_monte_carlo(wfo,starting_equity=10000,simulations=50,seed=7)
    policy=ResearchCertificationPolicy(min_oos_trades=10,min_oos_windows=3)
    result=certify_research(wfo,interval,bootstrap,robustness,policy)
    assert result.passed
    assert result.failures == ()


def test_certification_fails_closed_on_sample_mismatch():
    wfo=_wfo(); pnl=wfo.oos_trade_pnl
    interval=mean_confidence_interval(pnl[:-1])
    bootstrap=moving_block_bootstrap(pnl,block_size=2,simulations=50,seed=7)
    robustness=run_oos_monte_carlo(wfo,starting_equity=10000,simulations=20,seed=7)
    with pytest.raises(ValueError,match="sample count"):
        certify_research(wfo,interval,bootstrap,robustness,ResearchCertificationPolicy(min_oos_trades=2))


def test_certification_rejects_tampered_robustness_linkage():
    wfo=_wfo(); pnl=wfo.oos_trade_pnl
    interval=mean_confidence_interval(pnl)
    bootstrap=moving_block_bootstrap(pnl,block_size=2,simulations=50,seed=7)
    robustness=run_oos_monte_carlo(wfo,starting_equity=10000,simulations=20,seed=7)
    tampered=replace(robustness,oos_trade_pnl=robustness.oos_trade_pnl[:-1]+(99.0,))
    with pytest.raises(ValueError):
        certify_research(wfo,interval,bootstrap,tampered,ResearchCertificationPolicy(min_oos_trades=2))


def test_certification_rejects_inconsistent_wfo_cardinality():
    wfo=_wfo(); pnl=wfo.oos_trade_pnl
    interval=mean_confidence_interval(pnl)
    bootstrap=moving_block_bootstrap(pnl,block_size=2,simulations=50,seed=7)
    robustness=run_oos_monte_carlo(wfo,starting_equity=10000,simulations=20,seed=7)
    tampered=replace(wfo,oos_results=wfo.oos_results[:-1])
    with pytest.raises(ValueError,match="cardinality"):
        certify_research(tampered,interval,bootstrap,robustness,ResearchCertificationPolicy(min_oos_trades=2))


def test_certification_rejects_oos_metric_result_mismatch():
    wfo=_wfo(); pnl=wfo.oos_trade_pnl
    interval=mean_confidence_interval(pnl)
    bootstrap=moving_block_bootstrap(pnl,block_size=2,simulations=50,seed=7)
    robustness=run_oos_monte_carlo(wfo,starting_equity=10000,simulations=20,seed=7)
    altered=replace(wfo.oos_metrics[0],net_pnl=wfo.oos_metrics[0].net_pnl + 1.0)
    tampered=replace(wfo,oos_metrics=(altered,) + wfo.oos_metrics[1:])
    with pytest.raises(ValueError,match="do not match"):
        certify_research(tampered,interval,bootstrap,robustness,ResearchCertificationPolicy(min_oos_trades=2))


def test_certification_blocks_excessive_is_to_oos_expectancy_degradation():
    wfo = _wfo()
    stronger_train = tuple(replace(metric, expectancy=10.0) for metric in wfo.train_metrics)
    degraded = replace(wfo, train_metrics=stronger_train)
    pnl = degraded.oos_trade_pnl
    interval = mean_confidence_interval(pnl)
    bootstrap = moving_block_bootstrap(pnl, block_size=2, simulations=100, seed=7)
    robustness = run_oos_monte_carlo(degraded, starting_equity=10000, simulations=50, seed=7)
    policy = ResearchCertificationPolicy(
        min_oos_trades=10,
        min_oos_windows=3,
        max_oos_expectancy_degradation_pct=50.0,
    )
    result = certify_research(degraded, interval, bootstrap, robustness, policy)
    assert not result.passed
    assert "OOS expectancy degradation above maximum" in result.failures


def test_certification_blocks_unstable_selected_parameters():
    wfo = _wfo()
    unstable_validation = replace(
        wfo.validation,
        selected_parameters=({"x": 1}, {"x": 2}, {"x": 3}),
    )
    unstable = replace(wfo, validation=unstable_validation)
    pnl = unstable.oos_trade_pnl
    interval = mean_confidence_interval(pnl)
    bootstrap = moving_block_bootstrap(pnl, block_size=2, simulations=100, seed=7)
    robustness = run_oos_monte_carlo(unstable, starting_equity=10000, simulations=50, seed=7)
    policy = ResearchCertificationPolicy(
        min_oos_trades=10,
        min_oos_windows=3,
        min_parameter_stability_pct=50.0,
    )
    result = certify_research(unstable, interval, bootstrap, robustness, policy)
    assert not result.passed
    assert "parameter stability below minimum" in result.failures


@pytest.mark.parametrize("field", [
    "max_oos_expectancy_degradation_pct",
    "min_parameter_stability_pct",
])
def test_certification_policy_rejects_invalid_new_thresholds(field):
    with pytest.raises(ValueError):
        replace(ResearchCertificationPolicy(), **{field: float("nan")}).validate()

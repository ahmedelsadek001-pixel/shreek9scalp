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
        (PurgedWindow(0,4,4,8),PurgedWindow(8,12,12,16),PurgedWindow(16,20,20,24)),
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

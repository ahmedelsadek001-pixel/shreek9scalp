"""Structured, backtest-derived evidence reporting for SHREEK V5.2."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from research.backtest_wfo import BacktestWFOResult
from research.robustness import RobustnessEvidence


@dataclass(frozen=True)
class OOSEvidenceReport:
    """Immutable summary of realized OOS performance and robustness evidence."""

    oos_trade_count: int
    oos_net_pnl: float
    oos_expectancy: float
    oos_stability_pct: float
    positive_oos_windows: int
    oos_window_count: int
    ruin_rate_pct: float
    median_ending_equity: float
    worst_ending_equity: float
    median_max_drawdown: float
    worst_max_drawdown: float
    simulations: int

    def validate(self) -> None:
        """Fail closed if report fields are non-finite or structurally invalid."""
        integers = (
            self.oos_trade_count,
            self.positive_oos_windows,
            self.oos_window_count,
            self.simulations,
        )
        if any(type(value) is not int or value < 0 for value in integers):
            raise ValueError("report counts must be non-negative integers")
        if self.oos_trade_count == 0 or self.oos_window_count == 0 or self.simulations == 0:
            raise ValueError("report requires OOS trades, windows, and simulations")
        if self.positive_oos_windows > self.oos_window_count:
            raise ValueError("positive OOS windows cannot exceed OOS window count")
        numeric = (
            self.oos_net_pnl,
            self.oos_expectancy,
            self.oos_stability_pct,
            self.ruin_rate_pct,
            self.median_ending_equity,
            self.worst_ending_equity,
            self.median_max_drawdown,
            self.worst_max_drawdown,
        )
        if any(not isfinite(float(value)) for value in numeric):
            raise ValueError("report metrics must be finite")
        if not 0.0 <= self.oos_stability_pct <= 100.0:
            raise ValueError("OOS stability must be between 0 and 100")
        if not 0.0 <= self.ruin_rate_pct <= 100.0:
            raise ValueError("ruin rate must be between 0 and 100")


def build_oos_evidence_report(
    wfo: BacktestWFOResult,
    robustness: RobustnessEvidence,
) -> OOSEvidenceReport:
    """Build a report exclusively from realized WFO OOS and Monte Carlo evidence."""
    if not isinstance(wfo, BacktestWFOResult):
        raise ValueError("wfo must be a BacktestWFOResult")
    if not isinstance(robustness, RobustnessEvidence):
        raise ValueError("robustness must be RobustnessEvidence")
    report = OOSEvidenceReport(
        oos_trade_count=robustness.oos_trade_count,
        oos_net_pnl=wfo.oos_net_pnl,
        oos_expectancy=wfo.oos_expectancy,
        oos_stability_pct=wfo.oos_stability_pct,
        positive_oos_windows=wfo.positive_oos_windows,
        oos_window_count=len(wfo.oos_metrics),
        ruin_rate_pct=robustness.summary.ruin_rate_pct,
        median_ending_equity=robustness.summary.median_ending_equity,
        worst_ending_equity=robustness.summary.worst_ending_equity,
        median_max_drawdown=robustness.summary.median_max_drawdown,
        worst_max_drawdown=robustness.summary.worst_max_drawdown,
        simulations=robustness.summary.simulations,
    )
    report.validate()
    return report

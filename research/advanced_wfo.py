"""Research-only stability analytics layered on causal walk-forward results."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from core.walk_forward import WalkForwardSummary


@dataclass(frozen=True)
class WFOStabilityReport:
    windows: int
    positive_windows_pct: float
    median_test_score: float
    worst_test_score: float
    best_test_score: float
    parameter_switches: int
    stable: bool


def analyze_wfo_stability(
    summary: WalkForwardSummary,
    *,
    min_positive_windows_pct: float = 60.0,
    min_median_test_score: float = 0.0,
) -> WFOStabilityReport:
    """Measure OOS stability and parameter churn without changing selection."""
    if not 0 <= min_positive_windows_pct <= 100:
        raise ValueError("min_positive_windows_pct must be between 0 and 100")
    if not summary.windows:
        raise ValueError("WFO summary must contain windows")
    scores = [float(result.test_score) for result in summary.windows]
    switches = sum(
        1
        for previous, current in zip(summary.windows, summary.windows[1:])
        if dict(previous.parameters) != dict(current.parameters)
    )
    positive_pct = sum(score > 0 for score in scores) / len(scores) * 100.0
    median_score = median(scores)
    stable = positive_pct >= min_positive_windows_pct and median_score >= min_median_test_score
    return WFOStabilityReport(
        len(scores), positive_pct, median_score, min(scores), max(scores), switches, stable
    )

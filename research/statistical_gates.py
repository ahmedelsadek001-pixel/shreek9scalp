"""Fail-closed statistical gate for SHREEK V5.2 research candidates."""
from __future__ import annotations

from dataclasses import dataclass

from research.bootstrap_validation import BootstrapReport
from research.edge_matrix import EdgeCell


@dataclass(frozen=True)
class StatisticalGatePolicy:
    min_samples: int = 30
    min_positive_expectancy_probability: float = 0.95
    require_positive_ci_lower: bool = False

    def validate(self) -> None:
        if self.min_samples < 1:
            raise ValueError("min_samples must be positive")
        if not 0.0 <= self.min_positive_expectancy_probability <= 1.0:
            raise ValueError("probability threshold must be between 0 and 1")
        if type(self.require_positive_ci_lower) is not bool:
            raise ValueError("require_positive_ci_lower must be boolean")


@dataclass(frozen=True)
class StatisticalGateResult:
    passed: bool
    reasons: tuple[str, ...]


def evaluate_statistical_gate(
    cell: EdgeCell,
    bootstrap: BootstrapReport,
    policy: StatisticalGatePolicy = StatisticalGatePolicy(),
) -> StatisticalGateResult:
    """Evaluate evidence quality without authorizing execution."""
    policy.validate()
    if not isinstance(cell, EdgeCell):
        raise TypeError("cell must be EdgeCell")
    if not isinstance(bootstrap, BootstrapReport):
        raise TypeError("bootstrap must be BootstrapReport")
    reasons: list[str] = []
    if cell.trades < policy.min_samples:
        reasons.append("sample count below minimum")
    if bootstrap.samples != cell.trades:
        reasons.append("bootstrap sample count does not match edge cell")
    if bootstrap.positive_expectancy_probability < policy.min_positive_expectancy_probability:
        reasons.append("bootstrap positive-expectancy probability below minimum")
    if policy.require_positive_ci_lower and bootstrap.lower_ci <= 0:
        reasons.append("bootstrap confidence interval includes non-positive expectancy")
    if cell.expectancy <= 0:
        reasons.append("observed expectancy is not positive")
    return StatisticalGateResult(not reasons, tuple(reasons))

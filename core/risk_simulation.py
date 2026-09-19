"""Deterministic risk and robustness simulation helpers."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import random
from typing import Optional, Sequence


def _is_number(value: object) -> bool:
    """Return whether value is an actual finite int/float, excluding bool."""
    if type(value) not in (int, float):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        # ``math.isfinite`` converts integers to float; enormous integers can
        # overflow during that conversion and must fail validation cleanly.
        return False


@dataclass(frozen=True)
class SimulationResult:
    pnl: tuple[float, ...]
    ending_equity: float
    max_drawdown: float
    max_drawdown_pct: float
    ruin: bool


@dataclass(frozen=True)
class RobustnessSummary:
    simulations: int
    ruin_rate_pct: float
    median_ending_equity: float
    worst_ending_equity: float
    median_max_drawdown: float
    worst_max_drawdown: float
    p05_ending_equity: float
    p95_max_drawdown: float


def _validate(pnl: Sequence[float], starting_equity: float, simulations: int) -> None:
    if not _is_number(starting_equity) or starting_equity <= 0:
        raise ValueError("starting equity must be positive and finite")
    if not pnl or any(not _is_number(x) for x in pnl):
        raise ValueError("pnl must be non-empty and finite numeric values")
    if type(simulations) is not int or simulations <= 0:
        raise ValueError("simulations must be a positive integer")


def _validate_seed(seed: Optional[int]) -> None:
    if seed is not None and type(seed) is not int:
        raise ValueError("seed must be an integer or None")


def _validate_cost_multipliers(slippage_multiplier: float, spread_multiplier: float) -> None:
    if (
        not _is_number(slippage_multiplier)
        or not _is_number(spread_multiplier)
        or slippage_multiplier < 1
        or spread_multiplier < 1
    ):
        raise ValueError("cost multipliers must be finite and >= 1")
    if not isfinite(slippage_multiplier * spread_multiplier):
        raise ValueError("combined cost multiplier must be finite")


def _validate_sorted_sample(values: Sequence[float]) -> None:
    if not values:
        raise ValueError("sample must be non-empty")
    if any(not _is_number(value) for value in values):
        raise ValueError("sample values must be finite numbers")
    if any(left > right for left, right in zip(values, values[1:])):
        raise ValueError("sample values must be sorted")


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    """Linearly interpolate a quantile from an already sorted finite sample."""
    _validate_sorted_sample(sorted_values)
    if not _is_number(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("quantile probability must be finite and between 0 and 1")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    index = probability * (len(sorted_values) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    value = float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)
    if not isfinite(value):
        raise ValueError("quantile result must remain finite")
    return value


def _median(sorted_values: Sequence[float]) -> float:
    """Return a finite median without overflowing an intermediate sum."""
    _validate_sorted_sample(sorted_values)
    middle = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return float(sorted_values[middle])
    value = float(sorted_values[middle - 1] / 2.0 + sorted_values[middle] / 2.0)
    if not isfinite(value):
        raise ValueError("median result must remain finite")
    return value


def simulate_sequence(
    pnl: Sequence[float],
    starting_equity: float = 10000.0,
    seed: Optional[int] = None,
    slippage_multiplier: float = 1.0,
    spread_multiplier: float = 1.0,
) -> SimulationResult:
    """Bootstrap trade outcomes and apply conservative cost stress.

    Ruin is a path event: once equity reaches zero or below, the simulation
    stops and remains ruined rather than allowing later synthetic profits to
    recover the account.
    """
    _validate(pnl, starting_equity, 1)
    _validate_seed(seed)
    _validate_cost_multipliers(slippage_multiplier, spread_multiplier)
    rng = random.Random(seed)
    sampled = [rng.choice(list(pnl)) for _ in pnl]
    multiplier = 1.0 / (slippage_multiplier * spread_multiplier)
    adjusted = []
    equity = starting_equity
    peak = equity
    max_dd = 0.0
    ruined = False

    for x in sampled:
        stressed = x * multiplier if x >= 0 else x * slippage_multiplier * spread_multiplier
        if not isfinite(stressed):
            raise ValueError("stressed trade P&L must remain finite")
        adjusted.append(stressed)
        equity += stressed
        if not isfinite(equity):
            raise ValueError("simulated equity must remain finite")
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        if not isfinite(max_dd):
            raise ValueError("simulated drawdown must remain finite")
        if equity <= 0:
            ruined = True
            break

    drawdown_pct = max_dd / starting_equity * 100.0
    if not isfinite(drawdown_pct):
        raise ValueError("simulated drawdown percentage must remain finite")
    realized = tuple(adjusted)
    return SimulationResult(realized, equity, max_dd, drawdown_pct, ruined)


def monte_carlo(
    pnl: Sequence[float],
    starting_equity: float = 10000.0,
    simulations: int = 1000,
    seed: Optional[int] = 42,
    slippage_multiplier: float = 1.0,
    spread_multiplier: float = 1.0,
) -> RobustnessSummary:
    """Run reproducible bootstrap stress tests and summarize tail risk."""
    _validate(pnl, starting_equity, simulations)
    _validate_seed(seed)
    _validate_cost_multipliers(slippage_multiplier, spread_multiplier)
    rng = random.Random(seed)
    results = [
        simulate_sequence(
            pnl,
            starting_equity,
            rng.randrange(2**63),
            slippage_multiplier,
            spread_multiplier,
        )
        for _ in range(simulations)
    ]
    endings = sorted(r.ending_equity for r in results)
    dds = sorted(r.max_drawdown for r in results)
    ruin = sum(r.ruin for r in results)
    median_end = _median(endings)
    median_dd = _median(dds)
    summary = RobustnessSummary(
        simulations,
        ruin / simulations * 100.0,
        median_end,
        endings[0],
        median_dd,
        dds[-1],
        _quantile(endings, 0.05),
        _quantile(dds, 0.95),
    )
    if any(not isfinite(float(value)) for value in (
        summary.ruin_rate_pct, summary.median_ending_equity,
        summary.worst_ending_equity, summary.median_max_drawdown,
        summary.worst_max_drawdown, summary.p05_ending_equity,
        summary.p95_max_drawdown,
    )):
        raise ValueError("Monte Carlo summary metrics must remain finite")
    return summary

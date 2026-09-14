"""Deterministic risk and robustness simulation helpers."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import random
from typing import Optional, Sequence


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


def _validate(pnl: Sequence[float], starting_equity: float, simulations: int) -> None:
    if not isfinite(starting_equity) or starting_equity <= 0:
        raise ValueError("starting equity must be positive and finite")
    if not pnl or any(not isfinite(float(x)) for x in pnl):
        raise ValueError("pnl must be non-empty and finite")
    if type(simulations) is not int or simulations <= 0:
        raise ValueError("simulations must be a positive integer")


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
    if (
        not isfinite(slippage_multiplier)
        or not isfinite(spread_multiplier)
        or slippage_multiplier < 1
        or spread_multiplier < 1
    ):
        raise ValueError("cost multipliers must be finite and >= 1")
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
        adjusted.append(stressed)
        equity += stressed
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        if equity <= 0:
            ruined = True
            break

    realized = tuple(adjusted)
    return SimulationResult(
        realized,
        equity,
        max_dd,
        max_dd / starting_equity * 100.0,
        ruined,
    )


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
    mid = simulations // 2
    median_end = endings[mid] if simulations % 2 else (endings[mid - 1] + endings[mid]) / 2
    median_dd = dds[mid] if simulations % 2 else (dds[mid - 1] + dds[mid]) / 2
    return RobustnessSummary(
        simulations,
        ruin / simulations * 100.0,
        median_end,
        endings[0],
        median_dd,
        dds[-1],
    )

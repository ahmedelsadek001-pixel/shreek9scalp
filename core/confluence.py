"""Deterministic confluence engine for SHREEK V5.1.

A score is evidence, not authorization. The engine fails closed on HTF
conflict and only emits BUY/SELL when the requested minimum evidence exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import constants as C
from config.settings import Settings
from core.enums import Direction, StructureEvent, Timeframe
from core.models import ConfluenceCriterion, ConfluenceResult, MarketStructure, TradeSignal


@dataclass(frozen=True)
class ConfluenceDecision:
    direction: Direction
    result: ConfluenceResult
    tradable: bool
    reason: str


def _same_direction(a: Direction, b: Direction) -> bool:
    return a in (Direction.BUY, Direction.SELL) and a == b


def _event_matches(structure: Optional[MarketStructure], direction: Direction) -> bool:
    if structure is None:
        return False
    bullish = structure.event in (StructureEvent.BOS_BULLISH, StructureEvent.CHOCH_BULLISH)
    bearish = structure.event in (StructureEvent.BOS_BEARISH, StructureEvent.CHOCH_BEARISH)
    return bullish if direction == Direction.BUY else bearish if direction == Direction.SELL else False


def evaluate_confluence(
    direction: Direction,
    d1: Optional[MarketStructure],
    h4: Optional[MarketStructure],
    h1: Optional[MarketStructure],
    m15: Optional[MarketStructure],
    signal: Optional[TradeSignal],
    in_pd_zone: bool = False,
    killzone_active: bool = False,
    draw_on_liquidity: bool = False,
    settings: Optional[Settings] = None,
) -> ConfluenceDecision:
    """Evaluate strategy evidence without placing or authorizing broker orders."""
    settings = settings or Settings()
    criteria: list[ConfluenceCriterion] = []

    if direction not in (Direction.BUY, Direction.SELL):
        return ConfluenceDecision(direction, ConfluenceResult([], 0, 0), False, "Invalid trade direction")

    htf_aligned = all(_same_direction(x.bias, direction) for x in (d1, h4))
    criteria.append(ConfluenceCriterion("HTF alignment", 2 if htf_aligned else 0, C.PTS_HTF_ALIGNMENT))
    if not htf_aligned:
        result = ConfluenceResult(criteria, sum(c.points for c in criteria), sum(c.max_points for c in criteria))
        return ConfluenceDecision(direction, result, False, "HTF conflict or missing D1/H4 alignment")

    criteria.append(ConfluenceCriterion("PD Array zone", C.PTS_PD_ARRAY_ZONE if in_pd_zone else 0, C.PTS_PD_ARRAY_ZONE))
    criteria.append(ConfluenceCriterion("H1 structural event", C.PTS_H1_STRUCTURAL_EVENT if _event_matches(h1, direction) else 0, C.PTS_H1_STRUCTURAL_EVENT))
    criteria.append(ConfluenceCriterion("M15 BOS/CHOCH", C.PTS_M15_BOS_CHOCH if _event_matches(m15, direction) else 0, C.PTS_M15_BOS_CHOCH))

    if signal is not None:
        criteria.append(ConfluenceCriterion("M15 candle confirmation", C.PTS_M15_CANDLE_CONFIRMATION if signal.candle_confirmation else 0, C.PTS_M15_CANDLE_CONFIRMATION))
        criteria.append(ConfluenceCriterion("Liquidity sweep", C.PTS_M15_LIQUIDITY_SWEEP if signal.sweep_confirmed else 0, C.PTS_M15_LIQUIDITY_SWEEP))
        setup_points = C.PTS_M15_ENTRY_SETUP if signal.setup_type.value == "COMBINED" else 1 if signal.setup_type.value in {"OB_ENTRY", "FVG_ENTRY"} else 0
        criteria.append(ConfluenceCriterion("M15 entry setup", setup_points, C.PTS_M15_ENTRY_SETUP))
        overlap = signal.order_block is not None and signal.fvg is not None
        if overlap and signal.setup_type.value != "COMBINED":
            criteria.append(ConfluenceCriterion("FVG/OB overlap", C.PTS_FVG_OB_OVERLAP, C.PTS_FVG_OB_OVERLAP))
        criteria.append(ConfluenceCriterion("Execution frame", C.PTS_EXECUTION_FRAME if signal.is_valid else 0, C.PTS_EXECUTION_FRAME))
        criteria.append(ConfluenceCriterion("FVG failure", C.PTS_FVG_FAILURE_BONUS if signal.fvg_failure else 0, C.PTS_FVG_FAILURE_BONUS))
    else:
        for name, maximum in (("M15 candle confirmation", C.PTS_M15_CANDLE_CONFIRMATION), ("Liquidity sweep", C.PTS_M15_LIQUIDITY_SWEEP), ("M15 entry setup", C.PTS_M15_ENTRY_SETUP), ("Execution frame", C.PTS_EXECUTION_FRAME), ("FVG failure", C.PTS_FVG_FAILURE_BONUS)):
            criteria.append(ConfluenceCriterion(name, 0, maximum))

    criteria.append(ConfluenceCriterion("Killzone", C.PTS_KILLZONE_ACTIVE if killzone_active else 0, C.PTS_KILLZONE_ACTIVE))
    criteria.append(ConfluenceCriterion("Draw on liquidity", C.PTS_DRAW_ON_LIQUIDITY if draw_on_liquidity else 0, C.PTS_DRAW_ON_LIQUIDITY))
    result = ConfluenceResult(criteria, sum(c.points for c in criteria), sum(c.max_points for c in criteria))

    if signal is None or not signal.is_valid:
        return ConfluenceDecision(direction, result, False, "No valid execution signal")
    if result.score < settings.confluence_threshold:
        return ConfluenceDecision(direction, result, False, f"Confluence score {result.score} below threshold {settings.confluence_threshold}")
    return ConfluenceDecision(direction, result, True, "Confluence passed; downstream risk gates still required")

"""Deterministic confluence engine for SHREEK V5.1.

A score is evidence, not authorization. The engine fails closed on HTF
conflict and only emits BUY/SELL when the requested minimum evidence exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config import constants as C
from config.settings import Settings
from core.enums import Direction, SetupType, StructureEvent
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


def _criterion(name: str, points: int, maximum: int, reason: str) -> ConfluenceCriterion:
    return ConfluenceCriterion(name, points, maximum, reason)


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
    settings = settings or Settings()
    criteria: list[ConfluenceCriterion] = []
    if direction not in (Direction.BUY, Direction.SELL):
        return ConfluenceDecision(direction, ConfluenceResult([], 0, 0), False, "Invalid trade direction")

    htf_aligned = all(_same_direction(x.bias, direction) for x in (d1, h4))
    criteria.append(_criterion("HTF alignment", C.PTS_HTF_ALIGNMENT if htf_aligned else 0, C.PTS_HTF_ALIGNMENT,
                               "D1 and H4 agree" if htf_aligned else "D1/H4 conflict or missing"))
    if not htf_aligned:
        result = ConfluenceResult(criteria, sum(c.points for c in criteria), sum(c.max_points for c in criteria))
        return ConfluenceDecision(direction, result, False, "HTF conflict or missing D1/H4 alignment")

    criteria.append(_criterion("PD Array zone", C.PTS_PD_ARRAY_ZONE if in_pd_zone else 0, C.PTS_PD_ARRAY_ZONE,
                               "Price is inside PD Array zone" if in_pd_zone else "Price is outside PD Array zone"))
    criteria.append(_criterion("H1 structural event", C.PTS_H1_STRUCTURAL_EVENT if _event_matches(h1, direction) else 0,
                               C.PTS_H1_STRUCTURAL_EVENT, "H1 event matches direction" if _event_matches(h1, direction) else "No matching H1 event"))
    criteria.append(_criterion("M15 BOS/CHOCH", C.PTS_M15_BOS_CHOCH if _event_matches(m15, direction) else 0,
                               C.PTS_M15_BOS_CHOCH, "M15 event matches direction" if _event_matches(m15, direction) else "No matching M15 event"))

    if signal is not None:
        criteria.append(_criterion("M15 candle confirmation", C.PTS_M15_CANDLE_CONFIRMATION if signal.candle_confirmation else 0,
                                   C.PTS_M15_CANDLE_CONFIRMATION, "Candle confirms direction" if signal.candle_confirmation else "No candle confirmation"))
        criteria.append(_criterion("Liquidity sweep", C.PTS_M15_LIQUIDITY_SWEEP if signal.sweep_confirmed else 0,
                                   C.PTS_M15_LIQUIDITY_SWEEP, "Liquidity sweep confirmed" if signal.sweep_confirmed else "No liquidity sweep"))
        setup_points = C.PTS_M15_ENTRY_SETUP if signal.setup_type == SetupType.COMBINED else 1 if signal.setup_type in (SetupType.OB_ENTRY, SetupType.FVG_ENTRY) else 0
        criteria.append(_criterion("M15 entry setup", setup_points, C.PTS_M15_ENTRY_SETUP,
                                   f"Setup: {signal.setup_type.value}" if setup_points else "No qualifying entry setup"))
        if signal.order_block is not None and signal.fvg is not None and signal.setup_type != SetupType.COMBINED:
            criteria.append(_criterion("FVG/OB overlap", C.PTS_FVG_OB_OVERLAP, C.PTS_FVG_OB_OVERLAP, "FVG overlaps order block"))
        criteria.append(_criterion("Execution frame", C.PTS_EXECUTION_FRAME if signal.is_valid else 0,
                                   C.PTS_EXECUTION_FRAME, "Valid execution signal" if signal.is_valid else "Invalid execution signal"))
        criteria.append(_criterion("FVG failure", C.PTS_FVG_FAILURE_BONUS if signal.fvg_failure else 0,
                                   C.PTS_FVG_FAILURE_BONUS, "FVG failure confirmed" if signal.fvg_failure else "No FVG failure"))
    else:
        for name, maximum in (("M15 candle confirmation", C.PTS_M15_CANDLE_CONFIRMATION), ("Liquidity sweep", C.PTS_M15_LIQUIDITY_SWEEP),
                              ("M15 entry setup", C.PTS_M15_ENTRY_SETUP), ("Execution frame", C.PTS_EXECUTION_FRAME),
                              ("FVG failure", C.PTS_FVG_FAILURE_BONUS)):
            criteria.append(_criterion(name, 0, maximum, "Missing signal evidence"))

    criteria.append(_criterion("Killzone", C.PTS_KILLZONE_ACTIVE if killzone_active else 0, C.PTS_KILLZONE_ACTIVE,
                               "Killzone active" if killzone_active else "Outside killzone"))
    criteria.append(_criterion("Draw on liquidity", C.PTS_DRAW_ON_LIQUIDITY if draw_on_liquidity else 0, C.PTS_DRAW_ON_LIQUIDITY,
                               "Clear draw on liquidity" if draw_on_liquidity else "No validated draw on liquidity"))
    result = ConfluenceResult(criteria, sum(c.points for c in criteria), sum(c.max_points for c in criteria))
    if signal is None or not signal.is_valid:
        return ConfluenceDecision(direction, result, False, "No valid execution signal")
    if signal.direction != direction:
        return ConfluenceDecision(direction, result, False, "Signal direction conflicts with requested direction")
    if result.score < settings.confluence_threshold:
        return ConfluenceDecision(direction, result, False, f"Confluence score {result.score} below threshold {settings.confluence_threshold}")
    return ConfluenceDecision(direction, result, True, "Confluence passed; downstream risk gates still required")

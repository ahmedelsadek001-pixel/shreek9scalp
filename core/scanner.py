"""Deterministic scanner orchestration for SHREEK V5.1.

The scanner composes analysis modules but never places orders. It evaluates
only closed-candle data, produces a stable signal identity, applies confluence
and risk admission, and returns execution levels only after admission.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from config.settings import Settings
from core.confluence import ConfluenceDecision, evaluate_confluence
from core.enums import Direction, Timeframe
from core.execution_levels import build_execution_levels
from core.models import ExecutionLevels, MarketStructure, TradeSignal
from core.signal_identity import signal_fingerprint
from core.signal_pipeline import AdmissionDecision, admit_signal
from market.entry_signals import (
    analyze_execution_frame,
    analyze_m15_entry_signal,
    select_best_execution_frame,
)
from market.structure import determine_structure
from risk.trade_gates import GateResult


@dataclass(frozen=True)
class ScanDecision:
    symbol: str
    direction: Direction
    signal: Optional[TradeSignal]
    confluence: Optional[ConfluenceDecision]
    admission: AdmissionDecision
    fingerprint: Optional[str]
    execution_levels: Optional[ExecutionLevels] = None


def _closed(data: dict[str, object]) -> dict[str, object]:
    """Defensive copy of already-closed data; never mutate the data source."""
    return {name: frame.copy(deep=True) for name, frame in data.items()}


def _structure(
    data: dict[str, object], name: str, settings: Settings
) -> Optional[MarketStructure]:
    df = data.get(name)
    if df is None or getattr(df, "empty", True):
        return None
    try:
        atr = float(df.iloc[-1]["atr"])
    except (KeyError, TypeError, ValueError):
        return None
    if atr <= 0:
        return None
    frame = Timeframe(name)
    return determine_structure(
        df,
        frame,
        atr=atr,
        threshold_atr=settings.bos_break_threshold_atr,
        confirmation_bars=settings.swing_window.get(name, 5),
    )


def scan_symbol(
    symbol: str,
    data: dict[str, object],
    direction: Direction,
    settings: Optional[Settings] = None,
    gates: tuple[tuple[str, Callable[[], GateResult]], ...] = (),
    in_pd_zone: bool = False,
    killzone_active: bool = False,
    draw_on_liquidity: bool = False,
) -> ScanDecision:
    """Run one closed-bar scan and fail closed on missing evidence.

    The caller supplies authoritative hard gates (spread, news, daily loss,
    cooldown, duplicate identity, etc.). The scanner itself owns no broker I/O.
    """
    settings = settings or Settings()
    closed = _closed(data)
    symbol = symbol.strip().upper()
    if direction not in (Direction.BUY, Direction.SELL):
        return ScanDecision(
            symbol,
            direction,
            None,
            None,
            AdmissionDecision(False, "direction is not executable"),
            None,
        )
    required = {"D1", "H4", "H1", "M15"}
    if not required.issubset(closed):
        return ScanDecision(
            symbol,
            direction,
            None,
            None,
            AdmissionDecision(False, "required timeframe data missing"),
            None,
        )

    d1, h4, h1, m15 = (
        _structure(closed, x, settings) for x in ("D1", "H4", "H1", "M15")
    )
    if d1 is None or h4 is None or h1 is None or m15 is None:
        return ScanDecision(
            symbol,
            direction,
            None,
            None,
            AdmissionDecision(False, "required structure unavailable"),
            None,
        )

    signal = analyze_m15_entry_signal(closed["M15"], direction, settings)
    if not signal.is_valid:
        return ScanDecision(
            symbol,
            direction,
            signal,
            None,
            AdmissionDecision(False, signal.details, signal),
            None,
        )

    execution_signals = []
    for name, frame in (
        ("M15", Timeframe.M15),
        ("M5", Timeframe.M5),
        ("M3", Timeframe.M3),
    ):
        if name in closed and getattr(closed[name], "empty", True) is False:
            execution_signals.append(
                analyze_execution_frame(closed[name], direction, frame, settings)
            )
    best = select_best_execution_frame(execution_signals) or signal

    confluence = evaluate_confluence(
        direction,
        d1,
        h4,
        h1,
        m15,
        best,
        in_pd_zone,
        killzone_active,
        draw_on_liquidity,
        settings,
    )
    if not confluence.tradable:
        return ScanDecision(
            symbol,
            direction,
            best,
            confluence,
            AdmissionDecision(False, confluence.reason, best),
            None,
        )

    identity = signal_fingerprint(
        symbol,
        str(closed["M15"].iloc[-1]["time"]),
        direction.value,
        best.setup_type.value,
        best.frame.value,
    )
    admission = admit_signal(best, gates)
    if not admission.allowed:
        return ScanDecision(
            symbol,
            direction,
            best,
            confluence,
            admission,
            identity,
        )

    levels = build_execution_levels(
        best,
        draw_target=None,
        min_rr=settings.min_rr_to_draw,
        atr_sl_buffer=settings.atr_sl_buffer,
    )
    if levels is None:
        return ScanDecision(
            symbol,
            direction,
            best,
            confluence,
            AdmissionDecision(False, "execution levels unavailable", best),
            identity,
        )
    return ScanDecision(
        symbol, direction, best, confluence, admission, identity, levels
    )

"""One-shot automatic DEMO-only experimental Breakout + Retest bridge.

Research certification is currently FAILED. These orders are labeled
experimental DEMO observations and can never qualify as live authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
from pathlib import Path
from typing import Any

from core.enums import Direction
from execution.mt5_demo_probe import DemoTerminalConfig, _matches_demo_account
from execution.mt5_demo_transport import DemoOrder, submit_demo_order
from research.breakout_retest import BreakoutRetestConfig, ResearchBar, detect_breakout_retest
from research.data_validation import validate_market_data


STRATEGY_ID = "breakout-retest-research-v1-pip0.1"
PIP_SIZE = 0.1
BAR_SECONDS = 300


@dataclass(frozen=True)
class DemoAutoResult:
    signal_detected: bool
    sent: bool
    accepted: bool
    reason: str
    signal_id: str | None = None
    broker_order_id: int | None = None


def _closed_m5_bars(api: Any, symbol: str, now: datetime) -> tuple[ResearchBar, ...]:
    # MT5 index 0 is a forming candle; index 1 is the last closed candle.
    rates = api.copy_rates_from_pos(symbol, api.TIMEFRAME_M5, 1, 80)
    if rates is None or len(rates) != 80:
        raise ValueError("80 completed M5 bars unavailable")
    bars = tuple(sorted((ResearchBar(
        datetime.fromtimestamp(int(row["time"]), timezone.utc),
        float(row["open"]), float(row["high"]), float(row["low"]),
        float(row["close"]), float(row["tick_volume"]),
    ) for row in rates), key=lambda bar: bar.timestamp))
    validate_market_data(bars)
    # Avoid a cross-session setup or a delayed broker feed after market reopen.
    if any(int((right.timestamp - left.timestamp).total_seconds()) != BAR_SECONDS
           for left, right in zip(bars[-33:-1], bars[-32:])):
        raise ValueError("M5 context has a session gap")
    since_close = (now - bars[-1].timestamp).total_seconds() - BAR_SECONDS
    if not 0 <= since_close <= 120:
        raise ValueError("last completed M5 candle is stale or not yet closed")
    return bars


def scan_and_submit_demo(api: Any, config: DemoTerminalConfig, ledger: Path,
                         *, execute: bool = False, kill_switch_off: bool = False,
                         now: datetime | None = None) -> DemoAutoResult:
    refused = lambda reason: DemoAutoResult(False, False, False, reason)
    if (api is None or not isinstance(config, DemoTerminalConfig) or not isinstance(ledger, Path)
            or type(execute) is not bool or type(kill_switch_off) is not bool):
        return refused("automatic DEMO inputs invalid")
    try:
        config.validate()
    except ValueError:
        return refused("automatic DEMO binding invalid")
    if not config.symbol.startswith("XAUUSD"):
        return refused("experimental strategy only supports broker XAUUSD")
    clock = now or datetime.now(timezone.utc)
    if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
        return refused("automatic DEMO clock invalid")
    initialized = False
    try:
        initialized = api.initialize(config.terminal_path, timeout=config.timeout_ms) is True
        if not initialized:
            return refused("automatic DEMO terminal unavailable")
        terminal = api.terminal_info()
        if (terminal is None or getattr(terminal, "connected", None) is not True
                or not _matches_demo_account(api, api.account_info(), config)):
            return refused("automatic DEMO account identity unavailable")
        bars = _closed_m5_bars(api, config.symbol, clock)
        signals = detect_breakout_retest(bars, PIP_SIZE, BreakoutRetestConfig(),
                                         min_signal_index=len(bars) - 1)
        if len(signals) != 1 or signals[0].signal_time != bars[-1].timestamp:
            return refused("no unique current closed-bar strategy signal")
        signal = signals[0]
        if signal.direction not in (Direction.BUY, Direction.SELL):
            return refused("automatic DEMO signal direction invalid")
        side = signal.direction.value
        if not all(type(x) in (int, float) and isfinite(x) and x > 0
                   for x in (signal.entry_price, signal.sl_price, signal.tp1)):
            return refused("automatic DEMO signal levels invalid")
        if (side == "BUY" and not signal.sl_price < signal.entry_price < signal.tp1
                or side == "SELL" and not signal.tp1 < signal.entry_price < signal.sl_price):
            return refused("automatic DEMO signal stop or target invalid")
        signature = "|".join((STRATEGY_ID, config.symbol, signal.signal_time.isoformat(),
                              signal.breakout_time.isoformat(), side))
        signal_id = sha256(signature.encode("utf-8")).hexdigest()[:40]
        if not execute or not kill_switch_off:
            return DemoAutoResult(True, False, False, "automatic DEMO execution disabled", signal_id)
        quote = api.symbol_info_tick(config.symbol)
        price = getattr(quote, "ask" if side == "BUY" else "bid", None)
        if (type(price) not in (int, float) or not isfinite(price)
                or abs(price - signal.entry_price) > 0.10):
            return DemoAutoResult(True, False, False, "strategy signal differs from broker price", signal_id)
        if not _matches_demo_account(api, api.account_info(), config):
            return DemoAutoResult(True, False, False, "DEMO account changed after scan", signal_id)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError, OverflowError):
        return refused("automatic DEMO market data unavailable or stale")
    finally:
        if initialized:
            try:
                api.shutdown()
            except (AttributeError, OSError, RuntimeError):
                return refused("automatic DEMO session shutdown failed")
    if ledger.with_suffix(".stop").exists():
        return DemoAutoResult(True, False, False, "automatic DEMO stop file active", signal_id)
    order = DemoOrder(signal_id, config.symbol, side, 0.01,
                      signal.sl_price, signal.tp1, signal.entry_price)
    submission = submit_demo_order(api, config, order, ledger)
    return DemoAutoResult(True, submission.sent, submission.accepted,
                          submission.reason, signal_id, submission.broker_order_id)

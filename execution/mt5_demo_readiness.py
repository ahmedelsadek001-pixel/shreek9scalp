"""Read-only environment checks before a DEMO sandbox attempt.

This diagnostic never creates an order request or grants trading authority.
Its result expires immediately and the transport independently rechecks all gates.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from execution.mt5_demo_clock import fresh_demo_quote_age_ms
from execution.mt5_demo_probe import DemoTerminalConfig, _matches_demo_account


@dataclass(frozen=True)
class DemoReadiness:
    ready_for_demo_attempt: bool
    blockers: tuple[str, ...]
    symbol: str | None = None
    order_transport_enabled: bool = False
    observed_filling_policy: str | None = None
    observed_tick_utc_offset_seconds: int | None = None


def _tick_offset_candidate(tick: Any, config: DemoTerminalConfig, clock: datetime) -> int | None:
    """Report a fresh supported offset for diagnosis, never grant authority."""
    matches = [offset for offset in (0, 10800)
               if fresh_demo_quote_age_ms(
                   tick, replace(config, server_utc_offset_seconds=offset), clock) is not None]
    return matches[0] if len(matches) == 1 else None


def _filling_policy(symbol: Any) -> str | None:
    flags = getattr(symbol, "filling_mode", None)
    if type(flags) is not int or flags < 0:
        return None
    return {1: "FOK", 2: "IOC", 3: "FOK+IOC"}.get(flags & 3)


def _can_fill(api: Any, symbol: Any) -> bool:
    flags = getattr(symbol, "filling_mode", None)
    return (type(flags) is int and flags >= 0 and (
        (bool(flags & 2) and type(getattr(api, "ORDER_FILLING_IOC", None)) is int
         and api.ORDER_FILLING_IOC == 1)
        or (bool(flags & 1) and type(getattr(api, "ORDER_FILLING_FOK", None)) is int
            and api.ORDER_FILLING_FOK == 0)))


def _number(value: Any) -> bool:
    return type(value) in (float, int) and isfinite(value)


def inspect_demo_readiness(api: Any, config: DemoTerminalConfig,
                           *, now: datetime | None = None) -> DemoReadiness:
    refused = lambda reason: DemoReadiness(False, (reason,))
    if api is None or not isinstance(config, DemoTerminalConfig):
        return refused("MT5 runtime or DEMO binding unavailable")
    try:
        config.validate()
        if now is not None and (
                not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None):
            return refused("readiness clock invalid")
    except ValueError:
        return refused("DEMO binding invalid")
    initialized = False
    report = refused("DEMO inspection failed")
    try:
        initialized = api.initialize(config.terminal_path, timeout=config.timeout_ms) is True
        if not initialized:
            report = refused("DEMO terminal connection failed")
        else:
            account = api.account_info()
            terminal = api.terminal_info()
            if (terminal is None or getattr(terminal, "connected", None) is not True
                    or not _matches_demo_account(api, account, config)):
                report = refused("selected DEMO identity unavailable")
            else:
                blockers: list[str] = []
                if (getattr(account, "trade_allowed", None) is not True
                        or getattr(account, "trade_expert", None) is not True
                        or getattr(terminal, "trade_allowed", None) is not True
                        or getattr(terminal, "tradeapi_disabled", None) is not False):
                    blockers.append("DEMO trading permission disabled")
                if getattr(account, "currency", None) != "USD":
                    blockers.append("DEMO account currency is not USD")
                if not _number(getattr(account, "equity", None)) or account.equity <= 0:
                    blockers.append("DEMO equity unavailable")
                symbol = api.symbol_info(config.symbol)
                if (symbol is None or getattr(symbol, "visible", None) is not True
                        or getattr(symbol, "currency_profit", None) != "USD"
                        or getattr(symbol, "trade_mode", None) != api.SYMBOL_TRADE_MODE_FULL
                        or not _number(getattr(symbol, "trade_contract_size", None))
                        or not _number(getattr(symbol, "point", None))
                        or not _number(getattr(symbol, "volume_min", None))
                        or not _number(getattr(symbol, "volume_step", None))
                        or symbol.trade_contract_size <= 0 or symbol.point <= 0
                        or symbol.volume_min <= 0 or symbol.volume_min > 0.01
                        or symbol.volume_step <= 0
                        or abs(round(0.01 / symbol.volume_step) * symbol.volume_step - 0.01) > 1e-9
                        or not _can_fill(api, symbol)):
                    blockers.append("DEMO symbol or 0.01-lot FOK/IOC contract unavailable")
                chart_bid = getattr(api, "SYMBOL_CHART_MODE_BID", 0)
                if (symbol is None or type(chart_bid) is not int or chart_bid != 0
                        or type(getattr(symbol, "chart_mode", None)) is not int
                        or symbol.chart_mode != chart_bid):
                    blockers.append("broker candles are not confirmed Bid-based")
                positions, pending = api.positions_get(), api.orders_get()
                if positions != () or pending != ():
                    blockers.append("existing exposure or broker exposure read unavailable")
                tick = api.symbol_info_tick(config.symbol)
                # Initialization and broker reads may block. Evaluate the quote
                # against time sampled after receiving it, not a pre-connect
                # timestamp that could make a fresh tick appear future-dated.
                clock = now if now is not None else datetime.now(timezone.utc)
                if (tick is None or not all(_number(getattr(tick, x, None))
                                            for x in ("ask", "bid", "time_msc"))
                        or tick.bid <= 0 or tick.ask <= tick.bid
                        or fresh_demo_quote_age_ms(tick, config, clock) is None
                        or tick.ask - tick.bid > 0.50):
                    blockers.append("DEMO quote missing, stale or wide")
                last_terminal, last_account = api.terminal_info(), api.account_info()
                if (last_terminal is None or getattr(last_terminal, "connected", None) is not True
                        or getattr(last_terminal, "trade_allowed", None) is not True
                        or getattr(last_terminal, "tradeapi_disabled", None) is not False
                        or not _matches_demo_account(api, last_account, config)
                        or getattr(last_account, "trade_allowed", None) is not True
                        or getattr(last_account, "trade_expert", None) is not True):
                    blockers.append("DEMO identity changed during inspection")
                report = DemoReadiness(not blockers, tuple(blockers), config.symbol,
                                       observed_filling_policy=_filling_policy(symbol),
                                       observed_tick_utc_offset_seconds=_tick_offset_candidate(tick, config, clock))
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError, OverflowError):
        report = refused("DEMO inspection failed")
    finally:
        if initialized:
            try:
                api.shutdown()
            except (AttributeError, OSError, RuntimeError):
                report = refused("DEMO inspection shutdown failed")
    return report

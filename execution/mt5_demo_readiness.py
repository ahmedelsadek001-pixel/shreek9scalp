"""Read-only environment checks before a DEMO sandbox attempt.

This diagnostic never creates an order request or grants trading authority.
Its result expires immediately and the transport independently rechecks all gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from execution.mt5_demo_probe import DemoTerminalConfig, _matches_demo_account


@dataclass(frozen=True)
class DemoReadiness:
    ready_for_demo_attempt: bool
    blockers: tuple[str, ...]
    symbol: str | None = None
    order_transport_enabled: bool = False


def _number(value: Any) -> bool:
    return type(value) in (float, int) and isfinite(value)


def inspect_demo_readiness(api: Any, config: DemoTerminalConfig,
                           *, now: datetime | None = None) -> DemoReadiness:
    refused = lambda reason: DemoReadiness(False, (reason,))
    if api is None or not isinstance(config, DemoTerminalConfig):
        return refused("MT5 runtime or DEMO binding unavailable")
    try:
        config.validate()
        clock = now or datetime.now(timezone.utc)
        if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
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
                        or not (getattr(symbol, "filling_mode", 0) & 2)):
                    blockers.append("DEMO symbol or 0.01-lot IOC contract unavailable")
                chart_bid = getattr(api, "SYMBOL_CHART_MODE_BID", 0)
                if (symbol is None or type(chart_bid) is not int or chart_bid != 0
                        or type(getattr(symbol, "chart_mode", None)) is not int
                        or symbol.chart_mode != chart_bid):
                    blockers.append("broker candles are not confirmed Bid-based")
                positions, pending = api.positions_get(), api.orders_get()
                if positions != () or pending != ():
                    blockers.append("existing exposure or broker exposure read unavailable")
                tick = api.symbol_info_tick(config.symbol)
                if (tick is None or not all(_number(getattr(tick, x, None))
                                            for x in ("ask", "bid", "time_msc"))
                        or tick.bid <= 0 or tick.ask <= tick.bid
                        or not 0 <= clock.timestamp() * 1000 - tick.time_msc <= 5000
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
                report = DemoReadiness(not blockers, tuple(blockers), config.symbol)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError, OverflowError):
        report = refused("DEMO inspection failed")
    finally:
        if initialized:
            try:
                api.shutdown()
            except (AttributeError, OSError, RuntimeError):
                report = refused("DEMO inspection shutdown failed")
    return report

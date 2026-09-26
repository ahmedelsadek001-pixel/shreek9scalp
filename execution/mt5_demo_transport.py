"""Isolated DEMO-only MT5 market-order transport. No live-account authority.

The static release gate pins this file's reviewed bytes; a change must be
reviewed and the pin updated before CI allows any broker send call.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
from pathlib import Path
import re
import sqlite3
from typing import Any

from execution.mt5_demo_probe import DemoTerminalConfig, _matches_demo_account


@dataclass(frozen=True)
class DemoOrder:
    intent_id: str
    symbol: str
    side: str
    volume: float
    stop_loss: float
    take_profit: float


@dataclass(frozen=True)
class DemoSubmission:
    sent: bool
    accepted: bool
    reason: str
    broker_order_id: int | None = None


def _number(value: Any) -> bool:
    return type(value) in (float, int) and isfinite(value)


def _account_matches(api: Any, config: DemoTerminalConfig) -> bool:
    account = api.account_info()
    terminal = api.terminal_info()
    return (
        _matches_demo_account(api, account, config)
        and getattr(account, "currency", None) == "USD"
        and getattr(account, "trade_allowed", None) is True
        and getattr(account, "trade_expert", None) is True
        and terminal is not None
        and getattr(terminal, "connected", None) is True
        and getattr(terminal, "trade_allowed", None) is True
        and getattr(terminal, "tradeapi_disabled", None) is False
        and _number(getattr(account, "equity", None))
        and account.equity > 0
    )


def _reserve(ledger: Path, config: DemoTerminalConfig, order: DemoOrder) -> bool:
    """Durably reserve before broker send; any failure refuses transport."""
    if not ledger.is_absolute() or ledger.suffix != ".sqlite3":
        return False
    # Keep the ledger outside the checkout so broker evidence is not committed.
    if not ledger.parent.is_dir():
        return False
    fingerprint = sha256(f"{config.expected_login}|{config.expected_server}".encode()).hexdigest()
    with sqlite3.connect(str(ledger), timeout=1, isolation_level=None) as db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS attempts "
                   "(account_hash TEXT NOT NULL, intent_id TEXT NOT NULL, status TEXT NOT NULL, "
                   "broker_order_id INTEGER, broker_deal_id INTEGER, broker_price REAL, "
                   "symbol TEXT NOT NULL, side TEXT NOT NULL, volume REAL NOT NULL, "
                   "stop_loss REAL NOT NULL, take_profit REAL NOT NULL, reserved_at TEXT NOT NULL, "
                   "PRIMARY KEY (account_hash, intent_id))")
        unknown = db.execute("SELECT 1 FROM attempts WHERE account_hash=? AND status='UNKNOWN' LIMIT 1",
                             (fingerprint,)).fetchone()
        if unknown:
            db.execute("ROLLBACK")
            return False
        db.execute("INSERT INTO attempts (account_hash, intent_id, status, symbol, side, volume, "
                   "stop_loss, take_profit, reserved_at) VALUES (?, ?, 'UNKNOWN', ?, ?, ?, ?, ?, ?)",
                   (fingerprint, order.intent_id, order.symbol, order.side, order.volume,
                    order.stop_loss, order.take_profit, datetime.now(timezone.utc).isoformat()))
        db.execute("COMMIT")
    return True


def _acknowledge(ledger: Path, config: DemoTerminalConfig, intent_id: str,
                 broker_order_id: int, broker_deal_id: int | None,
                 broker_price: float | None) -> None:
    fingerprint = sha256(f"{config.expected_login}|{config.expected_server}".encode()).hexdigest()
    with sqlite3.connect(str(ledger), timeout=1, isolation_level=None) as db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        cursor = db.execute("UPDATE attempts SET status='ACCEPTED', broker_order_id=?, "
                            "broker_deal_id=?, broker_price=? "
                            "WHERE account_hash=? AND intent_id=? AND status='UNKNOWN'",
                            (broker_order_id, broker_deal_id, broker_price, fingerprint, intent_id))
        if cursor.rowcount != 1:
            raise RuntimeError("reserved DEMO intent missing")
        db.execute("COMMIT")


def submit_demo_order(api: Any, config: DemoTerminalConfig, order: DemoOrder,
                      ledger: Path, *, now: datetime | None = None) -> DemoSubmission:
    """Submit at most once after verifying DEMO identity before the send call.

    This is a manual DEMO sandbox order, not certified strategy output. Failed
    or uncertain submissions remain reserved until independent reconciliation.
    """
    refused = lambda reason: DemoSubmission(False, False, reason)
    if api is None or not isinstance(config, DemoTerminalConfig) or not isinstance(order, DemoOrder):
        return refused("invalid DEMO transport inputs")
    try:
        config.validate()
    except ValueError:
        return refused("invalid DEMO binding")
    if (not isinstance(ledger, Path) or not re.fullmatch(r"[A-Za-z0-9_-]{8,48}", order.intent_id)
            or order.symbol != config.symbol or order.side not in ("BUY", "SELL")
            or not all(_number(x) for x in (order.volume, order.stop_loss, order.take_profit))
            or order.volume <= 0 or order.volume > 0.01):
        return refused("invalid or oversized DEMO intent")
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        return refused("timezone-aware clock required")
    initialized = False
    reserved = False
    try:
        initialized = api.initialize(config.terminal_path, timeout=config.timeout_ms) is True
        if not initialized or not _account_matches(api, config):
            return refused("DEMO identity or trading permission unavailable")
        symbol = api.symbol_info(config.symbol)
        if (symbol is None or getattr(symbol, "visible", None) is not True
                or getattr(symbol, "currency_profit", None) != "USD"
                or getattr(symbol, "trade_mode", None) != api.SYMBOL_TRADE_MODE_FULL
                or not _number(getattr(symbol, "trade_contract_size", None))
                or not _number(getattr(symbol, "volume_min", None))
                or not _number(getattr(symbol, "volume_step", None))
                or not _number(getattr(symbol, "point", None))
                or symbol.trade_contract_size <= 0 or symbol.point <= 0
                or symbol.volume_min > order.volume or symbol.volume_step <= 0
                or abs(round(order.volume / symbol.volume_step) * symbol.volume_step - order.volume) > 1e-9
                or not (symbol.filling_mode & 2)):
            return refused("DEMO contract or IOC filling unsupported")
        # Existing positions and pending orders are refused, including broker read errors.
        positions = api.positions_get()
        pending = api.orders_get()
        if positions is None or pending is None or positions or pending:
            return refused("account positions, pending orders or exposure unknown")
        tick = api.symbol_info_tick(config.symbol)
        if (tick is None or not all(_number(getattr(tick, x, None)) for x in ("ask", "bid", "time_msc"))
                or tick.bid <= 0 or tick.ask <= tick.bid
                or (clock.timestamp() * 1000 - tick.time_msc) < 0
                or (clock.timestamp() * 1000 - tick.time_msc) > 5000
                or tick.ask - tick.bid > 0.50):
            return refused("missing, stale or wide DEMO quote")
        price = tick.ask if order.side == "BUY" else tick.bid
        if (order.side == "BUY" and not (order.stop_loss < price < order.take_profit)
                or order.side == "SELL" and not (order.take_profit < price < order.stop_loss)):
            return refused("protective stop or target invalid")
        stops = max(getattr(symbol, "trade_stops_level", 0), 0) * symbol.point
        if (abs(price - order.stop_loss) < stops or abs(price - order.take_profit) < stops):
            return refused("stop or target too close")
        equity = api.account_info().equity
        if (not _number(equity) or equity <= 0 or
                abs(price - order.stop_loss) * symbol.trade_contract_size * order.volume > equity * 0.005):
            return refused("DEMO stop risk exceeds 0.5% equity")
        request = {
            "action": api.TRADE_ACTION_DEAL, "symbol": config.symbol,
            "volume": order.volume, "type": api.ORDER_TYPE_BUY if order.side == "BUY" else api.ORDER_TYPE_SELL,
            "price": price, "sl": order.stop_loss, "tp": order.take_profit,
            "deviation": 10, "magic": 521000, "comment": "SHREEK-DEMO-" + order.intent_id[:12],
            "type_time": api.ORDER_TIME_GTC, "type_filling": api.ORDER_FILLING_IOC,
        }
        check = api.order_check(request)
        if check is None or getattr(check, "retcode", None) != 0:
            return refused("broker DEMO order check refused")
        # Recheck account, exposure, and quote immediately before the send.
        if not _account_matches(api, config) or api.positions_get() != () or api.orders_get() != ():
            return refused("DEMO identity or exposure changed before send")
        fresh = api.symbol_info_tick(config.symbol)
        if (fresh is None or getattr(fresh, "time_msc", None) != tick.time_msc
                or getattr(fresh, "ask", None) != tick.ask
                or getattr(fresh, "bid", None) != tick.bid
                or (datetime.now(timezone.utc).timestamp() * 1000 - tick.time_msc) > 5000):
            return refused("DEMO quote changed before send")
        try:
            reserved = _reserve(ledger, config, order)
        except (OSError, sqlite3.Error, ValueError):
            return refused("DEMO intent already reserved or ledger unavailable")
        if not reserved:
            return refused("DEMO ledger location unavailable")
        result = api.order_send(request)
        if (result is not None and getattr(result, "retcode", None) == api.TRADE_RETCODE_DONE
                and type(getattr(result, "order", None)) is int and result.order > 0):
            deal_id = getattr(result, "deal", None)
            deal_id = deal_id if type(deal_id) is int and deal_id > 0 else None
            fill_price = getattr(result, "price", None)
            fill_price = float(fill_price) if _number(fill_price) and fill_price > 0 else None
            _acknowledge(ledger, config, order.intent_id, result.order, deal_id, fill_price)
            return DemoSubmission(True, True, "DEMO broker acknowledged; reconcile independently", result.order)
        return DemoSubmission(True, False, "DEMO submission uncertain; do not retry")
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError, OverflowError, sqlite3.Error):
        if reserved:
            return DemoSubmission(True, False, "DEMO submission uncertain; do not retry")
        return refused("DEMO transport failed closed; inspect broker history before retry")
    finally:
        if initialized:
            try:
                api.shutdown()
            except (AttributeError, OSError, RuntimeError):
                pass

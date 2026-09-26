"""Read-only DEMO broker-history evidence for durable sandbox order attempts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
from pathlib import Path
import sqlite3
from typing import Any

from execution.mt5_demo_probe import DemoTerminalConfig, _matches_demo_account


@dataclass(frozen=True)
class DemoHistoryReport:
    verified_demo: bool
    reason: str
    attempts: tuple[dict[str, Any], ...] = ()


def _active_demo(api: Any, config: DemoTerminalConfig) -> bool:
    terminal = api.terminal_info()
    return (terminal is not None and getattr(terminal, "connected", None) is True
            and _matches_demo_account(api, api.account_info(), config))


def _deal_info(deal: Any) -> dict[str, Any] | None:
    fields = ("ticket", "order", "position_id", "entry", "type", "volume", "price",
              "profit", "commission", "swap", "fee", "time_msc")
    if any(getattr(deal, field, None) is None for field in fields):
        return None
    result = {field: getattr(deal, field) for field in fields}
    if (any(type(result[f]) is not int or result[f] < 0 for f in
            ("ticket", "order", "position_id", "entry", "type", "time_msc"))
            or any(type(result[f]) not in (int, float) or not isfinite(result[f])
                   for f in ("volume", "price", "profit", "commission", "swap", "fee"))
            or result["ticket"] == 0 or result["volume"] <= 0 or result["price"] <= 0):
        return None
    result["time_utc"] = datetime.fromtimestamp(result.pop("time_msc") / 1000, timezone.utc).isoformat()
    return result


def inspect_demo_history(api: Any, config: DemoTerminalConfig, ledger: Path) -> DemoHistoryReport:
    """Read only verified DEMO deals, bound to broker order tickets in ledger.

    This is observational sandbox evidence, never strategy accreditation.
    """
    refused = lambda reason: DemoHistoryReport(False, reason)
    if api is None or not isinstance(config, DemoTerminalConfig) or not isinstance(ledger, Path):
        return refused("invalid DEMO history input")
    try:
        config.validate()
    except ValueError:
        return refused("invalid DEMO binding")
    if not ledger.is_absolute() or not ledger.is_file():
        return refused("durable DEMO ledger unavailable")
    initialized = False
    report = refused("DEMO broker history unavailable")
    try:
        with sqlite3.connect(ledger.resolve().as_uri() + "?mode=ro", uri=True) as db:
            rows = db.execute("SELECT account_hash, intent_id, broker_order_id, symbol, side, volume "
                              "FROM attempts WHERE status='ACCEPTED' ORDER BY reserved_at").fetchall()
        initialized = api.initialize(config.terminal_path, timeout=config.timeout_ms) is True
        if not initialized or not _active_demo(api, config):
            return refused("DEMO account changed or disconnected")
        fingerprint = sha256(f"{config.expected_login}|{config.expected_server}".encode()).hexdigest()
        output: list[dict[str, Any]] = []
        for account_hash, intent_id, order_id, symbol, side, volume in rows:
            if (account_hash != fingerprint or type(order_id) is not int or order_id <= 0
                    or symbol != config.symbol
                    or side not in ("BUY", "SELL") or type(volume) not in (int, float)
                    or not isfinite(volume) or volume <= 0):
                return refused("DEMO ledger identity malformed")
            opening = api.history_deals_get(ticket=order_id)
            if opening is None:
                return refused("broker history lookup failed")
            matching = [d for d in opening if getattr(d, "order", None) == order_id
                        and getattr(d, "symbol", None) == symbol
                        and getattr(d, "magic", None) == 521000
                        and getattr(d, "entry", None) == api.DEAL_ENTRY_IN]
            item: dict[str, Any] = {"intent_id": intent_id, "broker_order_id": order_id,
                                    "symbol": symbol, "side": side, "status": "opening_not_verified",
                                    "broker_deals": []}
            if len(matching) == 1:
                position_id = getattr(matching[0], "position_id", None)
                related = api.history_deals_get(position=position_id) if type(position_id) is int and position_id > 0 else None
                if related is None:
                    return refused("broker position history lookup failed")
                if not any(getattr(d, "ticket", None) == getattr(matching[0], "ticket", None)
                           for d in related):
                    return refused("opening deal missing from position history")
                deals = [_deal_info(d) for d in related if getattr(d, "position_id", None) == position_id
                         and getattr(d, "symbol", None) == symbol]
                if any(d is None for d in deals):
                    return refused("broker deal metadata incomplete")
                item["broker_deals"] = sorted(deals, key=lambda d: (d["time_utc"], d["ticket"]))
                entry = _deal_info(matching[0])
                closes = [d for d in related if getattr(d, "position_id", None) == position_id
                          and getattr(d, "symbol", None) == symbol
                          and getattr(d, "entry", None) == api.DEAL_ENTRY_OUT]
                closed_volume = sum(getattr(d, "volume", 0) for d in closes)
                if entry is not None and len([d for d in related if getattr(d, "position_id", None) == position_id
                                               and getattr(d, "entry", None) == api.DEAL_ENTRY_IN]) == 1:
                    item["status"] = ("closed_observed" if abs(closed_volume - entry["volume"]) < 1e-9
                                      else "open_or_partial")
                    item["manual_intervention"] = any(getattr(d, "magic", None) != 521000 for d in closes)
            output.append(item)
        if not _active_demo(api, config):
            return refused("DEMO account changed during history read")
        report = DemoHistoryReport(True, "DEMO broker history observed; no strategy attribution", tuple(output))
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError, OverflowError, sqlite3.Error):
        report = refused("DEMO history inspection failed")
    finally:
        if initialized:
            try:
                api.shutdown()
            except (AttributeError, OSError, RuntimeError):
                report = refused("DEMO history shutdown failed")
    return report

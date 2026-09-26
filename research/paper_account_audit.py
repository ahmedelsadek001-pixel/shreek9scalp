"""Read-only, fail-closed audit of an externally exported DEMO account.

This module checks consistency, not broker authenticity or strategy performance.
It never sends orders and never sets a release evidence flag.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
from pathlib import Path


INTENT_COLUMNS = ("intent_id", "symbol", "side", "volume", "requested_price", "sent_at")
FILL_COLUMNS = ("intent_id", "broker_order_id", "symbol", "side", "volume", "entry_price",
                "exit_price", "commission", "net_pnl", "filled_at", "closed_at")
MANIFEST_KEYS = ("account_mode", "account_fingerprint", "source", "symbol", "strategy_id",
                 "strategy_version", "currency", "contract_size", "intents_sha256", "fills_sha256")


@dataclass(frozen=True)
class PaperAccountAudit:
    structurally_reconciled: bool
    eligible_for_external_review: bool
    paper_trading_validated: bool
    failures: tuple[str, ...]
    intent_count: int
    fill_count: int
    trading_days: int
    net_pnl: str | None
    worst_entry_slippage: str | None
    worst_fill_delay_seconds: int | None
    account_fingerprint: str | None
    source_hashes: tuple[str, str] | None

    def as_dict(self) -> dict[str, object]:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


def _text(value: object, field: str) -> str:
    if type(value) is not str or not value or value != value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError("invalid " + field)
    return value


def _sha(value: object, field: str) -> str:
    result = _text(value, field)
    if len(result) != 64 or any(c not in "0123456789abcdef" for c in result):
        raise ValueError("invalid " + field)
    return result


def _decimal(value: object, field: str, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    try:
        result = Decimal(_text(value, field))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("invalid " + field) from exc
    if not result.is_finite() or (positive and result <= 0) or (nonnegative and result < 0):
        raise ValueError("invalid " + field)
    return result


def _instant(value: object, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(_text(value, field))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError("timezone required")
        return result.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError("invalid " + field) from exc


def _rows(raw: bytes, columns: tuple[str, ...], name: str) -> list[dict[str, str]]:
    try:
        content = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
        if reader.fieldnames != list(columns):
            raise ValueError(name + " columns differ from the documented schema")
        records = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise ValueError(name + " is not a valid UTF-8 CSV") from exc
    if not records or any(None in row or any(value is None for value in row.values()) for row in records):
        raise ValueError(name + " is empty or has malformed rows")
    return records


def audit_paper_account(manifest_path: str | Path, intents_path: str | Path, fills_path: str | Path,
                        *, min_trades: int = 30, min_days: int = 10,
                        max_slippage: str = "1.00", max_fill_delay_seconds: int = 30) -> PaperAccountAudit:
    """Audit pinned independent exports; report never certifies broker provenance.

    The account fingerprint is SHA-256 of an operator-held account identifier;
    never put the identifier, personal data, or credentials in this repository.
    """
    if type(min_trades) is not int or min_trades < 1 or type(min_days) is not int or min_days < 1:
        raise ValueError("positive sample thresholds required")
    if type(max_fill_delay_seconds) is not int or max_fill_delay_seconds < 0:
        raise ValueError("invalid fill delay policy")
    slip_limit = _decimal(max_slippage, "max_slippage", nonnegative=True)
    failures: list[str] = []
    intents: list[dict[str, str]] = []
    fills: list[dict[str, str]] = []
    account = None
    hashes = None
    pnl = None
    worst_slip = None
    worst_delay = None
    days: set[object] = set()
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if type(manifest) is not dict or set(manifest) != set(MANIFEST_KEYS):
            raise ValueError("invalid manifest schema")
        if manifest["account_mode"] != "DEMO" or manifest["source"] != "broker_export":
            raise ValueError("DEMO broker export required; REAL and simulations are excluded")
        account = _sha(manifest["account_fingerprint"], "account_fingerprint")
        symbol = _text(manifest["symbol"], "symbol")
        _text(manifest["strategy_id"], "strategy_id")
        _text(manifest["strategy_version"], "strategy_version")
        _text(manifest["currency"], "currency")
        contract = _decimal(manifest["contract_size"], "contract_size", positive=True)
        intended = Path(intents_path).read_bytes()
        observed = Path(fills_path).read_bytes()
        hashes = (sha256(intended).hexdigest(), sha256(observed).hexdigest())
        if hashes != (_sha(manifest["intents_sha256"], "intents_sha256"),
                      _sha(manifest["fills_sha256"], "fills_sha256")):
            raise ValueError("source export hash mismatch")
        intents = _rows(intended, INTENT_COLUMNS, "intents")
        fills = _rows(observed, FILL_COLUMNS, "fills")
        by_id = {}
        for row in intents:
            key = _text(row["intent_id"], "intent_id")
            if key in by_id:
                raise ValueError("duplicate intent ID")
            if row["symbol"] != symbol or row["side"] not in ("BUY", "SELL"):
                raise ValueError("intent symbol or side mismatch")
            _decimal(row["volume"], "volume", positive=True)
            _decimal(row["requested_price"], "requested_price", positive=True)
            _instant(row["sent_at"], "sent_at")
            by_id[key] = row
        seen_ids: set[str] = set()
        broker_ids: set[str] = set()
        total = Decimal("0")
        peak_slip = Decimal("0")
        peak_delay = 0
        for row in fills:
            key = _text(row["intent_id"], "fill intent_id")
            broker_id = _text(row["broker_order_id"], "broker_order_id")
            if key not in by_id or key in seen_ids or broker_id in broker_ids:
                raise ValueError("orphan or duplicate fill")
            seen_ids.add(key)
            broker_ids.add(broker_id)
            intent = by_id[key]
            if row["symbol"] != symbol or row["side"] != intent["side"]:
                raise ValueError("fill symbol or side mismatch")
            volume = _decimal(row["volume"], "volume", positive=True)
            if volume != _decimal(intent["volume"], "intent volume", positive=True):
                raise ValueError("fill volume mismatch; partial fills require explicit normalization")
            entry = _decimal(row["entry_price"], "entry_price", positive=True)
            exit_price = _decimal(row["exit_price"], "exit_price", positive=True)
            commission = _decimal(row["commission"], "commission", nonnegative=True)
            net = _decimal(row["net_pnl"], "net_pnl")
            requested = _decimal(intent["requested_price"], "requested_price", positive=True)
            sent = _instant(intent["sent_at"], "sent_at")
            filled = _instant(row["filled_at"], "filled_at")
            closed = _instant(row["closed_at"], "closed_at")
            if filled < sent or closed < filled:
                raise ValueError("fill timestamps out of order")
            signed_move = exit_price - entry if row["side"] == "BUY" else entry - exit_price
            if abs(signed_move * volume * contract - commission - net) > Decimal("0.01"):
                raise ValueError("net P&L does not reconcile to price, volume and contract")
            slip = abs(entry - requested)
            delay = int((filled - sent).total_seconds())
            peak_slip = max(peak_slip, slip)
            peak_delay = max(peak_delay, delay)
            days.add(filled.date())
            total += net
        if len(seen_ids) != len(by_id):
            raise ValueError("unfilled intents; complete export required")
        pnl, worst_slip, worst_delay = str(total), str(peak_slip), peak_delay
        if len(fills) < min_trades:
            failures.append("insufficient observed DEMO trades")
        if len(days) < min_days:
            failures.append("insufficient distinct trading days")
        if peak_slip > slip_limit:
            failures.append("entry slippage above policy")
        if peak_delay > max_fill_delay_seconds:
            failures.append("fill delay above policy")
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        failures.append(str(exc))
    consistent = not failures
    return PaperAccountAudit(consistent, consistent, False, tuple(failures), len(intents),
                             len(fills), len(days), pnl, worst_slip, worst_delay, account, hashes)

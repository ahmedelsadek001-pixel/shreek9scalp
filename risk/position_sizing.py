"""Broker-aware position sizing with fail-closed safety semantics."""
from __future__ import annotations

import math
from utils.mt5_compat import mt5
from market.data_manager import MT5Manager, _MT5_CALL_LOCK
from utils.logger import get_logger

log = get_logger(__name__)


def compute_lot_size(symbol: str, risk_usd: float, sl_distance: float) -> float:
    """Return broker-valid volume whose modeled risk does not exceed risk_usd.

    ``sl_distance`` is a price distance, not a pip count. This avoids the
    common 5-digit/3-digit/CFD pip-conversion error and works with MT5 tick
    size/value metadata across symbols.
    """
    if not all(math.isfinite(float(x)) for x in (risk_usd, sl_distance)) or risk_usd <= 0 or sl_distance <= 0:
        return 0.0
    if not MT5Manager.ensure_initialized():
        log.error("Position sizing blocked: MT5 unavailable")
        return 0.0
    with _MT5_CALL_LOCK:
        symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        log.error("Position sizing blocked: symbol_info unavailable for %s", symbol)
        return 0.0

    tick_size = float(getattr(symbol_info, "trade_tick_size", 0) or 0)
    tick_value = float(getattr(symbol_info, "trade_tick_value", 0) or 0)
    lot_step = float(getattr(symbol_info, "volume_step", 0) or 0)
    lot_min = float(getattr(symbol_info, "volume_min", 0) or 0)
    lot_max = float(getattr(symbol_info, "volume_max", 0) or 0)
    if not all(math.isfinite(x) and x > 0 for x in (tick_size, tick_value, lot_step, lot_min, lot_max)):
        log.error("Position sizing blocked: invalid broker metadata for %s", symbol)
        return 0.0

    risk_per_lot = (sl_distance / tick_size) * tick_value
    if not math.isfinite(risk_per_lot) or risk_per_lot <= 0:
        return 0.0
    raw_lots = risk_usd / risk_per_lot
    if not math.isfinite(raw_lots) or raw_lots < lot_min:
        return 0.0

    lots = math.floor((raw_lots + 1e-12) / lot_step) * lot_step
    lots = min(lots, lot_max)
    if lots < lot_min or not math.isfinite(lots):
        return 0.0
    decimals = max(0, int(round(-math.log10(lot_step))) if lot_step < 1 else 0)
    return round(lots, decimals)

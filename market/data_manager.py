"""
MT5 connection singleton + multi-timeframe data fetch with caching.

V5 production rules: all MT5 calls are serialized and live analysis has an
explicit closed-bar path so the forming candle cannot drive a signal.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from utils.mt5_compat import mt5

from config.settings import TIMEFRAMES
from market.data_integrity import require_valid_bars
from utils.logger import get_logger

log = get_logger(__name__)
_MT5_CALL_LOCK = threading.RLock()
_DECIMALS_FALLBACK_2 = ("XAU", "BTC", "XBR", "OIL", "US30", "US500", "NAS", "UK100", "GER40")
_DECIMALS_FALLBACK_3 = ("JPY",)


def digits_for_symbol(symbol: str) -> int:
    with _MT5_CALL_LOCK:
        info = mt5.symbol_info(symbol)
    if info is not None and getattr(info, "digits", None) is not None:
        return int(info.digits)
    log.warning("No broker digits for %s; using fallback", symbol)
    if any(x in symbol for x in _DECIMALS_FALLBACK_2): return 2
    if any(x in symbol for x in _DECIMALS_FALLBACK_3): return 3
    return 5


class MT5Manager:
    _initialized = False
    _last_check: datetime | None = None
    _check_interval_sec = 30

    @classmethod
    def ensure_initialized(cls) -> bool:
        with _MT5_CALL_LOCK:
            now = datetime.now()
            if cls._initialized and cls._last_check and (now - cls._last_check).total_seconds() < cls._check_interval_sec:
                return True
            cls._last_check = now
            if not cls._initialized:
                cls._initialized = bool(mt5.initialize())
                return cls._initialized
            try:
                if mt5.terminal_info() is None:
                    cls._initialized = bool(mt5.initialize())
            except Exception:
                cls._initialized = bool(mt5.initialize())
            return cls._initialized

    @classmethod
    def shutdown(cls):
        with _MT5_CALL_LOCK:
            if cls._initialized:
                mt5.shutdown()
                cls._initialized = False


def _add_base_indicators(df: pd.DataFrame) -> pd.DataFrame:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["avg_body"] = (df["close"] - df["open"]).abs().rolling(20).mean()
    return df


@dataclass
class _CacheEntry:
    data_pack: dict
    fetched_at: float


class DataCache:
    def __init__(self, ttl_seconds: float = 2.0):
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, symbol: str) -> dict | None:
        with self._lock:
            entry = self._store.get(symbol)
            if entry is None or time.time() - entry.fetched_at > self.ttl_seconds:
                if entry is not None: self._store.pop(symbol, None)
                return None
            return entry.data_pack

    def set(self, symbol: str, data_pack: dict) -> None:
        with self._lock:
            self._store[symbol] = _CacheEntry(data_pack, time.time())


_DATA_CACHE = DataCache()


def get_mtf_data(symbol: str, use_cache: bool = True) -> dict | None:
    if use_cache:
        cached = _DATA_CACHE.get(symbol)
        if cached is not None: return cached
    if not MT5Manager.ensure_initialized(): return None
    with _MT5_CALL_LOCK:
        if not mt5.symbol_select(symbol, True):
            return {"error": f"Symbol {symbol} not available in MT5 Market Watch"}
    data_pack: dict = {}
    for tf_name, spec in TIMEFRAMES.items():
        with _MT5_CALL_LOCK:
            rates = mt5.copy_rates_from_pos(symbol, spec.mt5_constant, 0, spec.bars_to_fetch)
        if rates is None or len(rates) == 0:
            return {"error": f"No data for {symbol} on {tf_name}"}
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        require_valid_bars(df.to_dict("records"))
        data_pack[tf_name] = _add_base_indicators(df).reset_index(drop=True)
    _DATA_CACHE.set(symbol, data_pack)
    return data_pack


def get_mtf_data_closed(symbol: str, use_cache: bool = True) -> dict | None:
    data = get_mtf_data(symbol, use_cache=use_cache)
    if data is None or "error" in data: return data
    return {tf: df.iloc[:-1].reset_index(drop=True) for tf, df in data.items() if len(df) > 1}

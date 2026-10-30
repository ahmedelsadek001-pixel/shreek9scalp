"""Optional MetaTrader5 runtime compatibility layer.

The strategy engine and CI run without a broker terminal.  When the native
MetaTrader5 package is installed, this module exposes it unchanged.  On
Linux/CI it provides timeframe constants while broker calls fail closed.
"""
from __future__ import annotations

try:
    import MetaTrader5 as _mt5
except ImportError:  # pragma: no cover - exercised by Linux CI without MT5
    _mt5 = None


class _UnavailableMT5:
    TIMEFRAME_M3 = 3
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440

    def __getattr__(self, name: str):
        def unavailable(*args, **kwargs):
            return None
        return unavailable


mt5 = _mt5 if _mt5 is not None else _UnavailableMT5()
AVAILABLE = _mt5 is not None


def read_only_mt5_runtime():
    """Return the native runtime only; never substitute the CI stub for a broker probe."""
    return _mt5


def demo_only_mt5_runtime():
    """Return native MT5 for the isolated, account-attested DEMO transport."""
    return _mt5

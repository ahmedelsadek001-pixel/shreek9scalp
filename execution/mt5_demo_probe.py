"""Read-only MT5 DEMO account binding; never submits or changes broker orders.

The Python MT5 package requires a local terminal. The probe attaches only to
an explicitly selected terminal and verifies the already logged-in account.
It never logs in, accepts a password, or grants execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class DemoTerminalConfig:
    terminal_path: str
    expected_login: int
    expected_server: str
    symbol: str = "XAUUSD"
    timeout_ms: int = 5000

    def validate(self) -> None:
        if type(self.terminal_path) is not str or not self.terminal_path.strip():
            raise ValueError("explicit demo terminal path required")
        if type(self.expected_login) is not int or self.expected_login <= 0:
            raise ValueError("expected demo login must be a positive integer")
        for name in ("expected_server", "symbol"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip() or value != value.strip():
                raise ValueError(f"{name} must be non-empty normalized text")
        if type(self.timeout_ms) is not int or not 1 <= self.timeout_ms <= 30000:
            raise ValueError("demo terminal timeout must be between 1 and 30000 ms")


@dataclass(frozen=True)
class DemoTerminalProbe:
    connected_demo: bool
    reason: str
    symbol: str | None = None
    contract_size: float | None = None
    volume_min: float | None = None
    volume_step: float | None = None
    terminal_trade_allowed: bool = False
    order_transport_enabled: bool = False


def _matches_demo_account(api: Any, account: Any, config: DemoTerminalConfig) -> bool:
    """Never infer DEMO from account name, server spelling or a user flag."""
    # The Python account_info reference shows trade_mode=0 on a DEMO account.
    # Some MT5 Python builds do not expose the MQL5 enum constant by name.
    # If they do expose it, a conflicting value is refused.
    mode = getattr(api, "ACCOUNT_TRADE_MODE_DEMO", 0)
    return (
        type(mode) is int
        and mode == 0
        and account is not None
        and type(getattr(account, "trade_mode", None)) is int
        and account.trade_mode == 0
        and type(getattr(account, "login", None)) is int
        and account.login == config.expected_login
        and getattr(account, "server", None) == config.expected_server
    )


def _positive_number(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) and result > 0 else None


def probe_demo_terminal(api: Any, config: DemoTerminalConfig) -> DemoTerminalProbe:
    """Connect, recheck identity after reading symbol metadata, and disconnect.

    Each call creates its own short read-only session. A positive result is
    diagnostic and expires on return; no broker transport consumes this bool.
    """
    if not isinstance(config, DemoTerminalConfig):
        raise TypeError("config must be DemoTerminalConfig")
    config.validate()
    if api is None:
        return DemoTerminalProbe(False, "MT5 Python runtime unavailable")
    initialized = False
    report = DemoTerminalProbe(False, "DEMO terminal inspection failed")
    try:
        initialized = api.initialize(config.terminal_path, timeout=config.timeout_ms) is True
        if not initialized:
            report = DemoTerminalProbe(False, "demo terminal connection failed")
        else:
            terminal = api.terminal_info()
            account = api.account_info()
            if terminal is None or getattr(terminal, "connected", None) is not True:
                report = DemoTerminalProbe(False, "demo terminal disconnected")
            elif not _matches_demo_account(api, account, config):
                report = DemoTerminalProbe(False, "account is not the selected DEMO identity")
            else:
                symbol = api.symbol_info(config.symbol)
                contract = _positive_number(getattr(symbol, "trade_contract_size", None))
                minimum = _positive_number(getattr(symbol, "volume_min", None))
                step = _positive_number(getattr(symbol, "volume_step", None))
                if symbol is None or None in (contract, minimum, step):
                    report = DemoTerminalProbe(False, "DEMO symbol contract metadata unavailable")
                else:
                    final_terminal = api.terminal_info()
                    final_account = api.account_info()
                    if (final_terminal is None or getattr(final_terminal, "connected", None) is not True
                            or not _matches_demo_account(api, final_account, config)):
                        report = DemoTerminalProbe(False, "DEMO identity changed during probe")
                    else:
                        allowed = getattr(terminal, "trade_allowed", None) is True
                        report = DemoTerminalProbe(True, "verified DEMO terminal; observation only",
                                                   config.symbol, contract, minimum, step, allowed)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError, OverflowError):
        report = DemoTerminalProbe(False, "DEMO terminal inspection failed")
    finally:
        if initialized:
            try:
                api.shutdown()
            except (AttributeError, OSError, RuntimeError):
                report = DemoTerminalProbe(False, "DEMO terminal shutdown failed")
    return report

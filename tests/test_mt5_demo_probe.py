from dataclasses import dataclass

import pytest

from execution.mt5_demo_probe import DemoTerminalConfig, probe_demo_terminal
from execution import mt5_demo_probe_cli


@dataclass
class Account:
    login: int = 10123
    server: str = "Sandbox-Demo"
    trade_mode: int = 0


@dataclass
class Terminal:
    connected: bool = True
    trade_allowed: bool = True


@dataclass
class Symbol:
    trade_contract_size: float = 100.0
    volume_min: float = 0.01
    volume_step: float = 0.01


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(self, account=None, terminal=None, symbol=None, initialize=True):
        self.account = account if account is not None else Account()
        self.terminal = terminal if terminal is not None else Terminal()
        self.symbol = symbol if symbol is not None else Symbol()
        self.connect_ok = initialize
        self.stopped = 0
        self.reads = 0

    def initialize(self, path, *, timeout):
        assert path == "C:/DEMO/terminal64.exe" and timeout == 5000
        return self.connect_ok

    def terminal_info(self):
        return self.terminal

    def account_info(self):
        self.reads += 1
        return self.account

    def symbol_info(self, symbol):
        assert symbol == "XAUUSD"
        return self.symbol

    def shutdown(self):
        self.stopped += 1


CONFIG = DemoTerminalConfig("C:/DEMO/terminal64.exe", 10123, "Sandbox-Demo")


def test_verified_demo_probe_is_read_only_and_closes_terminal():
    api = FakeMT5()
    result = probe_demo_terminal(api, CONFIG)
    assert result.connected_demo
    assert result.contract_size == 100.0 and result.volume_step == 0.01
    assert result.order_transport_enabled is False
    assert api.reads == 2 and api.stopped == 1


@pytest.mark.parametrize("account", [
    Account(trade_mode=2), Account(login=20234), Account(server="Other-Demo"),
    Account(trade_mode=1),
])
def test_real_contest_or_different_account_is_rejected(account):
    api = FakeMT5(account=account)
    report = probe_demo_terminal(api, CONFIG)
    assert not report.connected_demo and not report.order_transport_enabled
    assert api.stopped == 1


def test_python_build_without_named_demo_constant_uses_documented_mode_zero():
    class UnnamedMode(FakeMT5):
        ACCOUNT_TRADE_MODE_DEMO = None

    # A present but malformed constant is blocked, not silently replaced.
    assert not probe_demo_terminal(UnnamedMode(), CONFIG).connected_demo
    api = FakeMT5()
    delattr(FakeMT5, "ACCOUNT_TRADE_MODE_DEMO")
    try:
        assert probe_demo_terminal(api, CONFIG).connected_demo
    finally:
        FakeMT5.ACCOUNT_TRADE_MODE_DEMO = 0


def test_missing_runtime_connection_or_symbol_metadata_fails_closed():
    assert not probe_demo_terminal(None, CONFIG).connected_demo
    bad = FakeMT5(initialize=False)
    assert not probe_demo_terminal(bad, CONFIG).connected_demo
    assert bad.stopped == 0
    for api in (FakeMT5(terminal=Terminal(connected=False)),
                FakeMT5(symbol=Symbol(volume_step=0.0))):
        assert not probe_demo_terminal(api, CONFIG).connected_demo
        assert api.stopped == 1


def test_switched_account_during_probe_is_rejected():
    class Switched(FakeMT5):
        def account_info(self):
            result = super().account_info()
            if self.reads == 2:
                return Account(trade_mode=2)
            return result
    assert not probe_demo_terminal(Switched(), CONFIG).connected_demo


def test_shutdown_failure_never_returns_a_positive_probe():
    class BrokenShutdown(FakeMT5):
        def shutdown(self):
            raise RuntimeError("terminal error")
    report = probe_demo_terminal(BrokenShutdown(), CONFIG)
    assert not report.connected_demo
    assert report.reason == "DEMO terminal shutdown failed"


def test_binding_is_explicit_and_cli_never_prints_account(monkeypatch, capsys):
    for name in ("SHREEK_DEMO_TERMINAL_PATH", "SHREEK_DEMO_LOGIN", "SHREEK_DEMO_SERVER"):
        monkeypatch.delenv(name, raising=False)
    assert mt5_demo_probe_cli.main() == 2
    output = capsys.readouterr().out
    assert "10123" not in output
    with pytest.raises(ValueError, match="positive integer"):
        DemoTerminalConfig("terminal.exe", True, "Sandbox-Demo").validate()


def test_cli_verified_demo_redacts_login_and_never_enables_transport(monkeypatch, capsys):
    monkeypatch.setenv("SHREEK_DEMO_TERMINAL_PATH", CONFIG.terminal_path)
    monkeypatch.setenv("SHREEK_DEMO_LOGIN", str(CONFIG.expected_login))
    monkeypatch.setenv("SHREEK_DEMO_SERVER", CONFIG.expected_server)
    monkeypatch.setattr(mt5_demo_probe_cli, "read_only_mt5_runtime", lambda: FakeMT5())
    assert mt5_demo_probe_cli.main() == 0
    import json
    output = capsys.readouterr().out
    assert "10123" not in output and "Sandbox-Demo" not in output
    report = json.loads(output)
    assert report["connected_demo"] is True
    assert report["order_transport_enabled"] is False


def test_cli_refuses_real_account_without_exposing_it(monkeypatch, capsys):
    monkeypatch.setenv("SHREEK_DEMO_TERMINAL_PATH", CONFIG.terminal_path)
    monkeypatch.setenv("SHREEK_DEMO_LOGIN", str(CONFIG.expected_login))
    monkeypatch.setenv("SHREEK_DEMO_SERVER", CONFIG.expected_server)
    monkeypatch.setattr(mt5_demo_probe_cli, "read_only_mt5_runtime",
                        lambda: FakeMT5(account=Account(trade_mode=2)))
    assert mt5_demo_probe_cli.main() == 2
    output = capsys.readouterr().out
    assert "10123" not in output and '"connected_demo": false' in output
